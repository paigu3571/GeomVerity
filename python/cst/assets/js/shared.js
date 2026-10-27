// SPDX-License-Identifier: MPL-2.0

let viewerReviewSent="";
let state = null,
  busy = false,
  nativeReady = false,
  versionOptionsKey = "",
  comparisonKey = "";
const byId = (id) => document.getElementById(id);
const shorten = (path) =>
  path ? path.split(/[\\/]/).filter(Boolean).slice(-2).join(" / ") : "尚未保存";
function element(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value ?? "";
  if (className) node.className = className;
  return node;
}
function showPage(page) {
  document
    .querySelectorAll("main section")
    .forEach((s) => (s.hidden = s.id !== page));
  document.querySelectorAll("nav button[data-page]").forEach((b) => {
    const active = b.dataset.page === page;
    b.classList.toggle("active", active);
    if (active) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
}
async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-GV-Token": token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw Error(value.error || "请求失败");
  return value;
}
function setBusy(value) {
  busy = value;
  byId("busyLine").hidden = !value;
  document
    .querySelectorAll(
      "main button,header button,.toolbar button,dialog .primary",
    )
    .forEach(
      (b) =>
        (b.disabled =
          !b.hasAttribute("data-ui-control") &&
          (value || b.dataset.unavailable === "true")),
    );
  document
    .querySelectorAll("[data-pick]")
    .forEach((b) => (b.disabled = value));
  document
    .querySelectorAll(
      "#claims input,#claims textarea,#claims select,#review input,#review textarea,#review select",
    )
    .forEach(
      (n) =>
        (n.disabled = value || (n.id === "reviewFinding" && !!reviewTransfer)),
    );
}
function showError(message) {
  byId("errorPanel").textContent = message;
  byId("errorPanel").hidden = !message;
  byId("errorBadge").hidden = !message;
  document
    .querySelectorAll(".form-error")
    .forEach((n) => (n.textContent = message));
}
function render(s) {
  state = s;
  renderComparison(s);
  renderClaims(s);
  renderReviews(s);
  renderEngineering(s);
  renderEngineeringComparison(s);
  renderBundle(s);
  renderFolderBrowser(s);
  const current = s.project.versions.find(
    (v) => v.id === s.project.current_version_id,
  );
  byId("projectName").textContent = s.project.name;
  byId("drawingVersion").textContent = current?.name || "尚未选择版本";
  byId("projectFile").textContent = shorten(s.project_file);
  byId("projectFile").title = s.project_file || "项目尚未保存";
  byId("headerProject").textContent = s.project.name;
  byId("headerProject").title = s.project.name;
  byId("projectStatus").textContent = "项目：" + s.project.name;
  byId("versionStatus").textContent =
    "版本：" + (current ? current.name : "未选择版本");
  byId("taskStatus").replaceChildren(GVUI.ProgressSteps(s.message, s.job));
  renderProject(s);
  if (s.viewer) {
    byId("drawingEmpty").hidden = true;
    byId("viewer").hidden = false;
    if (byId("viewer").getAttribute("src") !== s.viewer)
      byId("viewer").src = s.viewer;
  } else {
    byId("drawingEmpty").hidden = false;
    byId("viewer").hidden = true;
    byId("viewer").removeAttribute("src");
  }
  sendViewerReview(s);
  if (s.export_output)
    byId("exportResult").textContent = "已导出：" + s.export_output;
  setBusy(busy);
}

function sendViewerReview(s) {
 const key=s?.viewer_review?.id+"|"+s?.viewer;
 if(!s?.viewer_review || !s.viewer || viewerReviewSent===key)return;
 byId("viewer").contentWindow?.postMessage({type:"gv-review-update",payload:s.viewer_review},location.origin);viewerReviewSent=key;
}
byId("viewer").addEventListener("load",()=>{viewerReviewSent="";sendViewerReview(state);});
