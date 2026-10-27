// SPDX-License-Identifier: MPL-2.0
// 只映射核心已返回的状态，不推断签字、有效性或工程结论。
(() => {
  const states = Object.freeze({
    support: { text: "支持", icon: "circle-check" },
    review: { text: "需复核", icon: "alert-triangle" },
    contradiction: { text: "矛盾", icon: "circle-x" },
    unknown: { text: "未知", icon: "help-circle" },
  });
  const aliases = Object.freeze({
    支持: "support",
    继承: "support",
    可用于分析: "support",
    通过: "support",
    inherited: "support",
    available: "support",
    需复核: "review",
    待确认: "review",
    待来源确认: "review",
    有缺口: "review",
    pending_identity: "review",
    warning: "review",
    矛盾: "contradiction",
    不通过: "contradiction",
    失效: "contradiction",
    扫描失败: "contradiction",
    invalidated: "contradiction",
    failed: "contradiction",
    未知: "unknown",
    无法判定: "unknown",
    无验证器: "unknown",
    无人工确认: "unknown",
    unconfirmed: "unknown",
  });
  const labels = Object.freeze({
    inherited: "继承",
    available: "可用于分析",
    pending_identity: "待来源确认",
    warning: "需复核",
    invalidated: "失效",
    failed: "扫描失败",
    unconfirmed: "无人工确认",
  });
  function Icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "gv-icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.dataset.icon = name;
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#ti-" + name);
    svg.append(use);
    return svg;
  }
  function StatusBadge(state) {
    const raw =
      typeof state === "object" && state !== null ? state.state : state;
    const key = states[raw] ? raw : aliases[raw] || "unknown";
    const label =
      typeof state === "object" && state !== null
        ? state.text || labels[raw] || states[key].text
        : aliases[raw]
          ? labels[raw] || raw
          : states[key].text;
    const badge = document.createElement("span");
    badge.className = "gv-status gv-status--" + key;
    badge.dataset.state = key;
    badge.append(Icon(states[key].icon), document.createTextNode(label));
    return badge;
  }
  function HealthLabel(health) {
    if (!health) return "等待体检";
    // 显示后端已给出的tone/gap计数，不由数量自行判断状态。
    const labels = {
      available: "可用于分析",
      warning: "需复核",
      failed: "扫描失败",
      unknown: "资料未知",
    };
    const label = labels[health.tone] || "资料未知";
    return health.tone === "warning" && Number.isFinite(health.gap_record_count)
      ? label + " · " + health.gap_record_count + "条缺口"
      : label;
  }
  function Button(variant, label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gv-button gv-button--" + variant;
    button.textContent = label;
    if (handler) button.onclick = handler;
    return button;
  }
  function Card(state, className = "") {
    const card = document.createElement("article");
    card.className = "gv-card " + className;
    card.statusBadge = StatusBadge(state);
    card.dataset.state = card.statusBadge.dataset.state;
    return card;
  }
  function MetricCard(count, label) {
    const metric = document.createElement("div");
    metric.className = "metric gv-metric";
    const number = document.createElement("strong");
    number.textContent = count ?? "—";
    const caption = document.createElement("span");
    caption.textContent = label;
    metric.append(number, caption);
    return metric;
  }
  function CodeText(text) {
    const code = document.createElement("code");
    code.className = "gv-code";
    code.textContent = text;
    const copy = Button("ghost", "复制", async () => {
      try {
        await navigator.clipboard.writeText(String(text));
        Toast("已复制编码");
      } catch {
        Toast("复制未完成，请手动选择编码复制", true);
      }
    });
    copy.setAttribute("aria-label", "复制编码 " + text);
    code.append(copy);
    return code;
  }
  function SplitPane(target, initial = 55) {
    const separator = document.createElement("div");
    separator.className = "gv-separator";
    separator.tabIndex = 0;
    separator.setAttribute("role", "separator");
    separator.setAttribute("aria-label", "调整左右栏宽度");
    separator.setAttribute("aria-orientation", "vertical");
    separator.setAttribute("aria-valuemin", "30");
    separator.setAttribute("aria-valuemax", "70");
    let ratio = initial;
    function set(value) {
      ratio = Math.max(30, Math.min(70, value));
      target.style.setProperty("--split-left", ratio + "%");
      separator.setAttribute("aria-valuenow", String(Math.round(ratio)));
    }
    separator.onpointerdown = (e) => {
      separator.setPointerCapture(e.pointerId);
    };
    separator.onpointermove = (e) => {
      if (!separator.hasPointerCapture(e.pointerId)) return;
      const rect = target.getBoundingClientRect();
      set(((e.clientX - rect.left) / rect.width) * 100);
    };
    separator.onpointerup = (e) => separator.releasePointerCapture(e.pointerId);
    separator.onkeydown = (e) => {
      if (["ArrowLeft", "ArrowRight", "Home"].includes(e.key)) {
        e.preventDefault();
        set(
          e.key === "Home" ? initial : ratio + (e.key === "ArrowLeft" ? -2 : 2),
        );
      }
    };
    target.insertBefore(separator, target.children[1]);
    set(initial);
  }
  function Toast(message, error = false) {
    const toast = document.createElement("div");
    toast.className = "gv-toast";
    toast.setAttribute("role", error ? "alert" : "status");
    toast.append(
      document.createTextNode(message),
      Button("ghost", "关闭", () => toast.remove()),
    );
    document.body.append(toast);
    if (!error) setTimeout(() => toast.remove(), 3000);
  }
  function EmptyState(title, description, handler, help) {
    const empty = document.createElement("div");
    empty.className = "gv-empty";
    const art = document.createElement("div");
    art.className = "gv-empty-art";
    art.setAttribute("aria-hidden", "true");
    const heading = document.createElement("h3");
    heading.textContent = title;
    const hint = document.createElement("p");
    hint.textContent = description;
    const add = Button("primary", "添加第一个扫描版本", handler);
    add.id = "emptyAddVersion";
    const link = Button("ghost", "如何获得扫描结果", help);
    link.id = "scanHelp";
    empty.append(art, heading, hint, add, link);
    return empty;
  }
  function FloatingPanel(target, control) {
    // 绑定已有结构，保留对象详情ID和选择/定位事件；只管理显示与可访问状态。
    return Object.freeze({
      setCollapsed(value) {
        target.hidden = Boolean(value);
        control.setAttribute("aria-expanded", String(!value));
        control.setAttribute("aria-controls", target.id);
      },
    });
  }
  function ProgressSteps(message, job, now = Date.now()) {
    const text = document.createElement("span");
    text.className = "gv-progress";
    text.dataset.running = String(job.status === "running");
    // 阶段信息只展示后台原文；没有结构化总步数时不编造分母或百分比。
    text.textContent =
      message || (job.status === "running" ? "正在处理项目" : "就绪");
    if (job.status === "running" && job.started_at)
      text.textContent +=
        " · 已用 " +
        Math.max(0, Math.floor(now / 1000 - job.started_at)) +
        " 秒";
    return text;
  }
  window.GVUI = Object.freeze({
    HealthLabel,
    Icon,
    StatusBadge,
    Button,
    Card,
    MetricCard,
    CodeText,
    EmptyState,
    ProgressSteps,
    FloatingPanel,
    SplitPane,
    Toast,
  });
})();
