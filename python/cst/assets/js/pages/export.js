// SPDX-License-Identifier: MPL-2.0
let openedBundleKey = "";
function renderBundle(s) {
  const bundle = s.opened_bundle;
  if (!bundle) return;
  const key = JSON.stringify(bundle);
  if (key === openedBundleKey) return;
  openedBundleKey = key;
  const out = byId("openedBundle");
  out.replaceChildren();
  const good = bundle.verification.status === "verified";
  out.append(
    element("h3", good ? "文件完整性校验通过 · 只读回看" : "校验失败 · 已阻止回看结果"),
    element(
      "p",
      good
        ? "仅证明包内文件与清单一致，不是数字签名、身份认证或设计通过。"
        : (bundle.verification.failures || []).join("、"),
      "review-help",
    ),
  );
  if (!good) return;
  out.append(
    element(
      "p",
      (bundle.context?.project || "未记录项目") + " / " + (bundle.context?.version || "未记录版本"),
    ),
  );
  for (const row of bundle.claims_report?.rows || []) {
    const card = element("div", "", "claim-result");
    card.append(
      element("b", row.claim.text),
      element(
        "p",
        "结论：" +
          row.conclusion +
          "；执行：" +
          row.execution +
          "；方法：" +
          row.methods.join("、") +
          "；人工复核：" +
          row.manual_review +
          "；有效性：" +
          row.validity,
      ),
    );
    out.append(card);
  }
  out.append(
    technical("完整核验报告（含原文）", bundle.claims_report),
    technical("规则结果", bundle.findings),
    technical("人工复核履历", bundle.review_records),
    technical("人工划分修改履历", bundle.history),
  );
}
byId("openBundle").onclick = () => action("open_bundle", { path: byId("bundlePath").value });

let folderPickTarget=null,folderListingKey="";
async function browseFolders(path) {await action("browse_folders",{path});byId("folderBrowser").showModal();}
function renderFolderBrowser(s) {
 const value=s.folder_listing;if(!value)return;const key=JSON.stringify(value);if(key===folderListingKey)return;folderListingKey=key;
 byId("folderBrowsePath").value=value.path;byId("folderBrowseNotice").textContent=value.notice;byId("folderBrowseUse").dataset.unavailable=String(!value.path);
 const list=byId("folderBrowseList");list.replaceChildren();for(const path of value.directories)list.append(GVUI.Button("ghost",path.split(/[\\/]/).filter(Boolean).pop() || path,()=>browseFolders(path)));
}
byId("folderBrowseGo").onclick=()=>browseFolders(byId("folderBrowsePath").value);
byId("folderBrowseUp").onclick=()=>browseFolders(state.folder_listing?.parent || "");
byId("folderBrowseUse").onclick=()=>{if(!folderPickTarget || !state.folder_listing?.path)return;byId(folderPickTarget).value=state.folder_listing.path;byId("folderBrowser").close();};
