// SPDX-License-Identifier: MPL-2.0
let engineeringSelected = null, engineeringRenderKey = "";
const engineeringWords = /出口|疏散|照明|布灯|配电|检修|防水|隔热|用水|墙|门|房间|电气|设备/;
function cleanEngineeringText(text) {
  return String(text || "").replace(/\*\*|^#{1,6}\s*/gm, "").replace(/(?:decision_|sem_|finding_|change_)[\w]+/g, "").replace(/\b[A-Fa-f0-9]{32,}\b/g, "").replace(/\b(?:[A-F0-9]{5,8})\b/g, "").replace(/\b(?:[A-Z]+_)+[A-Z]+\b/g, "").replace(/[（(]\s*[）)]/g, "").replace(/([：:])(?:[、，]\s*)+/g,"$1").replace(/[、，]\s*(?=[（）。；：、，]|$)/g, "").replace(/\|/g," · ").replace(/(?: · ){2,}/g," · ").replace(/^[\s·-]+|[\s·-]+$/g, "");
}
function readableMarkdown(text) {
  const out = element("div", "", "engineering-markdown");
  const lines = String(text || "").split(/\r?\n/);
  for (let i=0;i<lines.length;i++) {
    const line=lines[i].trim(); if (!line || /^[-*_]{3,}$/.test(line)) continue;
    if (line.includes("|") && /^\s*\|?\s*:?-{3}/.test(lines[i+1] || "")) {
      const table=element("table"),head=element("thead"),body=element("tbody"),tr=element("tr");
      const cells=(x)=>x.replace(/^\||\|$/g,"").split("|").map(x=>x.trim().replace(/\*\*/g,""));
      cells(line).forEach(x=>tr.append(element("th",x)));head.append(tr);i++;
      while (i+1<lines.length && lines[i+1].includes("|")) { const row=element("tr");cells(lines[++i].trim()).forEach(x=>row.append(element("td",x)));body.append(row); }
      table.append(head,body);out.append(table);continue;
    }
    const heading=line.match(/^(#{1,6})\s+(.*)/);
    out.append(element(heading ? "h4" : "p",(heading ? heading[2] : line).replace(/\*\*/g,"")));
  }
  return out;
}
function engineeringParagraphs(text, rooms) {
  const rows=String(text || "").split(/\r?\n/).filter(x=>engineeringWords.test(x) && !/^[|\s:-]+$/.test(x) && !/^\s*\**(?:致|事项|依据|旧版哈希|新版哈希|变化对象数)\s*[:：]/.test(x));
  // 内部对象明细表留在完整原文；默认工程区只收可读建议，避免删去编号后剩下符号碎片。
  return rows.filter(x=>!(/(^\s*\|)|decision_|sem_|finding_/.test(x) && /change_|decision_|sem_|finding_/.test(x)))
    .map(raw=>({raw,text:cleanEngineeringText(raw),rooms:rooms.filter(r=>r.name && raw.includes(r.name)).map(r=>r.room_id)}))
    .filter(x=>x.text && !/^#{1,6}\s/.test(x.raw));
}
function engineeringSource(s) {
  if (s.engineering_notes?.version_id===s.project.current_version_id) return {text:s.engineering_notes.text,origin:s.engineering_notes.origin};
  const w=s.claims_workspace;
  return {text:w?.document?.original_text || "",origin:w ? "已载入意见；来源标记："+(w.document.model_name || "未填写作者或模型")+"。来源标记由文档提供，不证明作者身份或读过DWG。" : "还没有载入意见；下表目前只显示图纸比较结果"};
}
function engineeringLocate(room,neighbor=null) {
  return async()=>{
    if (room.old_only && room.change_ids.length) { if (await action("locate_change",{change_id:room.change_ids[0]})) showPage("drawing"); }
    else { const v=state.comparison.new_version.id;if(state.project.current_version_id!==v && !(await action("select",{id:v})))return; if(await action("locate_ref",{ref:room.room_id,neighbor}))showPage("drawing"); }
    byId("returnToChanges").hidden=false;
  };
}
async function engineeringReview(room, findingId=null) {
  if (room.old_only) return;
  if(!room.checks?.length){showError("本房间未纳入已实现的自动规则。请先看图核对其设备、照明和管线影响；当前不能进入另一房间的规则表单。");return;}
  const c=state.comparison.review_context?.find(c=>c.new.object_ids?.includes(room.room_id));
  if (room.confirmation?.status==="pending_identity" && c) {
    reviewTransfer=c.old_decision_id;reviewIntent="confirm";reviewRoomFilter=room.room_id;byId("transferTarget").textContent=room.name;renderReviewMode();showPage("review");return;
  }
  const v=state.comparison.new_version.id;
  if(state.project.current_version_id!==v && !(await action("select",{id:v})))return;
  if (!(await action("review_load")))return;
  reviewTransfer=null;reviewRoomFilter=room.room_id;renderReviewOptions();
  const f=reviewRows.find(f=>f.id===findingId && f.object_ids.includes(room.room_id)) || reviewRows.find(f=>f.object_ids.includes(room.room_id) && f.rule_id==="R1") || reviewRows.find(f=>f.object_ids.includes(room.room_id));
  if(f){byId("reviewFinding").value=f.id;reviewQueueMode=reviewRecorded(f) ? reviewWaiting(f) ? "waiting" : "done" : "pending";}
  renderReviewMode();showPage("review");
}
function engineeringDetails(room, notes=[]) {
  const card=element("article","","engineering-detail");
  const context=state.comparison.review_context?.find(c=>c.new.object_ids?.includes(room.room_id));
  card.append(element("h3",room.name),element("p",room.requires_decision ? plainReview(context,room.confirmation.status) : room.recorded ? "本房间已有复核或沿用记录；缺资料的检查仍需补齐。" : "看图核对本房间，再记录处理结果。","engineering-lead"));
  for(const alert of room.alerts || []) {const box=element("div","","engineering-alert");box.append(element("strong",alert.title),element("p",alert.text),element("p",alert.action));card.append(box);}
  card.append(element("h4","图纸已经发现什么"));room.changes.forEach(x=>card.append(element("p",x)));
  if (notes.length) {card.append(element("h4","原文建议：请与当前图纸结果对照"));notes.slice(0,6).forEach(n=>card.append(element("p",n.text)));card.append(element("small","按房名关联的原文段落，可能与当前规则结果不一致；请核对建议是否适用，旧确认状态以当前检查为准。"));}
  card.append(element("h4","你需要核对什么"));room.actions.slice(0,5).forEach(x=>card.append(element("p",cleanEngineeringText(x))));
  card.append(element("h4","当前资料与复核记录"));
  for(const f of room.checks) {
    const box=element("div","","engineering-check");
    const manual=f.values.manual_confirmation;
    box.append(element("b",f.title),element("p",f.manual_review ? f.manual_review.action==="reject" ? "已驳回 · 待重新处理" : "已记录复核 · "+(f.manual_review.disposition==="needs_change" ? "待改图" : f.manual_review.disposition==="needs_data" ? "待补资料" : "可查看意见") : f.result==="无法判定" ? "尚未复核 · 自动检查资料不全" : f.result));
    box.append(element("p",manual ? `已确认净长${manual.net_length_gt_7 ? "超过" : "不超过"}7米、出口${manual.entrance_count}处${f.values.confirmation_inherited ? "；已按原范围沿用" : ""}。` : f.next_step));
    if(f.manual_review)box.append(element("small",f.manual_review.name+" · "+new Date(f.manual_review.at).toLocaleString("zh-CN",{hour12:false})+" · "+f.manual_review.comment));
    card.append(box);
  }
  const actions=element("div","","engineering-actions");
  actions.append(GVUI.Button("secondary","看图核对",engineeringLocate(room)));
  if(!room.old_only && room.checks?.length)actions.append(GVUI.Button("primary","复核本房间事项",()=>engineeringReview(room)));
  else if(!room.old_only)card.append(element("p","本房间未纳入现有自动规则，当前仅提供改图定位；不会拿其他房间的检查来代替。请按图核对设备、照明和管线影响。"));
  for(const n of room.water_neighbors || [])actions.append(GVUI.Button("secondary","看与"+n.name+"的共同隔墙",engineeringLocate(room,n.id)));
  if(room.old_only)card.append(element("p","新版未识别到对应房间，请先在原图核对，不把它当成房间已拆除。"));
  card.prepend(actions);
  const source=technical("展开源记录与定位依据",{source_records:room.change_ids,room_reference:room.room_id,checks:room.checks});card.append(source);
  return card;
}
function engineeringBoard(host, rooms, notes=[]) {
  const list=element("div","","engineering-room-list"),detail=element("div","","engineering-room-detail");
  const pick=(r)=>{engineeringSelected=r.room_id;list.querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.roomId===r.room_id)));detail.replaceChildren(engineeringDetails(r,notes.filter(n=>n.rooms.includes(r.room_id))));};
  for(const r of rooms) {
    const bt=GVUI.Button("ghost","",()=>pick(r));bt.dataset.roomId=r.room_id;
    if(r.alerts?.length){bt.dataset.priority="true";bt.append(element("strong",r.alerts[0].title,"engineering-risk-label"));}
    bt.append(element("b",r.name),element("span",r.requires_decision ? "原确认待处理" : r.recorded ? "已有记录 · 点击查看意见" : "看图核对", "engineering-progress"),element("small",`${r.change_ids.length}条源记录已合并 · ${r.actions.slice(0,2).map(cleanEngineeringText).join("；")}`));list.append(bt);
  }
  host.append(list,detail);if(rooms.length)pick(rooms.find(r=>r.room_id===engineeringSelected)||rooms[0]);
}
function renderEngineering(s) {
  const rooms=s.comparison?.engineering_rooms || [],source=engineeringSource(s);
  const key=s.comparison?.id+"|"+s.project.current_version_id+"|"+source.text+"|"+(s.claims_workspace?.id||"");
  if(engineeringRenderKey===key)return;engineeringRenderKey=key;
  const ownNotes=s.engineering_notes?.version_id===s.project.current_version_id;
  byId("claimsTechnical").hidden=ownNotes;
  if(ownNotes)byId("claimsTechnical").open=false;
  const host=byId("claimsEngineering");host.replaceChildren();
  const info=element("div","","engineering-source");info.append(element("p",source.origin));host.append(info);
  if(!rooms.length) {info.append(element("p","先在换版页比较两版，系统才能把意见与房间变化关联起来。"),GVUI.Button("primary","去比较两版",()=>showPage("changes")));return;}
  const notes=engineeringParagraphs(source.text,rooms);
  info.append(element("p",`下方显示${rooms.length}个变化或受影响的房间，包含自动规则未覆盖的房间。意见提取${notes.length}条工程段落；有变化不等于已完成专业检查。`));
  const board=element("div","","engineering-workspace");host.append(board);engineeringBoard(board,rooms,notes);
  const unmatched=notes.filter(n=>!n.rooms.length);
  if(unmatched.length){const d=element("details");d.append(element("summary",`没有明确房名的工程段落（${unmatched.length}条，待指定房间）`));unmatched.forEach(n=>d.append(element("p",n.text)));host.append(d);}
  const reference=s.comparison?.manual_edit_reference;
  if(reference) { const d=element("details","","manual-change-reference");d.append(element("summary","本图的8项人工修改清单（事后对照，不是AI检测数）"),element("p",reference.notice));
    for(const item of reference.items) {const row=element("p");row.append(element("b",item.name+"："),element("span",item.edit));d.append(row);}host.prepend(d); }
  if(source.text){const original=element("details");original.append(element("summary","意见从哪里来？展开完整原文排版"),readableMarkdown(source.text));host.append(original);}
}
byId("engineeringExtract").onclick=()=>action("extract_engineering_notes",{text:byId("engineeringText").value});

function comparisonReviewButton(row) {
  const target=row.review_target || {}, room=state?.comparison?.engineering_rooms?.find(r=>r.room_id===target.room_id);
  const canReview=room && !room.old_only && target.finding_id && room.checks?.some(f=>f.id===target.finding_id);
  const canLocate=target.change_id || room;
  const bt=GVUI.Button("secondary",canReview ? "去复核本条" : "查看对应变化",async()=>{
    if(canReview) {await engineeringReview(room,target.finding_id);return;}
    if(target.change_id) {if(await action("locate_change",{change_id:target.change_id})){byId("returnToChanges").hidden=false;showPage("drawing");}return;}
    if(room)await engineeringLocate(room)();
  });
  bt.disabled=!canLocate;bt.title=canReview ? "打开本房间对应规则的人工复核" : "此说法没有对应的自动复核项，先查看原图变化，不进入另一房间表单";
  return bt;
}
function renderEngineeringComparison(s) {
  const out=byId("engineeringComparison"), model=s.engineering_comparison,expanded=out.querySelector("details")?.open || false;
  out.replaceChildren();out.hidden=!model?.rows?.length || claimDirty;
  if(out.hidden)return;
  const mismatches=model.rows.filter(r=>r.verdict==="不一致");
  const headLine=element("div","","engineering-comparison-head");
  headLine.append(element("strong",`AI说的 vs 图纸实际 · 核对${model.rows.length}条 · ${mismatches.length}条不一致`));out.append(headLine);
  const priority=element("div","","engineering-comparison-priority");
  for(const row of mismatches){const item=element("div","","engineering-comparison-item"),text=element("span",row.room_name+"："+row.drawing_fact);text.title=row.ai_excerpt+"\n"+row.drawing_fact;item.append(text,comparisonReviewButton(row));priority.append(item);}
  if(!mismatches.length)priority.append(element("small","所列说法未发现不一致；不代表整篇意见或设计通过。"));out.append(priority);
  const all=element("details");all.open=expanded;all.append(element("summary",`展开全部${model.rows.length}条对照与依据范围`),element("p",`从${model.checked_count}句中摘出可核对的说法，最多10条，不是图纸改动数；其余原句不代表已通过。`));
  const table=element("table"),head=element("thead"),body=element("tbody"),tr=element("tr");
  ["AI原句（关键半句）","图纸实际","一致吗"].forEach(t=>tr.append(element("th",t)));head.append(tr);
  for(const r of model.rows) {
    const line=element("tr");line.append(element("td",r.ai_excerpt),element("td",r.drawing_fact));
    const result=element("td",r.verdict);result.dataset.verdict=r.verdict;if(r.verdict==="不一致")result.append(comparisonReviewButton(r));line.append(result);body.append(line);
  }
  table.append(head,body);all.append(table,element("small",model.scope));out.append(all);
}
