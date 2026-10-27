// SPDX-License-Identifier: MPL-2.0
async function action(name, args = {}) {
  if (busy) return false;
  setBusy(true);
  showError("");
  let success = false;
  try {
    const job = await request("/api/action", { name, args });
    while (true) {
      const s = await request("/api/state");
      render(s);
      if (s.job.id === job.id && s.job.status !== "running") {
        if (s.job.status === "error") throw Error(s.job.error);
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
    success = true;
    if(name!=="browse_folders")document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  } catch (error) {
    showError("未完成：" + error.message + "。请检查输入后重试。");
  } finally {
    setBusy(false);
    if (state) render(state);
  }
  if (success && ["example", "create", "open", "add"].includes(name))
    await action("inspect");
  return success;
}
function projectPanel(mode) {
  byId("projectDialogTitle").textContent =
    mode === "create" ? "新建项目" : mode === "open" ? "打开项目" : "保存项目";
  byId("nameLabel").hidden = mode !== "create";
  for (const id of ["create", "open", "save"]) byId(id).hidden = id !== mode;
  byId("projectPath").value = mode === "save" ? state?.project_file || "" : "";
  showError("");
  byId("projectDialog").showModal();
}
document.querySelectorAll("nav button[data-page]").forEach(
  (b) =>
    (b.onclick = async () => {
      showPage(b.dataset.page);
      if (b.dataset.page === "drawing" && !state?.viewer && !busy)
        await action("view");
    }),
);
document
  .querySelectorAll("[data-close]")
  .forEach((b) => (b.onclick = () => byId(b.dataset.close).close()));
document.querySelectorAll("[data-pick]").forEach(
  (b) =>
    (b.onclick = async () => {
      try {
        if(nativeReady) {const selected=await window.pywebview.api.choose_folder();if(selected.path)byId(b.dataset.pick).value=selected.path;}
        else {folderPickTarget=b.dataset.pick;byId("folderBrowser").showModal();await browseFolders(byId(folderPickTarget).value || "");}
      } catch (error) {
        showError("选择文件夹未完成：" + error.message);
      }
    }),
);
window.addEventListener("pywebviewready", () => {
  byId("runtimeMode").textContent = "本机桌面窗口";
  nativeReady = true;
  document
    .querySelectorAll(".folderHint")
    .forEach(
      (n) =>
        (n.textContent = "可选择本机文件夹。项目只保存引用，不复制扫描数据。"),
    );
  setBusy(busy);
});
byId("compare").onclick = () =>
  action("compare", {
    old_id: byId("oldVersion").value,
    new_id: byId("newVersion").value,
    same_drawing: byId("sameDrawing").checked,
  });
byId("newProject").onclick = () => projectPanel("create");
byId("openProject").onclick = () => projectPanel("open");
byId("addVersion").onclick = () => {
  showError("");
  byId("versionDialog").showModal();
};
byId("saveProject").onclick = () =>
  state?.project_file ? action("save") : projectPanel("save");
byId("example").onclick = () => action("example");
byId("create").onclick = () =>
  action("create", {
    name: byId("name").value,
    path: byId("projectPath").value,
  });
byId("open").onclick = () =>
  action("open", { path: byId("projectPath").value });
byId("save").onclick = () =>
  action("save", { path: byId("projectPath").value });
byId("add").onclick = () =>
  action("add", {
    name: byId("versionName").value,
    directory: byId("scanPath").value,
    note: byId("note").value,
  });
byId("view").onclick = () => action("view",{refresh:true});
byId("openDrawing").onclick = () => action("view");
byId("exportBundle").onclick = () =>
  action("export", {
    path: byId("outputPath").value,
    claims_dirty: claimDirty,
  });
byId("errorBadge").onclick = () => {
  byId("errorPanel").hidden = !byId("errorPanel").hidden;
};
async function followRunning(s) {
  setBusy(true);
  showError("");
  try {
    while (s.job.status === "running") {
      render(s);
      await new Promise((resolve) => setTimeout(resolve, 450));
      s = await request("/api/state");
    }
    render(s);
    if (s.job.status === "error") showError("未完成：" + s.job.error);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
    if (state) render(state);
  }
}
request("/api/state")
  .then((s) => {
    render(s);
    if (s.job.status === "running") followRunning(s);
    else if (s.project.versions.some((v) => !(s.health || {})[v.id]))
      action("inspect");
  })
  .catch((e) => showError(e.message));

byId("navToggle").onclick = () => {
  const collapsed = document.body.classList.toggle("nav-collapsed");
  byId("navToggle").setAttribute("aria-expanded", String(!collapsed));
  byId("navToggle").setAttribute(
    "aria-label",
    collapsed ? "展开导航" : "收起导航",
  );
  byId("navToggle").title = collapsed ? "展开导航" : "收起导航";
};
byId("openSettings").onclick = () => byId("settingsDialog").showModal();

byId("returnToChanges").onclick = () => showPage("changes");
