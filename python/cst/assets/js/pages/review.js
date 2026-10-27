// SPDX-License-Identifier: MPL-2.0
let reviewFormKey = "", reviewQueueMode="pending", reviewRoomFilter=null;
let reviewIntent = "confirm", reviewDisposition="recorded";
let reviewTransfer = null,
  reviewRows = [],
  reviewVersionKey = "";
function renderReviewOptions() {
 if(reviewTransfer)return;
 const select=byId("reviewFinding"),previous=select.value;select.replaceChildren();
 const choices=reviewRows.filter(f=>!reviewRoomFilter || f.object_ids.includes(reviewRoomFilter));
 for(const f of choices) {const option=element("option",(f.object_name || "无适用房间")+" · "+(f.rule_title || f.rule_id)+" · "+f.result);option.value=f.id;select.append(option);}
 if(choices.some(f=>f.id===previous))select.value=previous;
}
function renderReviewMode() {
  renderReviewOptions();
  byId("transferTarget").hidden = !reviewTransfer;
  byId("transferAckLabel").hidden = !reviewTransfer;
  byId("reviewFinding").disabled = !!reviewTransfer;
  byId("reviewFindingLabel").hidden = !!reviewTransfer;
  renderReviewFinding();
  renderReviewQueue();
  renderReviewPresets();
  byId("reviewCancelTransfer").hidden = !reviewTransfer;
  byId("reviewConfirm").textContent = reviewTransfer
    ? reviewIntent === "reject"
      ? "记录为不同房间，不沿用"
      : "确认沿用原来的确认"
    : "保存本条复核";
  byId("reviewReject").textContent = reviewTransfer ? "暂不沿用" : "驳回本条";
  byId("transferAck").checked = false;
}
function renderReviews(s) {
  if (byId("reviewSyntheticLabel"))
    byId("reviewSyntheticLabel").hidden = !s.development;
  if (!s.development && byId("reviewSynthetic"))
    byId("reviewSynthetic").checked = false;
  if (reviewTransfer) renderReviewFinding();
  const data = s.review_findings,
    key = s.project.current_version_id + "|" + JSON.stringify(data || null);
  if (key === reviewVersionKey) return;
  reviewVersionKey = key;
  reviewRows =
    data?.version_id === s.project.current_version_id ? data.findings : [];
  renderReviewOptions();
  renderReviewFinding();
  renderReviewQueue();
  renderReviewPresets();
  const history = byId("reviewHistory");
  history.replaceChildren();
  if (data)
    {const list=element("details");list.append(element("summary","全部本地复核记录（"+data.events.length+"条）"));
     for(const record of [...data.events].reverse()) list.append(reviewRecordCard(record));history.append(list,technical("履历校验技术数据",data.events));}
}
function renderReviewFinding() {
  const out = byId("reviewFindingDetail");
  out.replaceChildren();
  if (reviewTransfer) {
    const c = state?.comparison?.review_context?.find(
      (x) => x.old_decision_id === reviewTransfer,
    );
    out.dataset.oldDecisionId = reviewTransfer;
    out.append(element("h3", "先看图，再确认是不是同一间房"));
    if (!c) {
      out.append(element("p", "本条对应依据未载入，请退出并重新比较。"));
      return;
    }
    out.append(
      element(
        "p",
        reviewIntent === "reject"
          ? "你选择：不是同一间房，不沿用原确认。"
          : "你选择：是同一间房，仅沿用原来的确认范围。",
      ),
    );
    out.append(
      element("h3", c.old.object_name || "未识别适用房间"),
      element("p", plainReview(c, "pending_identity")),
      reviewRoomButton(c),
    );
    for (const [title, f] of [
      ["旧版", c.old],
      ["新版", c.new],
    ]) {
      out.append(
        element("h4", title + " · " + (f.object_name || "无对应对象")),
        element("p", "规则：" + (f.rule_title || "未记录")),

        GVUI.StatusBadge(f.result || "未知"),
        element("p", title === "新版" ? transferHelp(c, reviewIntent) : missingHelp(f)),

        technical("技术详情：" + title, {
          object_ids: f.object_ids,
          values: f.values,
          scope: f.scope,
        }),
      );
    }
    out.append(technical("技术详情", c));
    out.append(
      element("p", "原确认人：" + (c.engineer.confirmed_by || "无")),
      element(
        "p",
        "原确认范围：" + (c.engineer.scope || c.old.scope || "未记录"),
      ),
      technical("原确认与房间出口候选", {
        engineer: c.engineer,
        room_review: c.room_review,
      }),
    );
    return;
  }
  delete out.dataset.oldDecisionId;
  const f = reviewRows.find((x) => x.id === byId("reviewFinding").value);
  if (f) {
    if(f.manual_review)out.append(reviewRecordCard(f.manual_review));
    out.append(
      element("h3", "本条要核对和记录的事"),
      element("h3", f.object_name || "无适用房间"),
      element("p", f.rule_title || f.rule_id),
      GVUI.StatusBadge(f.result),

      element(
        "p",
        "原确认范围：" + (f.decision?.engineer?.scope || "无已记录确认"),
      ),
      technical("技术详情", {
        reason: f.reason,
        object_ids: f.object_ids,
        scope: f.scope,
        values: f.values,
      }),
    );
    byId("reviewFindingDetail").append(
      reviewRoomButton({ new: f }, state.project.current_version_id),
      element("p", missingHelp(f)),
      element(
        "p",
        "现有工具结论：" + f.result + "；确认不会把“无法判定”改成“通过”。",
      ),
    );

  }
}
function roomReviewRows() {
  let rows=reviewRows;
  const relevant=new Set((state?.comparison?.engineering_rooms || []).map(r=>r.room_id));
  if(reviewRoomFilter)rows=rows.filter(f=>f.object_ids.includes(reviewRoomFilter));
  else if(relevant.size)rows=rows.filter(f=>f.object_ids.some(id=>relevant.has(id)));
  return rows;
}
function reviewRecorded(f) { return f.manual_review ? f.manual_review.action!=="reject" : !!f.values?.confirmation_inherited; }
function reviewWaiting(f) { return f.manual_review && f.manual_review.action!=="reject" ? (f.manual_review.disposition ? f.manual_review.disposition==="needs_data" : false) : false; }
function reviewRecordCard(record) {
 const card=element("article","","review-saved-record");
 const label=record.action==="reject" ? "已驳回，待重新处理" : {recorded:"已核对并记录意见",needs_data:"等待补充资料",needs_change:"发现问题，待改图"}[record.disposition] || "历史记录（未分类）";
 card.append(element("strong",label),element("p",record.name+" · "+new Date(record.at).toLocaleString("zh-CN",{hour12:false})),element("p","适用房间："+record.scope),element("p",record.comment));return card;
}
function nextReviewItem() {
  const rows=roomReviewRows().filter(f=>!reviewRecorded(f));
  if(rows.length){reviewTransfer=null;byId("reviewFinding").value=rows[0].id;renderReviewMode();}
  else {showPage("changes");reviewTab="priority";renderReviewBody();}
}
function renderReviewQueue() {
  const out=byId("reviewQueue");out.replaceChildren();
  // 沿用表单已有明确对象；普通规则队列的计数与空状态不适用于它。
  if(reviewTransfer) {
    const context=state?.comparison?.review_context?.find(c=>c.old_decision_id===reviewTransfer);
    out.append(element("h3","正在复核："+(context?.new.object_name || context?.old.object_name || "房间依据待载入")),element("p","核对是否为同一间房，仅沿用原确认范围。填写右侧意见后再提交；返回不会记录。"));
    return;
  }
  const rows=roomReviewRows(), tabs=element("div","","review-progress-tabs");
  for(const [key,label,predicate] of [["pending","待处理",f=>!reviewRecorded(f)],["waiting","待补资料",f=>reviewWaiting(f)],["done","已记录",f=>reviewRecorded(f) && !reviewWaiting(f)]]) {
    const bt=GVUI.Button("ghost",label+" "+rows.filter(predicate).length,()=>{reviewQueueMode=key;renderReviewQueue();});
    bt.setAttribute("aria-pressed",String(reviewQueueMode===key));tabs.append(bt);
  }
  out.append(tabs,element("p","待处理＝尚未记录或已驳回待重核；待补资料＝已明确登记缺资料；已记录＝已核对或已登记改图意见。工具结论单独保留。","review-queue-help"));
  if(reviewRoomFilter)out.append(element("p","当前房间："+(rows[0]?.object_name || "所选房间")));
  const shown=rows.filter(f=>reviewQueueMode==="pending" ? !reviewRecorded(f) : reviewQueueMode==="waiting" ? reviewWaiting(f) : reviewRecorded(f) && !reviewWaiting(f));
  if(!shown.length)out.append(element("p",reviewRows.length ? "本组没有未处理事项。可以查看待补资料或返回房间清单。" : "从换版房间清单选择一间房，或读取当前版事项。"));
  for(const f of shown) {
    const bt=GVUI.Button("ghost",f.object_name || "无适用房间",()=>{reviewTransfer=null;byId("reviewFinding").value=f.id;renderReviewMode();});
    bt.append(element("small",f.rule_title || f.rule_id),element("span",f.values?.confirmation_inherited && !f.manual_review ? "已沿用原确认" : f.manual_review ? f.manual_review.action==="reject" ? "已驳回 · 待重新处理" : reviewWaiting(f) ? "已记录 · 待补资料" : f.manual_review.disposition==="needs_change" ? "已记录 · 待改图" : "已记录" : "尚未复核 · 工具结果："+f.result));
    bt.setAttribute("aria-pressed",String(f.id===byId("reviewFinding").value));out.append(bt);
  }
}
byId("reviewFinding").onchange = () => {
  renderReviewFinding();
  renderReviewQueue();
  renderReviewPresets();
};
byId("reviewBack").onclick=()=>showPage("changes");
byId("reviewLoad").onclick = async () => {
 const v=state?.comparison?.new_version.id;
 if(v && v!==state.project.current_version_id && !(await action("select",{id:v})))return;
 await action("review_load");
};
byId("reviewCancelTransfer").onclick = () => {
  reviewTransfer = null;
  showPage("changes");
};
for (const [id, normal, transfer] of [
  ["reviewConfirm", "confirm", "confirm_identity_transfer"],
  ["reviewReject", "reject", "reject_identity_transfer"],
])
  byId(id).onclick = async () => {
    const args = {
      action: reviewTransfer
        ? reviewIntent === "reject" && normal === "confirm"
          ? "reject_identity_transfer"
          : transfer
        : normal,
      name: byId("reviewName").value,
      comment: byId("reviewComment").value,
      scope: byId("reviewScope").value,
      synthetic: state?.development === true && byId("reviewSynthetic").checked,
      disposition: reviewDisposition,
    };
    if (reviewTransfer) {
      args.old_decision_id = reviewTransfer;
      args.identity_ack = byId("transferAck").checked;
      if (await action("review_transfer", args)) {
        reviewTransfer = null;
        renderReviewMode();
        showPage("changes");
      }
    } else {
      args.finding_id = byId("reviewFinding").value;
      if (await action("review_write", args)) {
        const f=reviewRows.find(f=>f.id===args.finding_id), record=f?.manual_review;
        reviewQueueMode=reviewRecorded(f) ? reviewWaiting(f) ? "waiting" : "done" : "pending";renderReviewQueue();renderReviewFinding();
        const note=byId("reviewFeedback");note.hidden=false;note.replaceChildren(element("strong","已保存 · "+(f?.object_name || "本事项")),element("p","这条意见已在左侧“"+(!reviewRecorded(f)?"待处理":reviewWaiting(f)?"待补资料":"已记录")+"”列出。记录意见不会改变下方工具结论。"),GVUI.Button("secondary","查看刚保存记录",()=>{reviewQueueMode=reviewRecorded(f)?reviewWaiting(f)?"waiting":"done":"pending";renderReviewQueue();renderReviewFinding();byId("reviewFindingDetail").scrollIntoView({block:"start"});}),GVUI.Button("primary","下一件待处理",nextReviewItem));
      }
    }
  };

