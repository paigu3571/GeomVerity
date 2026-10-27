// SPDX-License-Identifier: MPL-2.0
// 灯具最后绘制，透明点击区覆盖房间和变化线；旧灯先画、新灯在最上层。
for (const selector of [".lamp.invalid", ".lamp:not(.invalid)"])
  svg
    .querySelectorAll(selector)
    .forEach((lamp) => svg.querySelector(".semantic").append(lamp));
const detailPanel = GVUI.FloatingPanel(el("objectPanel"), el("focusCanvas"));
detailPanel.setCollapsed(false);
el("listToggle").disabled = !DATA.change_summary;
el("listToggle").onclick = () => {
  el("changeList").hidden = !el("changeList").hidden;
  el("listToggle").classList.toggle("on", !el("changeList").hidden);
};
el("listFilter").onchange = renderChangeList;
el("focusCanvas").onclick = () => {
  const active = document.body.classList.toggle("drawing-focus");
  detailPanel.setCollapsed(active);
  el("focusCanvas").setAttribute("aria-pressed", String(active));
  el("focusCanvas").textContent = active ? "展开详情" : "收起详情";
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    el("changeList").hidden = true;
    el("listToggle").classList.remove("on");
    document.body.classList.remove("drawing-focus");
    detailPanel.setCollapsed(false);
    el("focusCanvas").setAttribute("aria-pressed", "false");
    el("focusCanvas").textContent = "收起详情";
  }
});
if (DATA.change_summary) {
  const t = DATA.change_summary.times;
  if (t)
    el("changeTimes").innerHTML =
      `旧版扫描：${esc(t.old_scan)} → 新版扫描：${esc(t.new_scan)}（北京时间）<br>新版图纸保存：${esc(t.new_file_saved)}；本次对比生成：${esc(t.comparison_generated)}<br>${esc(t.meaning)}`;
  const answer = DATA.change_summary.engineer_comparison;
  if (answer)
    el("answerComparison").innerHTML =
      "<details><summary>与张田修改记录对照（" +
      answer.items.length +
      " 项）</summary>" +
      answer.items
        .map(
          (r) =>
            `<div class="card"><b>${esc(r.id)} · ${esc(r.name)}</b><br>实际修改：${esc(r.edit)}<br>当前对照：${esc(r.observed)}<br>期望输出：${esc(r.expected)}<br>${esc(r.status)}<br><button data-answer-handle="${esc(r.target_handle || "")}" data-answer-name="${esc(r.target_name || r.name)}">在图上查看</button></div>`,
        )
        .join("") +
      "</details>";
  el("answerComparison")
    .querySelectorAll("[data-answer-handle]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          const id =
            Object.keys(DATA.objects).find(
              (id) =>
                DATA.objects[id]["类型"] === "change" &&
                DATA.objects[id]["源Handle列表"].includes(
                  b.dataset.answerHandle,
                ),
            ) ||
            DATA.rooms.find(
              (r) => r.type === "space" && r.name === b.dataset.answerName,
            )?.id;
          if (id) {
            mode(true);
            select(id, true);
          }
        }),
    );
  renderChangeList();
}
el("allChanges").disabled = !DATA.change_summary;
el("allChanges").onclick = () => {
  svg.classList.toggle("changes-room-only");
  el("allChanges").classList.toggle(
    "on",
    !svg.classList.contains("changes-room-only"),
  );
};
el("changes").disabled = !DATA.change_summary;
el("changes").classList.toggle("on", !!DATA.change_summary);
el("changes").onclick = () => {
  svg.classList.toggle("changes-off");
  el("changes").classList.toggle("on", !svg.classList.contains("changes-off"));
  const r = DATA.rooms.find((r) => r.type === "change");
  if (r) select(r.id, true);
};
el("issues").onclick = () => {
  issuesOnly = !issuesOnly;
  el("issues").classList.toggle("on", issuesOnly);
  el("search").value = "";
  options();
  if (issuesOnly) {
    const r = DATA.rooms.find((r) => r.type === "drawing_issue");
    if (r) {
      mode(true);
      select(r.id, true);
    } else { panel.innerHTML="<h2>没有可定位的房名问题</h2><p>本次扫描没有提供可定位的未识别房名。这不代表全图没有问题，请检查扫描体检。</p>"; }
  }
};
el("before").onclick = () => mode(false);
el("after").onclick = () => mode(true);
el("all").onclick = () => fit(DATA.full_bounds, 4);
el("back").onclick = () => {
  issuesOnly = false;
  el("issues").classList.remove("on");
  options();
  mode(true);
  if (DATA.default) select(DATA.default, true);
};
el("search").oninput = options;
el("rooms").onchange = () => {
  mode(true);
  select(el("rooms").value, true);
};
svg.onclick = (e) => {
  if (drag?.moved) return;
  const o = e.target.closest("[data-id]");
  if (o) select(o.dataset.id);
};
svg.onkeydown = (e) => {
  if (e.key === "Enter" && e.target.dataset.id) select(e.target.dataset.id);
};
svg.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(
        svg.getScreenCTM().inverse(),
      ),
      factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    box = [
      p.x + (box[0] - p.x) * factor,
      p.y + (box[1] - p.y) * factor,
      box[2] * factor,
      box[3] * factor,
    ];
    update();
  },
  { passive: false },
);
svg.onpointerdown = (e) => {
  if (e.button !== 0) return;
  drag = {
    x: e.clientX,
    y: e.clientY,
    b: [...box],
    moved: false,
    id: drawingTarget(e),
  };
  svg.setPointerCapture(e.pointerId);
};
svg.onpointermove = (e) => {
  if (!drag) return;
  const scale = svg.getScreenCTM().a,
    dx = (e.clientX - drag.x) / scale,
    dy = (e.clientY - drag.y) / scale;
  if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 4)
    drag.moved = true;
  box = [drag.b[0] - dx, drag.b[1] - dy, drag.b[2], drag.b[3]];
  update();
};
svg.onpointerup = () => {
  if (drag?.moved) setTimeout(() => (drag = null), 0);
  else {
    const id = drag?.id;
    drag = null;
    if (id) select(id);
  }
};
el("foot").textContent =
  (DATA.change_summary
    ? `${DATA.change_summary.change_count} 条对象变化候选 · ${DATA.change_summary.cloud_regions?.length || 0} 处合并云线范围，细项用颜色和清单显示；默认显示房间变化；点“全部变更”查看墙/门等 · `
    : "") +
  `${DATA.rooms.filter((r) => r.type === "space").length} 个空间 · ${DATA.rooms.filter((r) => r.type === "shaft").length} 个井道 · ${DATA.rooms.filter((r) => r.type === "zone").length} 个区域 · ${DATA.rooms.filter((r) => r.type === "drawing_issue").length} 处图纸问题 · 点房间查规则，点灯具查来源，点邻房看隔墙；查看器不修改源图`;
