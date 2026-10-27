// SPDX-License-Identifier: MPL-2.0
function renderProject(s) {
  byId("versions").replaceChildren();
  for (const v of s.project.versions) {
    const health = (s.health || {})[v.id];
    const active = v.id === s.project.current_version_id;
    const card = GVUI.Card(
      {
        state: health?.tone || "unknown",
        text: health?.tone === "warning" && Number.isFinite(health.gap_record_count)
          ? "有" + health.gap_record_count + "处读取不完整 · 需复核"
          : GVUI.HealthLabel(health),
      },
      "version-card" + (active ? " current" : ""),
    );
    card.dataset.tone = health ? health.tone : "unknown";
    const top = element("div", "", "card-top");
    top.append(element("h3", v.name));
    if (active) top.append(element("span", "当前版本", "chip"));
    const conclusion = element("p", "", "conclusion");
    conclusion.append(card.statusBadge);
    card.append(top, conclusion);
    const metrics = element("div", "", "metrics");
    for (const item of health?.display_metrics || []) {
      const metric = GVUI.MetricCard(item.count, item.label);
      metrics.append(metric);
    }
    card.append(metrics);
    card.statusBadge.title = health?.conclusion || "等待只读体检…";
    if (health)
      card.append(element("p", "仅限数据分析，不代表专业通过", "version-note"));
    const meta = element("div", "", "meta");
    meta.append(
      element(
        "span",
        "扫描 " + (health?.generated_at_utc?.slice(0, 10) || "未知") + " UTC",
      ),
      element("span", "插件 " + (health?.producer_version || "未知")),
      element("span", "配置 " + (health?.profile_version || "未知")),
    );
    card.append(meta);
    if (health)
      card.append(
        element(
          "div",
          "读不出的天正对象 " +
            (health.unreadable_proxy_count ?? "未知") +
            " · 图形有问题 " +
            (health.invalid_geometry_count ?? "未知") +
            " · 有房名但没围成房间 " +
            (health.unresolved_space_label_count ?? "未知"),
          "gaps",
        ),
      );
    if (health) {
      const details = element("details", "");
      details.className = "path";
      details.append(element("summary", "扫描说明"));
      details.append(
        element(
          "p",
          "读取图中天正对象的解释器：" + (health.fact_provider_id || "未知"),
        ),
      );
      details.append(GVUI.CodeText("插件 " + (health.producer_version || "未知")), GVUI.CodeText("配置 " + (health.profile_version || "未知")));
      if (health.reason_codes?.length)
        details.append(GVUI.CodeText(health.reason_codes.join(" · ")));
      card.append(details);
    }
    const fileMeta = element(
      "p",
      [health?.drawing_file || "文件名未知", v.note]
        .filter(Boolean)
        .join(" · "),
      "version-note file-meta",
    );
    fileMeta.title = "扫描目录：" + v.scan_directory;
    card.append(fileMeta);
    if (health && !health.load_ok) {
      const detail = element("details", "");
      detail.append(element("summary", "查看加载原因"));
      for (const [layer, value] of Object.entries(health.layers)) {
        if (value.error)
          detail.append(element("p", layer + "：" + value.error, "path"));
      }
      card.append(detail);
    }
    const actions = element("div", "", "card-actions");
    const select = GVUI.Button("secondary", active ? "已选用" : "设为当前版");
    select.type = "button";
    select.onclick = () => action("select", { id: v.id });
    const view = GVUI.Button("ghost", "查看图面");
    view.type = "button";
    view.onclick = async () => {
      if (!(await action("select", { id: v.id }))) return;
      showPage("drawing");
      await action("view");
    };
    if (active)
      actions.append(element("span", "当前版本", "current-label"), view);
    else actions.append(select, view);
    card.append(actions);
    byId("versions").append(card);
  }
  const empty = !s.project.versions.length;
  byId("addVersion").hidden = empty;
  byId("versions").classList.toggle("empty-grid", empty);
  if (empty)
    byId("versions").append(
      GVUI.EmptyState(
        "这个项目还没有扫描版本",
        "先在 CAD 中采集，再添加扫描结果文件夹。",
        () => byId("addVersion").onclick(),
        () => byId("scanHelpDialog").showModal(),
      ),
    );
}