GVUI.SplitPane(byId("reviewSplit"), 35);

function plainReview(c, status) {
  if (!c) return "没有足够记录，请先看图核对这条事项。";
  const original=c.old.values?.manual_confirmation?.entrance_count, candidate=c.new.values?.candidate_opening_count;
  if (status==="invalidated" && Number.isInteger(original) && Number.isInteger(candidate))
    return `之前确认过${original}个出口；新版识别到${candidate}处门洞候选。原确认不能直接沿用，请看图核对实际出口数量。`;
  if (status === "pending_identity")
    return "之前确认过的出口条件。这次房间和门都没变，只是CAD内部编号变了。请看图确认是不是同一间房。";
  return status === "inherited"
    ? "原来的确认仍可用于原先确认的那部分内容；这不代表整图设计已经通过。"
    : status === "invalidated"
      ? "这次改动影响了原来的确认，请重新看图核对。"
      : "以前没有人工确认这条事项，请先核对图纸与检查资料。";
}

function missingHelp(f) {
  if (f.result !== "无法判定")
    return f.result === "通过"
      ? "本条数量条件已满足；只限这条检查，不是整图设计签字。"
      : "请看图核对这条检查，并补充处理意见。";
  if ((f.rule_title || "").includes("出入口") || f.rule_id === "R1")
    return "缺少已确认的室内净长或实际出口数量。请在CAD图上量取净长、逐个核对出口，在本条意见记录量取值和处理要求。本版尚无数值补录重算入口，保存文字不会改变工具结论；不要把‘已补资料’当作自动重算成功。";
  if(f.rule_id==="R3")return "缺上一层平面和楼层对应位置：请建筑提供，再核对本房间上方是否有用水场所。本版尚无上层图导入重算入口，请选择‘资料未齐’，写明需要建筑提供什么。";
  const neighbours=(f.values?.adjacent_candidates || []).filter(n=>n.water_candidate).map(n=>n.name);
  if(f.rule_id==="R4")return (neighbours.length ? "已发现贴邻候选："+neighbours.join("、")+"。" : "缺完整确认的同层用水邻房资料。")+"需建筑确认漏水/结露影响及共同隔墙防水做法。看图后，可登记待补资料或需要改图；本版不能根据文字意见自动认定防水合格。";
  return "需建筑核实同层相邻房间用途与隔墙构造，请把具体提资要求记入本条意见。";
}