if (DATA.change_summary)
  el("change-clouds").innerHTML = (DATA.change_summary.cloud_regions || [])
    .map(
      (r) =>
        `<path class="focus-cloud change-shape" data-region="${esc(r.id)}" d="${cloudPath(r.view_bounds)}"/>`,
    )
    .join("");
options();
fit(DATA.full_bounds);
if (DATA.default) select(DATA.default, true);
else panel.innerHTML = "<h2>点击对象查看来源</h2>";
const params = new URLSearchParams(location.search);
if (params.get("room") && DATA.objects[params.get("room")])
  select(params.get("room"), true);
if (params.get("mode") === "before") mode(false);

el("closeObject").onclick = () => el("focusCanvas").click();
el("themeToggle").onclick = () => {
  const light = document.body.classList.toggle("drawing-light");
  el("themeToggle").textContent = light ? "深色画布" : "浅色画布";
  el("themeToggle").setAttribute("aria-pressed", String(light));
};
el("drawingHelp").onclick = () => el("drawingHelpDialog").showModal();
el("closeDrawingHelp").onclick = () => el("drawingHelpDialog").close();
for (const [id, cls] of [
  ["layerSource", "hide-source"],
  ["layerSemantic", "hide-semantic"],
  ["layerChanges", "hide-changes"],
])
  el(id).onchange = () => svg.classList.toggle(cls, !el(id).checked);

