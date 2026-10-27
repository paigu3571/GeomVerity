// SPDX-License-Identifier: MPL-2.0
let claimDraft = [],
  claimWorkspaceKey = "",
  claimDirty = false,
  claimsReport = null,
  claimsFilter = "all";
function markClaimsDirty() {
  claimDirty = true;
  byId("claimsDirty").textContent =
    "你改过内容，请重新点“运行逐条核验”；之前的颜色已撤下。";
  claimsReport = null;
  byId("engineeringComparison").hidden=true;
  const focused = document.activeElement,
    start = focused?.selectionStart,
    end = focused?.selectionEnd;
  byId("claimsResults")
    .querySelectorAll(".claim-edit")
    .forEach((n) => byId("claimsEditor").append(n));
  byId("claimsResults").replaceChildren();
  renderClaimsReading();
  renderClaimsFilters();
  if (focused?.isConnected) {
    focused.focus();
    if (typeof start === "number") focused.setSelectionRange(start, end);
  }
}
function claimSelection() {
  const t = byId("claimsOriginal"),
    start = Array.from(t.value.slice(0, t.selectionStart)).length,
    end = Array.from(t.value.slice(0, t.selectionEnd)).length;
  if (end <= start) throw Error("请先在原文中选中一句文字");
  return {
    text: t.value.slice(t.selectionStart, t.selectionEnd),
    span: { start, end },
  };
}
function renderClaimEditor() {
  const out = byId("claimsEditor");
  out.replaceChildren();
  if (!claimDraft.length)
    out.append(
      element(
        "p",
        "从左侧原文选择一句，添加后填写引用和需要核对的数值。",
        "empty-state",
      ),
    );
  for (const c of claimDraft) {
    const row = element("details", "", "claim-edit");
    row.dataset.claimId = c.id;
    row.append(element("summary", "修改这句话的核对方式"));
    row.append(
      element(
        "b",
        c.id +
          " · " +
          (c.extraction === "model"
            ? "AI辅助划分（" + (c.generated_by || "未记录") + "）"
            : "人工划分"),
      ),
      element("blockquote", c.text),
    );
    const range = element(
      "small",
      "原文位置 " + c.span.start + "–" + c.span.end,
    );
    row.append(range);
    const kind = element("select");
    for (const [value, label] of [
      ["reference", "引用是否存在"],
      ["area", "面积数值"],
      ["status", "确认/通过/有效性说法"],
      ["unsupported", "其他（可能无验证器）"],
    ]) {
      const o = element("option", label);
      o.value = value;
      kind.append(o);
    }
    kind.value = c.kind;
    const refs = element("input");
    refs.value = c.refs.join(", ");
    refs.placeholder = "对象 / finding / change / decision ID，逗号分隔";
    const values = element("textarea");
    values.value = JSON.stringify(c.values);
    for (const [label, input] of [
      ["检查类型", kind],
      ["依据引用", refs],
      ['结构化数值（JSON，例如 {"sem_x.area_m2":12.5}）', values],
    ]) {
      const l = element("label", label);
      l.append(input);
      row.append(l);
    }
    kind.onchange = () => {
      c.kind = kind.value;
      markClaimsDirty();
    };
    refs.oninput = () => {
      c.refs = refs.value.split(/[,，\s]+/).filter(Boolean);
      markClaimsDirty();
    };
    values.oninput = () => {
      c.valuesText = values.value;
      markClaimsDirty();
    };
    const replace = element("button", "用原文新选区替换");
    replace.onclick = () => {
      try {
        Object.assign(c, claimSelection());
        markClaimsDirty();
        renderClaimEditor();
      } catch (e) {
        showError(e.message);
      }
    };
    const remove = element("button", "移除此主张");
    remove.onclick = () => {
      claimDraft = claimDraft.filter((x) => x !== c);
      markClaimsDirty();
      renderClaimEditor();
    };
    row.append(replace, remove);
    const card = Array.from(
      byId("claimsResults").querySelectorAll("[data-claim-id]"),
    ).find((x) => x.dataset.claimId === c.id);
    (card || out).append(row);
  }
  renderClaimsReading();
}
function claimsDocument() {
  return {
    ...(state?.claims_workspace?.document || {}),
    schema_version: "claims.v1",
    original_text: byId("claimsOriginal").value,
    original_text_origin: "full_original",
    model_name: byId("claimsProducer").value || null,
    claims: claimDraft.map((c) => {
      const { valuesText, ...row } = c;
      return {
        ...row,
        values: valuesText === undefined ? row.values : JSON.parse(valuesText),
        generated_by: c.generated_by || null,
      };
    }),
  };
}
function renderClaims(s) {
  const version = s.project.versions.find(
    (v) => v.id === s.project.current_version_id,
  );
  byId("claimsVersion").textContent = version?.name || "未选择";
  const w = s.claims_workspace,
    key = s.project.current_version_id + "|" + (w?.id || "none");
  if (key !== claimWorkspaceKey) {
    claimWorkspaceKey = key;
    claimDirty = false;
    claimDraft = JSON.parse(JSON.stringify(w?.document.claims || []));
    byId("claimsOriginal").value = w?.document.original_text || "";
    byId("claimsProducer").value = w?.document.model_name || "";
    byId("claimsDirty").textContent = w?.context_stale
      ? "比较上下文已变化，历史报告保留在文件中，请重新核验。"
      : w
        ? "已保存 " + w.history.length + " 次句子与修改记录。"
        : "尚未保存主张划分。";
    renderClaimsResults(w?.context_stale ? null : w?.report);
    if (w?.context)
      byId("claimsDirty").textContent +=
        " · " +
        (w.context.status_basis === "frozen_record"
          ? "生成时冻结记录，仅核对资料忠实度"
          : "按当前版本检查") +
        " · " +
        (w.context.changes ? "已关联本次换版依据" : "未关联换版依据");
    if (w?.context) byId("claimsDirty").title = w.context.changes || "";
  }
  const catalog = byId("claimsCatalog");
  catalog.replaceChildren();
  if (s.claims_catalog) {
    for (const [key, title] of [
      ["rooms", "房间"],
      ["findings", "规则结果"],
      ["changes", "变化"],
    ]) {
      const d = element("details");
      d.append(element("summary", title));
      for (const r of s.claims_catalog[key]?.items || [])
        d.append(
          element("p", (r.name || r.rule_id || r.id) + " · " + r.id, "path"),
        );
      catalog.append(d);
    }
  }
}
function renderClaimsResults(report) {
  claimsReport = report;
  const out = byId("claimsResults");
  out.replaceChildren();
  if (!report) {
    renderClaimEditor();
    renderClaimsFilters();
    return;
  }
  out.append(
    element("h3", "每句话的核对结果"),
    element("p", report.scope, "review-help"),
  );
  for (const [sentenceIndex, row] of report.rows.entries()) {
    const card = GVUI.Card(row.conclusion, "claim-result");
    card.dataset.claimId = row.claim.id;
    card.id = "result-" + row.claim.id;
    card.tabIndex = -1;
    card.append(
      element("b", "第" + (sentenceIndex + 1) + "句"),
      GVUI.StatusBadge({
        state: row.conclusion,
        text:
          {
            支持: "这句话有依据",
            需复核: "这句话还要核对",
            矛盾: "说法与数据不一致",
            未知: "这句话暂时核对不了",
          }[row.conclusion] || row.conclusion,
      }),
      element("blockquote", row.claim.text),
    );
    const dims = element("div", "", "claim-dimensions");
    for (const [label, value] of [
      ["结论", row.conclusion],
      ["执行", row.execution],
      ["方法", row.methods.join("、")],
      ["人工复核", row.manual_review],
      ["有效性", row.validity],
    ])
      dims.append(element("span", label + "：" + value));
    card.append(
      element(
        "p",
        {
          支持: "现有图纸数据支持这句话；请点开依据看核对了哪些内容。",
          需复核:
            "这句话涉及的资料或旧确认有变化，请先看图核对，再决定是否采用。",
          矛盾: "这句话与目前读取到的数据不一致，请修改意见或核查图纸。",
          未知:
            row.execution === "无验证器"
              ? "软件目前没有办法核对这种说法，不能当成对或错。"
              : "没有找到足够依据，请补充对应房间、检查结果或数值。",
        }[row.conclusion] || "请展开依据查看本句检查情况。",
      ),
    );
    if (row.validity !== "有效")
      card.append(element("p", "本句还需重新检查：" + row.validity));
    const evidence = technical("看依据与技术详情", row);
    evidence.append(dims);
    card.append(evidence);
    for (const check of row.checks)
      evidence.append(
        element(
          "p",
          check.method + " · " + check.conclusion + "：" + check.reason,
        ),
      );
    for (const ref of row.claim.refs) {
      const bt = element("button", "在图上看这句的依据");
      bt.title = ref;
      bt.onclick = async () => {
        if (await action("locate_ref", { ref })) showPage("drawing");
      };
      card.append(bt);
    }

    out.append(card);
  }
  out.append(technical("完整原文、主张与核验报告", report));
  renderClaimEditor();
  renderClaimsFilters();
}
byId("claimsImport").onclick = () =>
  action("claims_import", {
    path: byId("claimsImportPath").value,
    changes: byId("claimsImportChanges").value,
    status_basis: byId("claimsImportBasis").value,
  });