function renderReviewPresets() {
  const key = reviewTransfer || byId("reviewFinding").value,
    out = byId("reviewPresets");
  out.replaceChildren();
  if (key !== reviewFormKey) {
    reviewFormKey = key;
    const c = state?.comparison?.review_context?.find(
      (x) => x.old_decision_id === reviewTransfer,
    );
    const f=reviewRows.find(f=>f.id===byId("reviewFinding").value);
    byId("reviewScope").value = c?.new.object_name || f?.object_name || "本事项";
    byId("reviewFeedback").hidden=true;
    byId("reviewComment").value = "";reviewDisposition="recorded";
  }
  out.append(
    element(
      "p",
      "选一条常用意见，也可以在下方补充或修改；选意见不会提交确认。",
    ),
  );
  const texts=reviewTransfer ? ["已看图核对，是同一房间，沿用原确认。","不是同一房间，不沿用，需要重新核对。"] : ["已核对，记录本房间意见。","资料未齐，登记缺哪些资料：","发现问题，需改图或专业处理："];
  for (const [index,text] of texts.entries()) {    out.append(
      GVUI.Button("secondary", text, () => {
        reviewDisposition=["recorded","needs_data","needs_change"][index];
        byId("reviewComment").value = text;
        byId("reviewComment").focus();
      }),
    );
  }
}