// 后绘制的变化线可能盖住灯具：在屏幕14px内优先选择最近的可见灯具。
function drawingTarget(e) {
  const matrix = svg.getScreenCTM();
  let nearest = null,
    distance = 14;
  if (
    !svg.classList.contains("before") &&
    !svg.classList.contains("hide-semantic")
  )
    for (const lamp of svg.querySelectorAll(".lamp:not(.invalid)")) {
      const circle = lamp.querySelector("circle:not(.lamp-hit)");
      if (!circle || !lamp.getClientRects().length) continue;
      const point = new DOMPoint(
        circle.cx.baseVal.value,
        circle.cy.baseVal.value,
      ).matrixTransform(matrix);
      const d = Math.hypot(point.x - e.clientX, point.y - e.clientY);
      if (d < distance) {
        distance = d;
        nearest = lamp.dataset.id;
      }
    }
  return nearest || e.target.closest("[data-id]")?.dataset.id;
}
svg.onclick = (e) => {
  if (!drag?.moved) {
    const id = drawingTarget(e);
    if (id) select(id);
  }
};

el("layerGrid").onchange = () =>
  document.body.classList.toggle("drawing-grid-on", el("layerGrid").checked);

// 用于路演静态对照：只改变镜头与核对云线，不改任何图纸或判定。
if (params.get("snapshot") === "1") {
  document.body.classList.add("snapshot");
  const requested = JSON.parse(params.get("clouds") || "[]");
  const rectangles = requested
    .filter(
      (b) => Array.isArray(b) && b.length === 4 && b.every(Number.isFinite),
    )
    .slice(0, 12);
  if (rectangles.length) {
    const [ox, oy] = DATA.origin_wcs_mm;
    el("change-clouds").replaceChildren();
    el("focus").innerHTML = rectangles
      .map(
        (b) =>
          `<path class="focus-cloud" d="${cloudPath([(b[0] - ox) / 1000, -(b[3] - oy) / 1000, (b[2] - b[0]) / 1000, (b[3] - b[1]) / 1000])}"/>`,
      )
      .join("");
  }
}

el("layerOld").onchange=()=>svg.classList.toggle("show-old",el("layerOld").checked);

// 演示时只隐藏实验符号，不关闭房间/门/变化线，也不改变布灯或专业结果。
el("toggleLights").onclick=()=>{
  const hidden=svg.classList.toggle("hide-lamps");
  el("toggleLights").setAttribute("aria-pressed",String(hidden));
  el("toggleLights").textContent=hidden ? "显示实验灯具" : "隐藏实验灯具";
};

// Parent review updates only annotations; the camera, lamp toggle and source SVG stay intact.
window.addEventListener("message",event=>{
 if(event.source!==parent || event.origin!==location.origin || event.data?.type!=="gv-review-update")return;
 const payload=event.data.payload;if(payload?.drawing_hash!==DATA.drawing_sha256 || !Array.isArray(payload.findings))return;
 const index=new Map(payload.findings.map(f=>[f.id,f]));
 for(const object of Object.values(DATA.objects))object["适用规则结果"]=(object["适用规则结果"] || []).map(f=>index.get(f.id) || f);
 if(DATA.change_summary)DATA.change_summary.review_inheritance=payload.inheritance;
 if(selected)select(selected,false);
});

const requestedNeighbor=params.get("neighbor");
if(selected && requestedNeighbor){const relation=relationRows(selected).find(r=>r.other_id===requestedNeighbor);if(relation)showNeighbor(selected,relation);}