byId("claimAdd").onclick = () => {
  try {
    const chosen = claimSelection();
    claimDraft.push({
      id: "claim_" + Date.now().toString(36) + "_" + claimDraft.length,
      ...chosen,
      refs: [],
      values: {},
      kind: "reference",
      extraction: "manual",
      generated_by: null,
    });
    markClaimsDirty();
    renderClaimEditor();
  } catch (e) {
    showError(e.message);
  }
};
byId("claimsOriginal").oninput = byId("claimsProducer").oninput =
  markClaimsDirty;
byId("claimsSources").onclick = () => action("claims_sources");
for (const [id, name] of [
  ["claimsSave", "claims_save"],
  ["claimsCheck", "claims_check"],
])
  byId(id).onclick = async () => {
    try {
      await action(name, { document: claimsDocument() });
    } catch (e) {
      showError("无法读取结构化数值：" + e.message);
    }
  };

function renderClaimsFilters() {
  const out = byId("claimsFilters");
  out.replaceChildren();
  const rows = claimsReport?.rows || [];
  for (const [key, label] of [
    ["all", "全部"],
    ["support", "支持"],
    ["review", "需复核"],
    ["contradiction", "矛盾"],
    ["unknown", "未知"],
  ]) {
    const count = rows.filter(
      (r) =>
        key === "all" || GVUI.StatusBadge(r.conclusion).dataset.state === key,
    ).length;
    const bt = GVUI.Button("ghost", label + " " + count, () => {
      claimsFilter = key;
      renderClaimsFilters();
    });
    bt.setAttribute("aria-pressed", String(claimsFilter === key));
    out.append(bt);
  }
  byId("claimsResults")
    .querySelectorAll(".claim-result")
    .forEach(
      (card) =>
        (card.hidden =
          claimsFilter !== "all" && card.dataset.state !== claimsFilter),
    );
}
function renderClaimsReading() {
  const out = byId("claimsReading"),
    text = Array.from(byId("claimsOriginal").value);
  out.replaceChildren();
  if (!text.length) {
    out.append(
      element(
        "p",
        "载入完整原文后，在此对照主张与依据。未划出的文字保持原样。",
      ),
    );
    return;
  }
  // Span offsets use Unicode code points, matching the Python claims contract.
  const cuts = new Set([0, text.length]);
  const spans = claimDraft.filter(
    (c) =>
      c.span.start >= 0 &&
      c.span.end <= text.length &&
      c.span.end > c.span.start &&
      text.slice(c.span.start, c.span.end).join("") === c.text,
  );
  spans.forEach((c) => {
    cuts.add(c.span.start);
    cuts.add(c.span.end);
  });
  const edges = Array.from(cuts).sort((a, b) => a - b);
  for (let i = 0; i < edges.length - 1; i++) {
    const start = edges[i],
      end = edges[i + 1],
      c = spans.find((c) => c.span.start <= start && c.span.end >= end);
    const content = text.slice(start, end).join("");
    if (!c) {
      out.append(document.createTextNode(content));
      continue;
    }
    const row = claimsReport?.rows.find((r) => r.claim.id === c.id),
      badge = GVUI.StatusBadge(row?.conclusion || "未知");
    const mark = element("button", content, "claim-highlight");
    mark.dataset.state = badge.dataset.state;
    mark.title = c.id + " · " + (row?.conclusion || "尚未核验");
    mark.onclick = () => {
      claimsFilter = "all";
      renderClaimsFilters();
      const target = Array.from(
        document.querySelectorAll(
          "#claimsResults .claim-result,#claimsEditor .claim-edit",
        ),
      ).find((x) => x.dataset.claimId === c.id);
      if (target) {
        if (target.tagName === "DETAILS") target.open = true;
        target.scrollIntoView({ block: "nearest" });
        target.focus();
      }
    };
    out.append(mark);
  }
}
GVUI.SplitPane(byId("claimsSplit"), 55);

byId("claimsDemo").onclick = () => action("claims_demo");
