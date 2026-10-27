// SPDX-License-Identifier: MPL-2.0

"use strict";
if (new URLSearchParams(location.search).get("embed") === "1")
  document.body.classList.add("embedded");
const DATA = JSON.parse(document.getElementById("data").textContent),
  svg = document.getElementById("drawing"),
  panel = document.getElementById("panel");
let selected = null,
  box = [],
  drag = null,
  issuesOnly = false;
const el = (id) => document.getElementById(id),
  esc = (x) =>
    String(x ?? "未提供").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    ),
  detail = (title, obj) =>
    `<details><summary>${esc(title)}</summary><pre>${esc(JSON.stringify(obj, null, 2))}</pre></details>`;
function fit(b, pad = 3) {
  if (!b) return;
  const w = Math.max(b[2], 1),
    h = Math.max(b[3], 1);
  box = [b[0] - pad, b[1] - pad, w + pad * 2, h + pad * 2];
  update();
}
function update() {
  svg.setAttribute("viewBox", box.join(" "));
}
function mode(after) {
  svg.classList.toggle("before", !after);
  el("after").classList.toggle("on", after);
  el("before").classList.toggle("on", !after);
}
function options() {
  const q = el("search").value.trim();
  el("rooms").innerHTML = DATA.rooms
    .filter(
      (r) =>
        (!issuesOnly || r.type === "drawing_issue") &&
        (!q || r.name.includes(q)),
    )
    .map(
      (r) =>
        `<option value="${esc(r.id)}">${esc(r.name || "未命名空间")}</option>`,
    )
    .join("");
  if (selected && [...el("rooms").options].some((o) => o.value === selected))
    el("rooms").value = selected;
}
function cloudPath(b) {
  const pad = 0.7,
    x = b[0] - pad,
    y = b[1] - pad,
    w = b[2] + 2 * pad,
    h = b[3] + 2 * pad,
    step = Math.max(0.7, Math.min(1.8, Math.max(w, h) / 12));
  const corners = [
    [x, y],
    [x + w, y],
    [x + w, y + h],
    [x, y + h],
    [x, y],
  ];
  let d = `M${x},${y}`;
  for (let k = 0; k < 4; k++) {
    const [ax, ay] = corners[k],
      [bx, by] = corners[k + 1],
      len = Math.hypot(bx - ax, by - ay),
      n = Math.ceil(len / step),
      ux = (bx - ax) / len,
      uy = (by - ay) / len;
    for (let i = 0; i < n; i++) {
      const tx = ax + (((i + 1) * len) / n) * ux,
        ty = ay + (((i + 1) * len) / n) * uy,
        cx = ax + (((i + 0.5) * len) / n) * ux + ((uy * len) / n) * 0.4,
        cy = ay + (((i + 0.5) * len) / n) * uy - ((ux * len) / n) * 0.4;
      d += `Q${cx},${cy} ${tx},${ty}`;
    }
  }
  return d + "Z";
}
function highlight(bounds, extra = "") {
  el("focus").innerHTML =
    (bounds && !(DATA.change_summary && !svg.classList.contains("changes-off"))
      ? `<path class="focus-cloud" d="${cloudPath(bounds)}"/>`
      : "") + extra;
}
function rows(label, value) {
  return `<div class="line"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
}
function relationRows(id) {
  const o = DATA.objects[id],
    groups = new Map();
  for (const r of DATA.neighbors || []) {
    if (r.room_id !== id && r.room_handle !== o?.source?.handle) continue;
    const key = r.other_handle + "|" + r.other_name;
    if (!groups.has(key)) groups.set(key, r);
  }
  return [...groups.values()];
}
function showNeighbor(id, r) {
  select(id);
  const o = DATA.objects[id],
    n = DATA.objects[r.other_id];
  if (!n?.view_bounds) return;
  const a = o.view_bounds,
    b = n.view_bounds,
    x = Math.min(a[0], b[0]),
    y = Math.min(a[1], b[1]),
    bounds = [
      x,
      y,
      Math.max(a[0] + a[2], b[0] + b[2]) - x,
      Math.max(a[1] + a[3], b[1] + b[3]) - y,
    ];
  const related = (DATA.neighbors || []).filter(
    (v) =>
      (v.room_id === id || v.room_handle === o.source.handle) &&
      v.other_handle === r.other_handle &&
      v.other_name === r.other_name,
  );
  const walls = [...new Set(related.map((v) => v.wall_id))];
  highlight(
    bounds,
    walls
      .map(
        (w) =>
          `<path class="neighbor-wall" d="${esc(DATA.wall_paths[w] || "")}"/>`,
      )
      .join(""),
  );
  fit(bounds, 3);
  panel.innerHTML =
    `<small>隔墙关系 / 图面核对</small><h2>${esc(o["房名"])}</h2><div class="card"><b>隔墙邻房：${esc(r.other_name)}</b><br>洋红云线圈住两间房，洋红细线标出中间墙体。<br>程序依据：同一墙体两面与两间房边界对应，重叠约 ${(r.overlap_mm / 1000).toFixed(2)} 米。</div><h3>您只需要看这一件事</h3><p>两间房是否确实隔着这堵墙相邻？如果对不上，请告诉我们这两个房名，不用读代码或填写全部表格。</p><p>用途和风险由规则继续判断；隔墙相邻本身不代表违规。</p>` +
    rows("房间来源", r.room_handle + " / " + r.other_handle) +
    rows(
      "墙体来源",
      [...new Set(related.map((v) => v.wall_handle))].join("、"),
    ) +
    `<button id="returnRoom">返回房间说明</button>` +
    detail("开发者数据：完整隔墙证据", related);
  el("returnRoom").onclick = () => select(id, true);
}

function priorities(o) {
  return o?.priorities || [];
}
function priorityBanner(o) {
  const a = priorities(o);
  if (!a.length) return "";
  return a
    .map(
      (p, i) =>
        `<section class="priority-card ${p.rank === 0 ? "urgent" : ""}"><span class="priority-tag">${i === 0 ? "① 优先处理" : "同样需要优先核对"}</span><h3>${esc(p.title)}</h3><p>${esc(displayWords(p.text))}</p><p><b>先做什么：</b>${esc(displayWords(p.action))}</p><div class="priority-secondary">${esc(displayWords(p.boundary))}</div></section>`,
    )
    .join("");
}
function rulePriority(f) {
  return f.priority_rank ?? 3;
}

function openingChangeCards(o) {
  const changes = o["门窗变更"] || [];
  if (!changes.length) return "";
  const note = DATA.change_summary?.engineer_comparison?.items.find(
    (r) =>
      r.engineer_correction &&
      r.target_name === (o["变更"]?.new?.name || o["房名"]),
  );
  return (
    (note
      ? '<div class="card"><b>门位移动（张田已确认）</b><br>原记录房名已更正为本房间；旧、新门位如下，可分别点图核对。</div>'
      : "") +
    "<h3>门窗位置变化</h3>" +
    changes
      .map(
        (c) =>
          `<div class="card"><b>${esc(c.kinds.includes("删除") ? "旧门窗位置取消（灰虚线）" : c.kinds.includes("新增") ? "新版门窗位置（绿色）" : "门窗位置或来源变化")}</b><br><details><summary>技术详情</summary>旧图编号：${esc(c.old_handle || "无旧对象")}；新图编号：${esc(c.new_handle || "无新对象")}</details>${c.old_handle ? "旧位置已经画出灰色虚线；" : ""}${c.new_handle ? "新版位置已高亮。" : ""}<br><button data-opening-change="${esc(c.change_id)}">在图上看${c.kinds.includes("删除") ? "旧位置" : "新位置"}</button></div>`,
      )
      .join("") +
    "<p>请分别看图核对原门口和新门口；软件记录不能代替实际出口检查。</p>"
  );
}
function bindOpeningChanges() {
  panel.querySelectorAll("[data-opening-change]").forEach(
    (b) =>
      (b.onclick = () => {
        svg.classList.remove("changes-off");
        el("changes").classList.add("on");
        mode(true);
        select(b.dataset.openingChange, true);
      }),
  );
}

function lampChangeNote(roomId) {
  const changed = DATA.change_summary?.lighting_changes?.some(
    (x) => x.new_room_id === roomId,
  );
  const deleted = (DATA.objects[roomId]?.["门窗变更"] || []).some((x) =>
    x.kinds.includes("删除"),
  );
  return changed && deleted
    ? "门已删除，此处按新墙面重新布灯。仍是实验布灯结果，请工程师核对安装位置和布灯逻辑。"
    : "";
}

function displayWords(text) {
  return String(text || "")
    .replaceAll("门洞候选", "待核对的门")
    .replaceAll("围合差异", "房间边界差别")
    .replaceAll("来源对象变化", "CAD内部编号更新")
    .replaceAll("来源身份变化", "CAD内部编号更新")
    .replaceAll("来源对应", "图上同一房间的核对")
    .replaceAll("候选", "软件识别结果");
}
