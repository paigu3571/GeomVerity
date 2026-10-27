// SPDX-License-Identifier: MPL-2.0
function select(id, zoom = false) {
  const o = DATA.objects[id];
  if (!o) return;
  selected = id;
  if (o["变更"] && !o["变更"].new) { svg.classList.add("show-old"); el("layerOld").checked=true; }
  svg
    .querySelectorAll(".selected")
    .forEach((e) => e.classList.remove("selected"));
  svg
    .querySelectorAll('[data-id="' + id + '"]')
    .forEach((e) => e.classList.add("selected"));
  highlight(o.view_bounds);
  if (zoom)
    fit(
      o.view_bounds,
      Math.max(
        2,
        Math.max(o.view_bounds?.[2] || 0, o.view_bounds?.[3] || 0) * 0.18,
      ),
    );
  if (o["类型"] === "change") {
    const c = o["变更"];
    highlight(o.view_bounds);
    const linkedRooms = c.impact?.rooms || [];
    panel.innerHTML =
      "<h2>" +
      esc(o["房名"]) +
      "</h2>" +
      priorityBanner(o) +
      "<h3>改了什么</h3><p>" +
      esc(displayWords(c.kinds.join("、"))) +
      "</p>" +
      "<h3>对电气有什么影响</h3><p>" +
      esc(
        linkedRooms.length
          ? "可能涉及：" +
              [...new Set(linkedRooms.map((r) => r.name))].join("、") +
              "，请看图核对。"
          : "暂未找到关联电气房间，仍需看图核实。",
      ) +
      "</p>" +
      "<h3>你要做什么</h3><p>核对图中改动；回到换版页，处理之前确认过的出口条件。</p>" +
      detail("技术详情", c);
    const linked = DATA.change_summary.lighting_changes.filter(
      (r) =>
        (c.old?.id && r.old_room_id === c.old.id) ||
        (c.new?.id && r.new_room_id === c.new.id),
    );
    if (linked.length)
      panel.innerHTML += "<h3>③ 布置调整（处理风险后查看）</h3>";
    for (const r of linked)
      panel.innerHTML +=
        '<div class="card"><b>' +
        esc(r.state) +
        "</b><br>旧候选 " +
        (r.old_count ?? 0) +
        " 个 → 新候选 " +
        r.new_count +
        " 个<br>" +
        esc(r.reason) +
        "<p>" +
        esc(lampChangeNote(r.new_room_id)) +
        "</p>" +
        "</div>";
    bindOpeningChanges();
    options();
    return;
  }
  const generated = o["类型"] === "generated_light",
    nested = o["外层块Handle"],
    handles = o["源Handle列表"] || [],
    target = nested || o.source?.handle || handles[0];
  const command =
    target && /^[0-9a-f]+$/i.test(target)
      ? `(sssetfirst nil (ssadd (handent "${target}")))`
      : null;
  if (o["类型"] === "drawing_issue") {
    const r = o["图纸问题"],
      titles = {
        EXISTING_ROOM_OVERLAP: "候选与已有房间重叠",
        MULTIPLE_LABELS: "一个围合中有多个房名",
        INNER_HOLES: "围合中有内孔",
        BELOW_AREA_THRESHOLD: "围合小于原面积门槛",
        ABOVE_AREA_THRESHOLD: "围合超出当前面积范围",
        SEARCH_EXTENT: "围合超出局部检索范围",
        TEXT_REGION_CONFLICT: "房名与已提取房间位置冲突",
        TEXT_POSITION_CANDIDATE: "文字位置候选",
        OVERHEAD_LABEL: "上空说明需核对楼层",
        NO_WALL_DATA: "缺少可用墙边界",
        UNRESOLVED_BOUNDARY: "尚未形成可用围合",
      };
    highlight(o.view_bounds, o["问题高亮"] || "");
    panel.innerHTML =
      `<small>图纸问题 / 给建筑专业的定位提示</small><h2>${esc(r.room_name)}</h2><span class="pill">${esc(titles[r.reason_code] || r.reason_code)}</span><div class="card">${esc(r.reason)}</div>` +
      rows("文字来源", r.text_handle) +
      `<p>红色叉点：程序房名定位点（文字外包框中心）。${r.gap_candidates.length ? "橙色短线与端点：附近需查看的边界端点；可能是门洞或正常墙端，不代表已证实缺墙。" : ""}${r.text_position_candidate ? "橙色虚线轮廓：附近无房名的闭合区域，连线指向建议放字位置；尚未认定属于本房间。" : ""}</p><h3>如何处理</h3><p>先看房名是否放在实际房间内，再看墙与门洞边界是否对应。确认是文字位置问题时，请在CAD里把房名放回房间内部、避免跨墙或与邻房房名混在一起；修改后重新扫描，不在查看器里修改源图。如果实际文字本来就在房间内，红点却偏出，请把截图交回；这也可能是程序取点问题，不要求为了程序挪动正确文字。</p><div class="card"><b>给下游的处理要求</b><br>${esc(r.downstream_action)}</div>`;
    if (r.gap_candidates.length)
      panel.innerHTML +=
        "<h3>边界端点候选</h3>" +
        r.gap_candidates
          .map(
            (g) =>
              `<div class="card">间距 ${g.length_mm}mm；源Handle：${esc(g.source_handles.join("、"))}</div>`,
          )
          .join("");
    if (r.text_position_candidate)
      panel.innerHTML += `<p>位置候选距原文字点到边界 ${r.text_position_candidate.distance_to_boundary_mm}mm；附近候选 ${r.text_position_candidate.nearby_empty_region_count} 处。程序未移动文字、未补墙。</p>`;
    if (nested)
      panel.innerHTML += `<p>CAD定位只能选中外层块 ${esc(nested)}；可在块内按图查找房名。</p>`;
    if (command) {
      panel.innerHTML +=
        '<button class="command" id="copy">复制CAD定位命令</button><div id="copied" class="flash"></div>';
      el("copy").onclick = async () => {
        try {
          await navigator.clipboard.writeText(command);
          el("copied").textContent = "已复制，到对应源图CAD粘贴。";
        } catch (e) {
          el("copied").textContent = "请复制：" + command;
        }
      };
    }
    panel.innerHTML += detail("开发者 / AI：问题坐标与来源数据", r);
    options();
    return;
  }
  const reviews = o["工程师确认"] || [],
    clean = o["门洞候选清洗"] || [],
    manual = clean.find((c) => c.manual_confirmation)?.manual_confirmation;
  const inputLabel = generated
    ? "规则生成的布置候选"
    : o["状态"] === "review"
      ? o.geometry?.extraction_method?.startsWith("python_wall_polygonize")
        ? "程序补提取"
        : "程序自动提取"
      : o["状态"] === "accepted"
        ? "识别检查通过"
        : o["状态"] === "rejected"
          ? "识别未采用"
          : o["状态"];
  panel.innerHTML = `<small>${generated ? "灯具布置〔实验〕" : "工程对象 / 中文说明"}</small><h2>${esc(generated ? "灯具布置〔实验〕" : o["房名"] || "图中门")}</h2><span class="pill">${esc(o["L4分类"] || "实验布灯")}</span><span class="pill">${esc(inputLabel)}</span>`;
  if (!generated)
    panel.innerHTML +=
      priorityBanner(o) +
      openingChangeCards(o) +
      rows("图纸用途", o["二级用途"] || o["L4分类"]) +
      rows(
        "轮廓面积",
        o["L2面积(m²)"] != null
          ? o["L2面积(m²)"].toFixed(1) + " m²"
          : "本次未取得面积",
      );
  const naming = o["用途解析来源"];
  if (naming?.model)
    panel.innerHTML += `<h3>用途如何确认</h3><div class="card">模型 ${esc(naming.model)} 提出用途分类；${esc(naming.approved_by)}于${esc(naming.approved_at || "见批准记录")}确认采用${esc(o["L4分类"])}。<br>${esc(naming.engineer_note || "用途经工程师批准；空间几何与规范结论另行检查。")}<br>原提议与本次校正保存在术语记录，可展开来源数据查看。</div>`;
  if (generated) {
    const g = o["生成依据"] || {},
      p = o["生成对象"] || {};
    panel.innerHTML +=
      `<div class="card"><b>${esc(g.room_name)}的${g.strategy === "wall_surface" ? "墙上布灯〔实验〕" : "均匀布灯〔实验〕"}</b><br>${g.strategy === "wall_surface" ? "安装依据：已有墙体几何面，按已提取开口避让。" : "布置依据：规整矩形内均布。"}<br>不是照度计算或施工定稿。</div>` +
      "<p>" +
      esc(lampChangeNote(o["房间"])) +
      "</p>" +
      rows("来源房间", g.room_name) +
      detail("技术详情：灯具位置与生成依据", { light: p, group: g }) +
      `<button id="parentRoom">查看来源房间</button>`;
  } else {
    if (reviews.length || manual) {
      panel.innerHTML += `<h3>已有人核对的内容</h3><div class="card"><b>出入口数量和净长条件已核对</b><br>复核人：${esc(reviews[0]?.reviewed_by || "张田")}；记录日期：${esc(reviews[0]?.reviewed_date || "见复核记录")}<br>${manual ? esc("出口 " + manual.entrance_count + " 处；净长超过7米：" + (manual.net_length_gt_7 ? "是" : "否")) : "见来源记录"}<br>这是出口条件确认，不等同整间房所有设计均已确认。</div>`;
    }
    if ((o["适用规则结果"] || []).length)
      panel.innerHTML += "<h3>② 规则依据与待补资料</h3>";
    for (const f of o["适用规则结果"] || []) {
      let label =
        f.result === "通过"
          ? "本项初查满足"
          : f.result === "无法判定"
            ? "需要补充资料"
            : f.result === "不适用"
              ? "本项不适用"
              : f.result === "不通过"
                ? "发现需处理的问题"
                : f.result;
      const titles = {
        R1: "变配电房出口数量",
        R2: "电井热源贴邻",
        R3: "变配电房上方用水场所",
        R4: "变配电房同层用水贴邻",
      };
      let reason =
        f.rule_id === "R1" && f.result === "通过" && reviews.length
          ? "工程师已核对净长和两个出入口，满足本次数量检查范围。"
          : f.reason;
      if (f.result === "无法判定") {
        if (f.rule_id === "R1")
          reason =
            "缺少实测室内净长或实际出口数量，请在CAD中量取、核对并补入检查资料后重新计算。";
        else if (f.rule_id === "R3")
          reason = "请补充上一层平面图，检查本房间上方是否有用水场所。";
        else if (f.rule_id === "R4")
          reason =
            "同层邻房范围尚未完整核对；若确实贴邻用水房间，还需隔墙防水做法。";
        else if (f.rule_id === "R2")
          reason = "本次没有提取到纳入检查的电井，不能据此说图上没有电井。";
      }
      panel.innerHTML += `<div class="card"><b>${esc(titles[f.rule_id] || f.rule_id)}</b> ${GVUI.StatusBadge({ state: f.result, text: label }).outerHTML}<br>${esc(reason)}${f.result === "无法判定" ? "<br><small>补齐对应资料后可继续计算，本轮没有把缺资料项当通过。</small>" : ""}</div>`;
    }
    const groups = o["生成对象"] || [];
    if (groups.length) {
      panel.innerHTML += "<h3>③ 灯具布置〔实验〕</h3>";
      for (const g of groups)
        panel.innerHTML += `<div class="card"><b>${g.candidate_count || 0} 盏实验灯具</b><br>${g.strategy === "wall_surface" ? "沿实际墙面布置，扣除开口避让范围" : "按规整矩形网格布置"}<br>规则：${esc(g.rule_id)}；已有墙面 ${g.mounting_wall_count || 0} 处。<br>亮蓝色符号可点击查看说明，独立DXF不修改原图。</div>`;
    }
    for(const group of o["生成对象"] || [])if(group.needs_manual_spacing_review)panel.innerHTML+=`<p class="priority-secondary">实验间距仍待人工核对：${esc(group.room_name)}在圆角、缺墙或避让处仍有布点缺口，不能作为已满足最大间距的照明布置。</p>`;
    const rs = relationRows(id);
    if (rs.length)
      panel.innerHTML +=
        "<h3>隔墙邻房：点一项在图上核对</h3>" +
        rs
          .map(
            (r, i) =>
              `<button class="neighbor" data-neighbor="${i}">${esc(r.other_name)} → 看共同隔墙</button>`,
          )
          .join("");
  }
  if (o["类型"] === "opening")
    panel.innerHTML +=
      "<p>出口条件确认属于关联房间的总数，不代表这个门洞已逐个核对。</p>";
  const chain = o["证据链"];
  const primitiveHandles = [
    ...new Set(
      (chain?.chains || []).flatMap((c) =>
        (c.l1_sources || []).map((p) => p.handle).filter(Boolean),
      ),
    ),
  ];
  panel.innerHTML +=
    "<details><summary>技术详情：图纸定位与计算过程</summary><h3>这项结果从哪里来</h3>" +
    (generated
      ? `<div class="trace-step">① 规则生成候选 → ${esc(o["生成依据"]?.room_name)}</div>`
      : "") +
    `<div class="trace-step">${generated ? "②" : "①"} 图纸中的${generated ? "来源房间" : esc(o["类型"] === "space" ? "房间" : "对象")} → ${esc(handles.join("、"))}</div><div class="trace-step">${generated ? "③" : "②"} 几何记录 → ${chain?.chains?.length || 0} 条关联证据 → 源图对象 ${esc(primitiveHandles.slice(0, 6).join("、") || "见技术详情")}</div>`;
  if (nested)
    panel.innerHTML += "<p>CAD定位会选中外层块 " + esc(nested) + "。</p>";
  if (command)
    panel.innerHTML +=
      '<button class="command" id="copy">复制CAD定位命令</button><div id="copied" class="flash"></div>';
  panel.innerHTML += detail("完整原始记录", o) + "</details>";
  if (command)
    el("copy").onclick = async () => {
      let ok = false;
      try {
        await navigator.clipboard.writeText(command);
        ok = true;
      } catch (e) {
        const t = document.createElement("textarea");
        t.value = command;
        panel.appendChild(t);
        t.select();
        ok = document.execCommand("copy");
        t.remove();
      }
      el("copied").textContent = ok
        ? "已复制，到对应源图CAD粘贴。"
        : "请手动复制：" + command;
    };
  if (generated) el("parentRoom").onclick = () => select(o["房间"], true);
  const rs = relationRows(id);
  panel
    .querySelectorAll("[data-neighbor]")
    .forEach(
      (btn) =>
        (btn.onclick = () =>
          showNeighbor(id, rs[Number(btn.dataset.neighbor)])),
    );
  bindOpeningChanges();
  options();
}
