// SPDX-License-Identifier: MPL-2.0
const reviewedItems = new Set();
function renderChangeList() {
  const rows = DATA.change_summary?.checklist || [],
    f = el("listFilter").value;
  const visible = rows.filter(
    (r) =>
      f === "all" ||
      (f === "rooms" && r.type === "房间") ||
      (f === "source" && r.type !== "房间") ||
      (f === "derived" && r.basis.startsWith("派生")),
  );
  el("listCount").textContent =
    `${visible.length} 项 · 已勾选 ${reviewedItems.size} 项（仅本页核对标记）`;
  el("changeRows").innerHTML = visible
    .map(
      (r) =>
        `<div class="check-row ${priorities(DATA.objects[r.id]).length ? "priority-row" : ""}"><input type="checkbox" aria-label="已查看 ${esc(r.name)}" data-reviewed="${esc(r.id)}" ${reviewedItems.has(r.id) ? "checked" : ""}><button data-change="${esc(r.id)}" ${DATA.objects[r.id] ? "" : "disabled"}><b>${priorities(DATA.objects[r.id]).length ? "优先核对 · " : ""}${esc(r.name || "未命名房间")}</b><br>${priorities(DATA.objects[r.id])[0] ? esc(priorities(DATA.objects[r.id])[0].title) + "<br>" : ""}${esc(displayWords(r.content || "图上位置或形状有变化，请点此核对"))}<details><summary>技术详情</summary><small class="${r.basis.startsWith("派生") || r.basis.startsWith("房名文字仍在") ? "derived" : ""}">${esc(r.basis)} · ${esc(r.impact)}<br>来源：${esc(r.handles.slice(0, 6).join(" / "))}${r.handles.length > 6 ? " 等 " + r.handles.length + " 个" : ""}${r.change_ids.length > 1 ? "；重复表达合并 " + r.change_ids.length + " 条" : ""}</small></details></button></div>`,
    )
    .join("");
  el("changeRows")
    .querySelectorAll("[data-change]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          svg.classList.remove("changes-off");
          el("changes").classList.add("on");
          if (DATA.objects[b.dataset.change]?.["变更"]?.new?.type !== "space") {
            svg.classList.remove("changes-room-only");
            el("allChanges").classList.add("on");
          }
          mode(true);
          select(b.dataset.change, true);
        }),
    );
  el("changeRows")
    .querySelectorAll("[data-reviewed]")
    .forEach(
      (b) =>
        (b.onchange = () => {
          if (b.checked) reviewedItems.add(b.dataset.reviewed);
          else reviewedItems.delete(b.dataset.reviewed);
          el("listCount").textContent =
            `${visible.length} 项 · 已勾选 ${reviewedItems.size} 项（仅本页核对标记）`;
        }),
    );
}