// 两个复核入口共用当前事项的新版房间引用，不读取普通队列第一项。
function reviewRoomButton(context, versionId = state?.comparison?.new_version?.id) {
  const ref = context?.new.object_ids?.[0];
  const bt = GVUI.Button("secondary", "看图并定位这间房", async () => {
    if (!ref) return;
    const version = versionId;
    if (version && state.project.current_version_id !== version)
      if (!(await action("select", { id: version }))) return;
    if (await action("locate_ref", { ref })) {
      byId("returnToChanges").hidden = false;
      showPage("drawing");
    }
  });
  if (!ref) { bt.disabled = true; bt.dataset.unavailable = "true"; }
  return bt;
}
function transferHelp(context, intent) {
  if (!context?.old.values?.manual_confirmation)
    return "这里显示尚未沿用时的结果。提交后只在原确认范围内重新核对，不能把缺资料直接当成通过；原条件不适用时请重新补齐资料。";
  if (intent === "reject")
    return "你选择不是同一间房，将不沿用原来的确认。请重新量取室内净长并核对实际出口数量，补齐资料后再检查。";
  return "这里显示的是尚未沿用原确认时的检查结果。若你看图确认是同一间房并提交沿用，原先确认的‘净长是否超过7米’和出口数量会按原范围带入新版，检查结果将重新计算；不是带入精确净长或自动判为通过。若不是同一间房，或原条件已改变，请选‘不是，重新确认’，再量取和核对。";
}
