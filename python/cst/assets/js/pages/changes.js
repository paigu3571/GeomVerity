// SPDX-License-Identifier: MPL-2.0
let reviewTab = "priority",
  selectedChange = null,
  queuePage = 0;
const typeLabel = {
  space: "房间",
  wall: "墙",
  door: "门",
  window: "窗",
  opening: "门洞",
  zone: "区域",
  shaft: "井道",
};
const methodLabel = {
  unique_room_label_evidence_handle: "同一房名文字来源匹配",
  stable_source_path: "稳定来源路径匹配",
  source_handle: "来源句柄匹配",
  semantic_id: "语义编号匹配",
};
function technical(title, data) {
  const d = element("details", "", "technical");
  d.append(
    element("summary", title),
    element("pre", JSON.stringify(data, null, 2)),
  );
  return d;
}
function renderComparison(s) {
  const key = s.project.versions.map((v) => v.id + v.name + v.note).join("|");
  if (versionOptionsKey !== key) {
    for (const id of ["oldVersion", "newVersion"]) {
      const select = byId(id);
      select.replaceChildren();
      for (const v of s.project.versions) {
        const o = element(
          "option",
          v.name + (v.note ? "（" + v.note + "）" : ""),
        );
        o.value = v.id;
        select.append(o);
      }
    }
    const vs = s.project.versions;
    byId("newVersion").value =
      vs.length > 1 ? vs[vs.length - 1].id : vs[0]?.id || "";
    byId("sameDrawing").checked = false;
    versionOptionsKey = key;
  }
  const r = s.comparison;
  if (comparisonKey === (r?.id || "none")) return;
  comparisonKey = r?.id || "none";
  const out = byId("comparisonResult");
  out.replaceChildren();
  if (!r) {
    out.append(
      element("div", "选择两版并比较后，在这里逐项核查。", "empty-state"),
    );
    return;
  }
  byId("compareSetup").open = false;
  selectedChange = null;
  queuePage = 0;
  reviewTab = "priority";
  const summary = element("div", "", "review-summary");
  summary.append(
    element("h3", r.old_version.name + " → " + r.new_version.name),
  );
  for (const [v, l] of [
    [r.change_count, "总改动记录"],
    [
      (r.changes || []).filter((x) => (x.new || x.old)?.type === "space")
        .length,
      "房间有改动",
    ],
  ]) {
    const n = element("div");
    n.append(element("strong", v), element("small", l));
    summary.append(n);
  }
  const confirmedRooms = new Set((r.review_context || []).filter(c => c.engineer?.confirmed_by).map(c => c.new.object_ids?.[0] || c.old.object_ids?.[0] || c.old_decision_id)).size;
  const pendingConfirmations = attentionItems(r).length;
  const confirmationNote = !confirmedRooms ? "请按房间查看。" : pendingConfirmations === confirmedRooms ? `其中${confirmedRooms}间之前确认过，需要先处理。` : pendingConfirmations ? `其中${confirmedRooms}间之前确认过，尚有${pendingConfirmations}项需要先处理。` : `其中${confirmedRooms}间之前确认过，可查看复核记录。`;
  out.append(
    element(
      "p",
      `这次比较发现${r.engineering_rooms?.length || 0}间房有变化或受影响，${confirmationNote}`,
      "review-note",
    ),
    summary,
  );
  const tabs = element("div", "", "review-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [id, label] of [
    ["priority", "按房间处理"],
    ["changes", "查看源记录"],
    ["confirm", "之前确认过的事"],
    ["diagnostic", "技术详情"],
  ]) {
    const bt = element("button", label);
    bt.dataset.reviewTab = id;
    bt.setAttribute("role", "tab");
    bt.onclick = () => {
      reviewTab = id;
      renderReviewBody();
    };
    tabs.append(bt);
  }
  out.append(tabs, element("div", "", "review-body"));
  out.lastChild.id = "reviewBody";
  renderReviewBody();
}
function renderReviewBody() {
  const r = state?.comparison;
  if (!r) return;
  document
    .querySelectorAll("[data-review-tab]")
    .forEach((b) =>
      b.setAttribute(
        "aria-selected",
        String(b.dataset.reviewTab === reviewTab),
      ),
    );
  const body = byId("reviewBody");
  body.replaceChildren();
  if (reviewTab === "priority") {
    renderAttention(body, r);
    return;
  }
  if (reviewTab === "confirm") {
    renderConfirmations(body, r);
    return;
  }
  if (reviewTab === "diagnostic") {
    const card = element("div", "", "review-detail");
    card.append(
      element("h3", "匹配记录与覆盖边界"),
      element(
        "p",
        "匹配提示用于追查来源歧义，不能把数量理解为设计问题数量。",
        "review-help",
      ),
    );
    for (const [label, value] of Object.entries(r.scan_health || {}))
      card.append(element("p", label + "体检：" + value, "review-help"));
    card.append(
      technical(
        "匹配提示 · " + (r.matching_warnings?.length || 0) + " 条",
        r.matching_warnings || [],
      ),
      technical("版本哈希与统计", {
        old_hash: r.old_hash,
        new_hash: r.new_hash,
        matched: r.matched,
        unchanged: r.unchanged,
        change_types: r.change_types,
        impact_counts: r.impact_counts,
      }),
    );
    body.append(card);
    return;
  }
  body.append(
    element(
      "p",
      "选左边一项，看右边三句话；需要核对时点“在图上定位”。看完图，再检查之前确认过的事。",
      "review-help queue-guide",
    ),
  );
  const ws = element("div", "", "review-workspace"),
    queue = element("div", "", "review-queue"),
    tools = element("div", "", "queue-tools");
  const search = element("input");
  search.id = "changeSearch";
  search.placeholder = "搜索房名";
  search.setAttribute("aria-label", "搜索变化");
  const type = element("select");
  type.id = "changeType";
  type.setAttribute("aria-label", "变化对象范围");
  for (const [v, t] of [
    ["rooms", "房间变化"],
    ["source", "墙 / 门 / 窗等"],
    ["all", "全部对象"],
  ]) {
    const o = element("option", t);
    o.value = v;
    type.append(o);
  }
  const kind = element("select");
  kind.id = "changeKind";
  kind.setAttribute("aria-label", "变化类别");
  for (const v of [
    "全部类别",
    ...new Set(r.changes.flatMap((x) => x.kinds || [])),
  ]) {
    const o = element("option", plainKinds([v]));
    o.value = v;
    kind.append(o);
  }
  tools.append(search, type, kind);
  const count = element("div", "", "queue-count");
  count.id = "queueCount";
  const rows = element("div", "", "queue-rows");
  rows.id = "queueRows";
  const pages = element("div", "", "queue-pages");
  pages.id = "queuePages";
  queue.append(tools, count, rows, pages);
  const detail = element("article", "", "review-detail");
  detail.id = "changeDetail";
  ws.append(queue, detail);
  body.append(ws);
  search.oninput =
    type.onchange =
    kind.onchange =
      () => {
        queuePage = 0;
        renderQueue();
      };
  renderQueue();
}
function renderQueue() {
  const r = state.comparison,
    q = byId("changeSearch").value.toLowerCase().trim(),
    type = byId("changeType").value,
    kind = byId("changeKind").value;
  const list = r.changes.filter((x) => {
    const ref = x.new || x.old;
    return (
      (type === "all" ||
        (type === "rooms" && ref?.type === "space") ||
        (type === "source" && ref?.type !== "space")) &&
      (kind === "全部类别" || x.kinds?.includes(kind)) &&
      (!q || JSON.stringify([x.old, x.new]).toLowerCase().includes(q))
    );
  });
  const max = Math.max(1, Math.ceil(list.length / 25));
  queuePage = Math.min(queuePage, max - 1);
  if (!list.some((x) => x.id === selectedChange)) selectedChange = list[0]?.id;
  byId("queueCount").textContent =
    list.length + " 条记录 · 每页最多25条 · 不是独立设计问题数";
  byId("queueRows").replaceChildren();
  for (const row of list.slice(queuePage * 25, queuePage * 25 + 25)) {
    const ref = row.new || row.old,
      bt = element("button", "", "queue-row");
    bt.setAttribute("aria-current", String(row.id === selectedChange));
    const name =
      row.old?.name && row.new?.name && row.old.name !== row.new.name
        ? row.old.name + " → " + row.new.name
        : ref?.name || typeLabel[ref?.type] || "未命名对象";
    const meta = [plainKinds(row.kinds), typeLabel[ref?.type] || ref?.type]
      .filter(Boolean)
      .join(" · ");
    bt.title = name + "；" + meta;
    bt.append(element("b", name), element("small", meta));
    bt.onclick = () => {
      selectedChange = row.id;
      renderQueue();
    };
    byId("queueRows").append(bt);
  }
  if (!list.length)
    byId("queueRows").append(
      element("p", "当前条件没有变化记录。", "empty-state"),
    );
  const pages = byId("queuePages");
  pages.replaceChildren();
  for (const [label, delta] of [
    ["上一页", -1],
    ["下一页", 1],
  ]) {
    const bt = element("button", label);
    bt.disabled = queuePage + delta < 0 || queuePage + delta >= max;
    bt.dataset.unavailable = String(bt.disabled);
    bt.onclick = () => {
      queuePage += delta;
      selectedChange = list[queuePage * 25]?.id;
      renderQueue();
    };
    pages.append(bt);
  }
  pages.insertBefore(
    element("span", queuePage + 1 + " / " + max),
    pages.lastChild,
  );
  renderChangeDetail(r.changes.find((x) => x.id === selectedChange));
  setBusy(busy);
}
function plainKinds(kinds) {
  return (kinds || [])
    .map(
      (x) =>
        ({
          来源对象变化: "CAD内部编号有更新",
          几何变化: "位置或形状有改动",
          名称或用途变化: "房名或用途有调整",
        })[x] || x,
    )
    .join("、");
}
function renderChangeDetail(row) {
  const card = byId("changeDetail");
  card.replaceChildren();
  if (!row) {
    card.append(element("p", "选左边一项，看这里的三句话。"));
    return;
  }
  const ref = row.new || row.old,
    rooms = row.impact?.rooms || [];
  card.append(
    element("h3", ref?.name || typeLabel[ref?.type] || "图中对象"),
    element("h4", "改了什么"),
    element("p", plainKinds(row.kinds)),
    element("h4", "对电气有什么影响"),
    element(
      "p",
      rooms.length
        ? "可能涉及：" +
            [...new Set(rooms.map((x) => x.name))].join("、") +
            "。请对照图纸核实。"
        : "软件暂未找到相关电气房间，仍需看图核对，不能当成整图没有影响。",
    ),
    element("h4", "你要做什么"),
    element(
      "p",
      "先看图中改动，再到“之前确认过的事”检查原来的确认还能不能用。",
    ),
  );
  const locate = element(
    "button",
    row.can_locate ? "在图上定位" : "暂时没有可定位的图形",
  );
  locate.disabled = !row.can_locate;
  locate.dataset.unavailable = String(!row.can_locate);
  locate.onclick = async () => {
    if (await action("locate_change", { change_id: row.id })) {
      byId("returnToChanges").hidden = false;
      showPage("drawing");
    }
  };
  const review = element("button", "查看之前确认过的事");
  review.onclick = () => {
    reviewTab = "confirm";
    renderReviewBody();
  };
  card.append(locate, review, technical("技术详情", row));
}
function renderConfirmations(body, r) {
  body.append(
    element("h3", "之前确认过的事"),
    element(
      "p",
      "先看这次改动有没有影响你以前的确认。选择后还要填写意见并亲自确认，不会自动签字。",
    ),
  );
  const other = technical("其他检查记录（以前没有人工确认）", []);
  for (const row of r.decision_inheritance || []) {
    const c = (r.review_context || []).find(
      (x) => x.old_decision_id === row.old_decision_id,
    );
    const box = element("article", "", "review-detail confirm-row");
    box.append(
      element("h3", c?.old.object_name || "图中房间"),
      GVUI.StatusBadge({
        state: row.status,
        text:
          row.status === "pending_identity"
            ? "请看图确认"
            : row.status === "invalidated"
              ? "原确认作废"
              : row.status === "inherited"
                ? "原范围仍可用"
                : "以前未确认",
      }),
      element("p", plainReview(c, row.status)),
      reviewRoomButton(c),
    );
    const start = (intent) => {
      reviewTransfer = row.old_decision_id;
      reviewIntent = intent;
      byId("transferTarget").textContent = c?.old.object_name || "本条事项";
      renderReviewMode();
      showPage("review");
    };
    if (row.status === "pending_identity" || row.identity_confirmation) {
      box.append(
        GVUI.Button("secondary", "是同一间，沿用原确认", () =>
          start("confirm"),
        ),
        GVUI.Button("ghost", "不是，重新确认", () => start("reject")),
      );
    } else if (row.status === "invalidated") {
      const bt = element("button", "重新核对这间房");
      bt.onclick = async () => {
        if (await action("review_load")) {
          const f = reviewRows.find(
            (x) =>
              x.object_name === c?.new.object_name && x.rule_id === row.rule_id,
          );
          reviewTransfer = null;
          if (f) byId("reviewFinding").value = f.id;
          renderReviewMode();
          showPage("review");
        }
      };
      box.append(bt);
    }
    box.append(technical("技术详情", { context: c, record: row }));
    (c?.engineer.confirmed_by ? body : other).append(box);
  }
  body.append(other);
}
function attentionItems(r) {
  return (r.review_inheritance || []).filter(x=>["invalidated","pending_identity"].includes(x.status) && !(r.engineering_rooms || []).some(g=>g.room_id===(x.new_room||x.old_room) && g.confirmation_recorded));
}
function renderAttention(body,r) {
  const info=element("p","按房间核对，不需要逐条处理60个源对象。先看左侧房间，再处理右侧的原确认、图纸资料或具体工程任务。","queue-guide");
  const board=element("div","","engineering-workspace");body.append(info,board);engineeringBoard(board,r.engineering_rooms || []);
}
