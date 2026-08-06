const state = {
  currentRunId: null,
  running: false,
  progressCard: null,
  health: null,
  runs: [],
  outbox: [],
  subscriptions: [],
  sources: [],
  evaluation: null,
  memory: null,
  outboxFilters: { query: "", status: "all", sort: "created_desc", expanded: false },
  runFilters: { query: "", status: "all", sort: "started_desc", expanded: false },
  actionModeTouched: false,
  theme: "light",
};

const depthProfiles = {
  quick: { pages: 1, results: 5 },
  standard: { pages: 3, results: 8 },
  deep: { pages: 5, results: 15 },
};

const pipelineStages = [
  { key: "intent", label: "意图解析", detail: "时间、区域、主题" },
  { key: "collect", label: "数据采集", detail: "公开源、登录源、扩展检索" },
  { key: "evidence", label: "去重清洗", detail: "清洗、去重、证据校验" },
  { key: "report", label: "生成报告", detail: "Word 与 outbox" },
];

const collapsedLimits = {
  outbox: 6,
  runs: 8,
};

const el = {
  apiStatus: document.querySelector("#apiStatus"),
  apiStatusText: document.querySelector("#apiStatusText"),
  footerStatusDot: document.querySelector("#footerStatusDot"),
  footerStatusText: document.querySelector("#footerStatusText"),
  footerTimezoneText: document.querySelector("#footerTimezoneText"),
  notificationButton: document.querySelector("#notificationButton"),
  notificationBadge: document.querySelector("#notificationBadge"),
  notificationMenu: document.querySelector("#notificationMenu"),
  notificationList: document.querySelector("#notificationList"),
  refreshNotificationsButton: document.querySelector("#refreshNotificationsButton"),
  themeToggleButton: document.querySelector("#themeToggleButton"),
  helpButton: document.querySelector("#helpButton"),
  helpPanel: document.querySelector("#helpPanel"),
  helpPanelContent: document.querySelector("#helpPanelContent"),
  userMenuButton: document.querySelector("#userMenuButton"),
  userLabel: document.querySelector("#userLabel"),
  userMenu: document.querySelector("#userMenu"),
  userMenuContent: document.querySelector("#userMenuContent"),
  form: document.querySelector("#runForm"),
  queryInput: document.querySelector("#queryInput"),
  chatStream: document.querySelector("#chatStream"),
  smartStartPanel: document.querySelector("#smartStartPanel"),
  smartStartMeta: document.querySelector("#smartStartMeta"),
  smartLatestReport: document.querySelector("#smartLatestReport"),
  smartRecommendation: document.querySelector("#smartRecommendation"),
  intentPreview: document.querySelector("#intentPreview"),
  searchDepthSelect: document.querySelector("#searchDepthSelect"),
  scheduleFrequency: document.querySelector("#scheduleFrequency"),
  scheduleTime: document.querySelector("#scheduleTime"),
  subscriptionControls: document.querySelector("#subscriptionControls"),
  maxPagesInput: document.querySelector("#maxPagesInput"),
  maxResultsInput: document.querySelector("#maxResultsInput"),
  runButton: document.querySelector("#runButton"),
  subscribeButton: document.querySelector("#subscribeButton"),
  runStatusBadge: document.querySelector("#runStatusBadge"),
  runIdValue: document.querySelector("#runIdValue"),
  noticeCountValue: document.querySelector("#noticeCountValue"),
  traceCountValue: document.querySelector("#traceCountValue"),
  evidencePassedValue: document.querySelector("#evidencePassedValue"),
  evidenceWarningsValue: document.querySelector("#evidenceWarningsValue"),
  attachmentsExtractedValue: document.querySelector("#attachmentsExtractedValue"),
  latestDownload: document.querySelector("#latestDownload"),
  memoryDigest: document.querySelector("#memoryDigest"),
  traceTimeline: document.querySelector("#traceTimeline"),
  checkpointList: document.querySelector("#checkpointList"),
  checkpointCount: document.querySelector("#checkpointCount"),
  refreshTraceButton: document.querySelector("#refreshTraceButton"),
  refreshOutboxButton: document.querySelector("#refreshOutboxButton"),
  refreshSourcesButton: document.querySelector("#refreshSourcesButton"),
  refreshRunsButton: document.querySelector("#refreshRunsButton"),
  refreshEvaluationButton: document.querySelector("#refreshEvaluationButton"),
  subscriptionPageBody: document.querySelector("#subscriptionPageBody"),
  runHistoryBody: document.querySelector("#runHistoryBody"),
  runSearchInput: document.querySelector("#runSearchInput"),
  runStatusFilter: document.querySelector("#runStatusFilter"),
  runSortSelect: document.querySelector("#runSortSelect"),
  toggleRunsButton: document.querySelector("#toggleRunsButton"),
  clearRunFiltersButton: document.querySelector("#clearRunFiltersButton"),
  runListHint: document.querySelector("#runListHint"),
  sourceList: document.querySelector("#sourceList"),
  sourcePageList: document.querySelector("#sourcePageList"),
  evaluationSummary: document.querySelector("#evaluationSummary"),
  ragMetrics: document.querySelector("#ragMetrics"),
  agentMetrics: document.querySelector("#agentMetrics"),
  harnessMetrics: document.querySelector("#harnessMetrics"),
  recallMetrics: document.querySelector("#recallMetrics"),
  evaluationCases: document.querySelector("#evaluationCases"),
  evaluationNotes: document.querySelector("#evaluationNotes"),
  refreshMemoryButton: document.querySelector("#refreshMemoryButton"),
  saveMemoryButton: document.querySelector("#saveMemoryButton"),
  memorySummary: document.querySelector("#memorySummary"),
  memoryUsageMetrics: document.querySelector("#memoryUsageMetrics"),
  memoryReportMetrics: document.querySelector("#memoryReportMetrics"),
  memorySubscriptionMetrics: document.querySelector("#memorySubscriptionMetrics"),
  memoryDailyMetrics: document.querySelector("#memoryDailyMetrics"),
  memoryProfile: document.querySelector("#memoryProfile"),
  memoryGeneratedAdvice: document.querySelector("#memoryGeneratedAdvice"),
  memoryQueries: document.querySelector("#memoryQueries"),
  memorySuggestions: document.querySelector("#memorySuggestions"),
  memoryEvents: document.querySelector("#memoryEvents"),
  memoryAnalysis: document.querySelector("#memoryAnalysis"),
  settingsSummary: document.querySelector("#settingsSummary"),
  toast: document.querySelector("#toast"),
};

const steps = {
  intent: document.querySelector("#stepIntent"),
  collect: document.querySelector("#stepCollect"),
  evidence: document.querySelector("#stepEvidence"),
  report: document.querySelector("#stepReport"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(readApiError(text) || `HTTP ${response.status}`);
  }
  return response.json();
}

function trackActivity(eventType, detail = {}) {
  const payload = JSON.stringify({
    event_type: eventType,
    target: detail.target || "",
    label: detail.label || "",
    metadata: detail.metadata || {},
    user_id: el.userLabel?.textContent?.trim() || "admin",
  });
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: "application/json" });
    navigator.sendBeacon("/api/memory/events", blob);
    return;
  }
  fetch("/api/memory/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

function trackClick(event) {
  if (!(event.target instanceof Element)) return;
  const target = event.target.closest("button, a");
  if (!target) return;
  const href = target.getAttribute("href") || "";
  const action =
    target.dataset.view ||
    target.dataset.popoverView ||
    target.dataset.runId ||
    target.dataset.subscriptionId ||
    target.id ||
    href ||
    target.className ||
    "unknown";
  trackActivity("click", {
    target: String(action).slice(0, 120),
    label: target.textContent.trim().slice(0, 120),
    metadata: {
      view: activeViewId(),
      href,
      button_id: target.id || "",
    },
  });
  if (href.startsWith("/api/outbox/")) {
    trackActivity("download", {
      target: "outbox",
      label: decodeURIComponent(href.split("/").pop() || ""),
      metadata: {
        view: activeViewId(),
        href,
      },
    });
  }
}

function activeViewId() {
  return document.querySelector(".view.active")?.id || "workbenchView";
}

function readApiError(text) {
  try {
    const payload = JSON.parse(text);
    return payload.detail || text;
  } catch {
    return text;
  }
}

function statusLabel(status) {
  const labels = {
    muted: "未运行",
    queued: "排队中",
    running: "运行中",
    finished: "已完成",
    failed: "失败",
    ready: "就绪",
    active: "启用",
    deleted: "已删除",
    configured: "正常",
    login_required: "需登录",
    pass: "通过",
    warn: "提醒",
    skipped: "跳过",
    click: "点击",
    download: "下载",
    run_start: "启动运行",
    run_delete: "删除运行",
    subscription_create: "创建订阅",
    subscription_run: "触发订阅",
    subscription_delete: "删除订阅",
    outbox_delete: "删除文件",
    weekly_report_view: "查看周报",
    quick_example: "示例输入",
  };
  return labels[status] || status || labels.muted;
}

function setApiStatus(ok, text) {
  if (el.apiStatus) el.apiStatus.className = `status-dot ${ok ? "status-ok" : "status-error"}`;
  if (el.apiStatusText) el.apiStatusText.textContent = text;
  if (el.footerStatusDot) el.footerStatusDot.className = `status-dot ${ok ? "status-ok" : "status-error"}`;
  if (el.footerStatusText) el.footerStatusText.textContent = ok ? "正常" : "连接失败";
}

function applyTheme(theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  document.body.classList.toggle("theme-dark", state.theme === "dark");
  try {
    window.localStorage.setItem("tendertrace.theme", state.theme);
  } catch {
    // localStorage may be unavailable in restricted browser contexts.
  }
  if (el.themeToggleButton) {
    const dark = state.theme === "dark";
    el.themeToggleButton.setAttribute("aria-pressed", String(dark));
    el.themeToggleButton.title = dark ? "浅色模式" : "深色模式";
    el.themeToggleButton.setAttribute("aria-label", dark ? "浅色模式" : "深色模式");
  }
}

function loadTheme() {
  try {
    return window.localStorage.getItem("tendertrace.theme") || "light";
  } catch {
    return "light";
  }
}

function togglePopover(name) {
  const target = popoverByName(name);
  if (!target) return;
  const shouldOpen = target.hidden;
  closePopovers();
  if (shouldOpen) {
    target.hidden = false;
    setPopoverExpanded(name, true);
    if (name === "notifications") renderNotifications();
    if (name === "help") renderHelpPanel();
    if (name === "user") renderUserMenu();
  }
}

function closePopovers() {
  for (const name of ["notifications", "help", "user"]) {
    const node = popoverByName(name);
    if (node) node.hidden = true;
    setPopoverExpanded(name, false);
  }
}

function popoverByName(name) {
  return {
    notifications: el.notificationMenu,
    help: el.helpPanel,
    user: el.userMenu,
  }[name];
}

function setPopoverExpanded(name, expanded) {
  const button = {
    notifications: el.notificationButton,
    help: el.helpButton,
    user: el.userMenuButton,
  }[name];
  if (button) button.setAttribute("aria-expanded", String(expanded));
}

function setRunStatus(status) {
  if (!el.runStatusBadge) return;
  el.runStatusBadge.textContent = statusLabel(status);
  el.runStatusBadge.className = `badge badge-${status || "muted"}`;
}

function setRunning(isRunning) {
  state.running = isRunning;
  document.body.classList.toggle("is-running", isRunning);
  if (el.runButton) {
    el.runButton.disabled = isRunning;
    el.runButton.innerHTML = isRunning
      ? '<span class="button-spinner" aria-hidden="true"></span>运行中'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>开始运行';
  }
  if (el.subscribeButton) el.subscribeButton.disabled = isRunning;
  if (!isRunning) syncActionMode();
  if (isRunning) {
    setRunStatus("running");
    markPipeline([]);
  }
}

function showView(viewId) {
  window.scrollTo(0, 0);
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === viewId);
  });
  if (viewId === "historyView") refreshRuns().catch(toastError("历史运行加载失败"));
  if (viewId === "subscriptionsView") refreshSubscriptions().catch(toastError("订阅加载失败"));
  if (viewId === "sourcesView") refreshSourcesPanel().catch(toastError("数据源加载失败"));
  if (viewId === "evaluationView") refreshEvaluation().catch(toastError("评测加载失败"));
  if (viewId === "memoryView") {
    trackActivity("weekly_report_view", { target: "memoryView", label: "用户记忆" });
    refreshMemoryWeekly().catch(toastError("用户记忆加载失败"));
  }
  if (viewId === "settingsView") refreshSettings().catch(toastError("设置加载失败"));
}

function appendMessage(role, html, extraClass = "") {
  const article = document.createElement("article");
  article.className = `message message-${role}${extraClass ? ` ${extraClass}` : ""}`;
  article.innerHTML =
    role === "user"
      ? `<div class="bubble">${html}</div><span class="avatar">我</span>`
      : `<span class="avatar bot-avatar">TT</span><div class="bubble">${html}</div>`;
  el.chatStream?.append(article);
  if (el.chatStream) el.chatStream.scrollTop = el.chatStream.scrollHeight;
  return article;
}

function appendProgressCard(query) {
  const article = appendMessage(
    "assistant",
    `<div class="progress-card" aria-live="polite">
      <div class="progress-card-head">
        <div>
          <strong>正在处理任务</strong>
          <p>${escapeHtml(query)}</p>
        </div>
        <span class="badge badge-running">排队中</span>
      </div>
      <div class="progress-stage-list"></div>
      <div class="progress-lines"></div>
    </div>`,
    "message-progress",
  );
  state.progressCard = article.querySelector(".progress-card");
  updateProgressCard([], { status: "queued", stats: {} });
}

function updateProgressCard(checkpoints, run) {
  if (!state.progressCard) return;
  const nodes = new Set((checkpoints || []).map((checkpoint) => checkpoint.node));
  const status = run?.status || "running";
  const activeKey = activeStageKey(nodes, status === "finished", status === "failed");
  const badge = state.progressCard.querySelector(".badge");
  badge.textContent = statusLabel(status);
  badge.className = `badge badge-${status}`;
  state.progressCard.querySelector(".progress-stage-list").innerHTML = pipelineStages
    .map((stage) => {
      const done = status === "finished" || nodes.has(stage.key);
      const active = activeKey === stage.key;
      const className = done ? "done" : active ? "active" : "pending";
      const label = done ? "已完成" : active ? "进行中" : "等待";
      return `
        <div class="progress-stage ${className}">
          <span class="progress-check"></span>
          <strong>${escapeHtml(stage.label)}</strong>
          <small>${escapeHtml(label)}</small>
        </div>
      `;
    })
    .join("");
  state.progressCard.querySelector(".progress-lines").innerHTML = progressLines(checkpoints || [], run)
    .map(
      (line) => `
        <div class="progress-line ${line.status}">
          <span></span>
          <strong>${escapeHtml(line.title)}</strong>
          <em>${escapeHtml(line.detail)}</em>
        </div>
      `,
    )
    .join("");
}

function activeStageKey(nodes, finished, failed) {
  if (finished || failed) return "";
  return pipelineStages.find((stage) => !nodes.has(stage.key))?.key || "report";
}

function progressLines(checkpoints, run) {
  const nodes = new Set(checkpoints.map((checkpoint) => checkpoint.node));
  const stats = run?.stats || {};
  const lines = [
    {
      title: "意图解析",
      detail: nodes.has("intent") ? "已生成 BidQL 检索条件" : "正在识别时间、区域、主题和计划",
      status: nodes.has("intent") ? "done" : "active",
    },
    {
      title: "多源采集",
      detail: sourceStatsText(stats),
      status: nodes.has("collect") ? "done" : nodes.has("intent") ? "active" : "pending",
    },
    {
      title: "地域范围",
      detail: regionScopeText(stats) || "保持用户指定地域范围",
      status: stats.region_scope?.status === "relaxed_city" ? "warn" : nodes.has("collect") ? "done" : "pending",
    },
    {
      title: "内容质检",
      detail: nodes.has("evidence")
        ? `证据通过 ${stats.evidence_passed ?? 0} 条，附件正文 ${stats.attachments_extracted ?? 0} 条`
        : "等待清洗、去重和证据校验",
      status: nodes.has("evidence") ? "done" : nodes.has("collect") ? "active" : "pending",
    },
    {
      title: "生成报告",
      detail: nodes.has("report") ? "Word 已生成并写入 outbox" : "等待写入 Word 文件",
      status: nodes.has("report") ? "done" : nodes.has("evidence") ? "active" : "pending",
    },
  ];
  if (run?.status === "failed") {
    lines.push({
      title: "运行失败",
      detail: run.error || "请查看事件流定位失败节点",
      status: "failed",
    });
  }
  return lines;
}

function showToast(message) {
  if (!el.toast) return;
  el.toast.textContent = message;
  el.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    el.toast.hidden = true;
  }, 3600);
}

function toastError(prefix) {
  return (error) => showToast(`${prefix}：${error.message}`);
}

function markPipeline(nodes) {
  Object.values(steps).forEach((node) => node?.classList.remove("done", "active"));
  const seen = new Set(nodes);
  if (seen.has("intent")) steps.intent?.classList.add("done");
  if (seen.has("collect")) steps.collect?.classList.add("done");
  if (seen.has("evidence")) steps.evidence?.classList.add("done");
  if (seen.has("report")) steps.report?.classList.add("done");
  if (!seen.has("intent")) steps.intent?.classList.add("active");
  else if (!seen.has("collect")) steps.collect?.classList.add("active");
  else if (!seen.has("evidence")) steps.evidence?.classList.add("active");
  else if (!seen.has("report")) steps.report?.classList.add("active");
}

function renderStats(stats = {}) {
  setText(el.noticeCountValue, stats.notice_count ?? 0);
  setText(el.traceCountValue, stats.trace_events ?? 0);
  setText(el.evidencePassedValue, stats.evidence_passed ?? 0);
  setText(el.evidenceWarningsValue, stats.evidence_warnings ?? 0);
  setText(el.attachmentsExtractedValue, stats.attachments_extracted ?? 0);
}

function renderLatestDownload(item) {
  if (!el.latestDownload) return;
  if (!item) {
    el.latestDownload.hidden = false;
    el.latestDownload.className = "download-strip empty-download";
    el.latestDownload.innerHTML = `
      <div>
        <strong>暂无可下载报告</strong>
        <span>完成一次运行后会同步到这里</span>
      </div>
    `;
    return;
  }
  const rawName = item.name || fileName(item.outbox_path || "");
  const name = escapeHtml(rawName);
  const runId = item.run_id ? escapeHtml(item.run_id) : "";
  const createdAt = escapeHtml(item.created_at || "刚刚生成");
  const size = item.size ? ` · ${escapeHtml(formatBytes(item.size))}` : "";
  const downloadUrl = item.download_url || `/api/outbox/${encodeURIComponent(rawName)}`;
  el.latestDownload.hidden = false;
  el.latestDownload.className = "download-strip";
  el.latestDownload.innerHTML = `
    <div class="download-main">
      <strong title="${name}">${name}</strong>
      <span>${createdAt}${size}${runId ? ` · Run ${runId}` : ""}</span>
    </div>
    <div class="action-group">
      <a class="link-button" href="${escapeHtml(downloadUrl)}" data-download-outbox-name="${name}">下载</a>
      ${runId ? `<button class="ghost-button" type="button" data-run-id="${runId}">追踪</button>` : ""}
      <button class="danger-button" type="button" data-delete-outbox-name="${name}">删除</button>
    </div>
  `;
}

function renderRunSummary(result) {
  const run = normalizeRunDetail(result);
  state.currentRunId = run.run_id;
  setText(el.runIdValue, run.run_id || "-");
  renderStats({ ...run.stats, notice_count: run.notice_count, trace_events: run.trace_events });
  setRunStatus(run.status || "muted");
  if (!run.outbox_path) return;
  const name = fileName(run.outbox_path);
  renderLatestDownload({
    name,
    download_url: `/api/outbox/${encodeURIComponent(name)}`,
    run_id: run.run_id,
    created_at: "刚刚生成",
  });
}

function renderTimeline(events) {
  if (!el.traceTimeline) return;
  if (!events.length) {
    el.traceTimeline.className = "timeline empty-state";
    el.traceTimeline.textContent = "暂无事件";
    return;
  }
  el.traceTimeline.className = "timeline";
  el.traceTimeline.innerHTML = events
    .map(
      (event) => `
        <div class="timeline-row">
          <strong>${event.seq}. ${escapeHtml(event.event_type)}${event.node ? ` · ${escapeHtml(event.node)}` : ""}</strong>
          <span>${escapeHtml(formatPayload(event.payload))}</span>
          <span>${escapeHtml(event.created_at || "")}</span>
        </div>
      `,
    )
    .join("");
}

function renderCheckpoints(checkpoints) {
  setText(el.checkpointCount, checkpoints.length);
  if (!el.checkpointList) {
    markPipeline(checkpoints.map((checkpoint) => checkpoint.node));
    return;
  }
  if (!checkpoints.length) {
    el.checkpointList.className = "checkpoint-list empty-state";
    el.checkpointList.textContent = "暂无检查点";
    markPipeline([]);
    return;
  }
  el.checkpointList.className = "checkpoint-list";
  el.checkpointList.innerHTML = checkpoints
    .map(
      (checkpoint) => `
        <div class="checkpoint-row">
          <strong>${checkpoint.seq}. ${escapeHtml(stageLabel(checkpoint.node))}</strong>
          <span>${escapeHtml(statusLabel(checkpoint.status))}</span>
        </div>
      `,
    )
    .join("");
  markPipeline(checkpoints.map((checkpoint) => checkpoint.node));
}

function renderOutbox(items) {
  renderLatestDownload(items[0]);
  renderSmartStart();
}

function renderSubscriptions(items) {
  renderSubscriptionTable(el.subscriptionPageBody, items);
}

function filterOutboxItems(items) {
  const query = normalizeSearch(state.outboxFilters.query);
  const status = state.outboxFilters.status;
  return [...items]
    .filter((item) => {
      if (status !== "all" && item.status !== status) return false;
      if (!query) return true;
      return normalizeSearch(
        [
          item.name,
          item.run_id,
          item.subscription_id,
          item.status,
          statusLabel(item.status),
          item.created_at,
        ].join(" "),
      ).includes(query);
    })
    .sort((left, right) => compareOutbox(left, right, state.outboxFilters.sort));
}

function compareOutbox(left, right, sort) {
  if (sort === "created_asc") return dateValue(left.created_at) - dateValue(right.created_at);
  if (sort === "name_asc") return String(left.name || "").localeCompare(String(right.name || ""));
  if (sort === "size_desc") return Number(right.size || 0) - Number(left.size || 0);
  return dateValue(right.created_at) - dateValue(left.created_at);
}

function filterRunItems(items) {
  const query = normalizeSearch(state.runFilters.query);
  const status = state.runFilters.status;
  return [...items]
    .filter((item) => {
      if (status !== "all" && item.status !== status) return false;
      if (!query) return true;
      return normalizeSearch(
        [
          item.id,
          item.original_query,
          item.status,
          statusLabel(item.status),
          item.started_at,
          item.finished_at,
          item.stats?.notice_count,
          item.stats?.trace_events,
        ].join(" "),
      ).includes(query);
    })
    .sort((left, right) => compareRun(left, right, state.runFilters.sort));
}

function compareRun(left, right, sort) {
  if (sort === "started_asc") return dateValue(left.started_at) - dateValue(right.started_at);
  if (sort === "notice_desc") {
    return Number(right.stats?.notice_count || 0) - Number(left.stats?.notice_count || 0);
  }
  if (sort === "status_asc") return String(left.status || "").localeCompare(String(right.status || ""));
  return dateValue(right.started_at) - dateValue(left.started_at);
}

function visibleListItems(items, expanded, limit) {
  return expanded ? items : items.slice(0, limit);
}

function updateListHint(target, total, matched, shown, unit, expanded) {
  if (!target) return;
  const filteredText = matched === total ? "" : `，筛选命中 ${matched}`;
  const modeText = expanded ? "已展开" : "已折叠";
  target.textContent = `${modeText}展示 ${shown} / ${total} ${unit}${filteredText}`;
}

function normalizeSearch(value) {
  return String(value ?? "").trim().toLowerCase();
}

function dateValue(value) {
  const parsed = Date.parse(String(value || "").replace(" ", "T"));
  return Number.isFinite(parsed) ? parsed : 0;
}

function shortIdentifier(value) {
  const text = String(value || "");
  return text.length > 10 ? `${text.slice(0, 8)}...` : text;
}

function renderSubscriptionTable(target, items) {
  if (!target) return;
  if (target.classList.contains("data-list")) {
    renderSubscriptionCards(target, items);
    return;
  }
  if (!items.length) {
    target.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无订阅任务</td></tr>';
    return;
  }
  target.innerHTML = items
    .map((item) => {
      const query = escapeHtml(item.original_query);
      const title = escapeHtml(subscriptionTitle(item));
      const schedule = escapeHtml(scheduleText(item));
      const lastRun = escapeHtml(subscriptionLastRunText(item));
      const nextRun = escapeHtml(subscriptionNextRunText(item));
      const increment = escapeHtml(subscriptionIncrementText(item));
      const email = escapeHtml(subscriptionEmailText(item));
      const download = subscriptionLatestDownloadHtml(item);
      return `
        <tr>
          <td class="file-cell"><span class="file-name" title="${title}">${title}</span></td>
          <td class="file-cell"><span class="file-name" title="${query}">${query}</span></td>
          <td>${schedule}</td>
          <td>
            <span class="badge badge-${escapeHtml(item.status || "muted")}">${escapeHtml(statusLabel(item.status))}</span>
            <span class="table-subvalue">${email}</span>
          </td>
          <td>
            <span class="table-main-value">${lastRun}</span>
            <span class="table-subvalue">${nextRun}</span>
            ${download}
          </td>
          <td>
            <span class="table-main-value">${increment}</span>
          </td>
          <td>
            <div class="action-group">
              <button class="ghost-button" type="button" data-subscription-id="${escapeHtml(item.id)}">运行</button>
              <button class="danger-button" type="button" data-delete-subscription-id="${escapeHtml(item.id)}">删除</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderSubscriptionCards(target, items) {
  if (!items.length) {
    target.innerHTML = '<div class="empty-cell">暂无订阅任务</div>';
    return;
  }
  const rows = items
    .map((item) => {
      const query = escapeHtml(item.original_query);
      const title = escapeHtml(subscriptionTitle(item));
      const schedule = escapeHtml(scheduleText(item));
      const status = escapeHtml(item.status || "muted");
      const lastRun = escapeHtml(subscriptionLastRunText(item));
      const nextRun = escapeHtml(subscriptionNextRunText(item));
      const increment = escapeHtml(subscriptionIncrementText(item));
      const email = escapeHtml(subscriptionEmailText(item));
      const download = subscriptionLatestDownloadHtml(item);
      return `
        <article class="data-row subscription-row" role="row">
          <div class="compact-cell compact-main" role="cell" data-label="订阅">
            <span class="cell-label">订阅</span>
            <div class="cell-value">
              <strong title="${title}">${title}</strong>
              <span class="compact-subvalue" title="${query}">
                <span class="subvalue-label">查询</span>
                <span>${query}</span>
              </span>
            </div>
          </div>
          <div class="compact-cell" role="cell" data-label="计划">
            <span class="cell-label">计划</span>
            <span class="cell-value">${schedule}</span>
          </div>
          <div class="compact-cell" role="cell" data-label="状态">
            <span class="cell-label">状态</span>
            <span class="cell-value">
              <span class="badge badge-${status}">${escapeHtml(statusLabel(item.status))}</span>
              <span class="compact-subvalue compact-note">${email}</span>
            </span>
          </div>
          <div class="compact-cell" role="cell" data-label="最近运行">
            <span class="cell-label">最近运行</span>
            <span class="cell-value">
              <span>${lastRun}</span>
              <span class="compact-subvalue compact-note">${nextRun}</span>
              ${download}
            </span>
          </div>
          <div class="compact-cell" role="cell" data-label="增量">
            <span class="cell-label">增量</span>
            <span class="cell-value">${increment}</span>
          </div>
          <div class="compact-cell compact-actions" role="cell" data-label="操作">
            <span class="cell-label">操作</span>
            <span class="cell-value action-value">
            <button class="ghost-button" type="button" data-subscription-id="${escapeHtml(item.id)}">运行</button>
            <button class="danger-button" type="button" data-delete-subscription-id="${escapeHtml(item.id)}">删除</button>
            </span>
          </div>
        </article>
      `;
    })
    .join("");
  target.innerHTML = `
    <div class="compact-table subscription-table" role="table" aria-label="我的订阅">
      <div class="compact-table-head" role="row">
        <span role="columnheader">订阅</span>
        <span role="columnheader">计划</span>
        <span role="columnheader">状态</span>
        <span role="columnheader">最近运行</span>
        <span role="columnheader">增量</span>
        <span role="columnheader">操作</span>
      </div>
      ${rows}
    </div>
  `;
}

function renderSources(items) {
  renderSourceList(el.sourceList, items);
  renderSourceList(el.sourcePageList, items);
}

function renderSourceList(target, items) {
  if (!target) return;
  if (!items.length) {
    target.className = "source-list empty-state";
    target.textContent = "暂无来源";
    return;
  }
  target.className = "source-list source-grid";
  target.innerHTML = items
    .map((item) => {
      const site = escapeHtml(item.site || "-");
      const engine = escapeHtml(item.engine || "-");
      const status = escapeHtml(item.status || "muted");
      const health = item.health || {};
      const rules = item.discovery_rules || {};
      const routes = Array.isArray(item.routes) ? item.routes : [];
      const validation = item.validation ? `<span>validation: ${escapeHtml(item.validation)}</span>` : "";
      const counts =
        item.cookie_count || item.origin_count
          ? `<span>cookies/origins: ${escapeHtml(item.cookie_count || 0)} / ${escapeHtml(item.origin_count || 0)}</span>`
          : "";
      const detail = item.detail ? `<span>${escapeHtml(item.detail)}</span>` : "";
      const allowRules = Array.isArray(rules.allow) ? rules.allow.slice(0, 2).join(" | ") : "";
      const denyRules = Array.isArray(rules.deny) ? rules.deny.slice(0, 2).join(" | ") : "";
      const routeSummary = routes.length
        ? routes.map((route) => `${route.kind || "route"}:${route.method || "GET"}`).join(" / ")
        : "未配置路由";
      const successRate =
        health.success_rate === null || health.success_rate === undefined ? "-" : percent(health.success_rate);
      return `
        <div class="source-row source-health-card">
          <div class="source-row-head">
            <strong>${site} · ${engine}</strong>
            <span><span class="badge badge-${status}">${escapeHtml(statusLabel(item.status))}</span></span>
          </div>
          <div class="source-health-grid">
            <span><strong>${escapeHtml(health.runs ?? 0)}</strong><small>近次运行</small></span>
            <span><strong>${escapeHtml(health.notices ?? 0)}</strong><small>累计命中</small></span>
            <span><strong>${escapeHtml(successRate)}</strong><small>成功率</small></span>
            <span><strong>${escapeHtml(health.blocked ?? 0)}</strong><small>阻断</small></span>
            <span><strong>${escapeHtml(health.retries ?? 0)}</strong><small>重试</small></span>
            <span><strong>${escapeHtml(health.page_artifacts ?? 0)}</strong><small>页面快照</small></span>
          </div>
          <span class="source-route-line">入口：${escapeHtml(routeSummary)}</span>
          <span class="source-rule-line">发现规则：allow ${escapeHtml(allowRules || "-")}；deny ${escapeHtml(denyRules || "-")}</span>
          ${validation}
          ${counts}
          ${detail}
          ${health.last_error ? `<span class="source-error-line">最近错误：${escapeHtml(health.last_error)}</span>` : ""}
        </div>
      `;
    })
    .join("");
}

function renderRuns(items) {
  if (!el.runHistoryBody) return;
  const filtered = filterRunItems(items);
  const visible = visibleListItems(filtered, state.runFilters.expanded, collapsedLimits.runs);
  updateListHint(
    el.runListHint,
    items.length,
    filtered.length,
    visible.length,
    "条运行",
    state.runFilters.expanded,
  );
  if (el.toggleRunsButton) {
    el.toggleRunsButton.hidden = filtered.length <= collapsedLimits.runs;
    el.toggleRunsButton.textContent = state.runFilters.expanded ? "收起" : "展开全部";
  }
  if (!filtered.length) {
    el.runHistoryBody.innerHTML = '<tr><td colspan="6" class="empty-cell">没有匹配的运行记录</td></tr>';
    return;
  }
  el.runHistoryBody.innerHTML = visible
    .map((item) => {
      const id = escapeHtml(item.id);
      const query = escapeHtml(item.original_query || "-");
      const stats = item.stats || {};
      const outboxName = item.outbox_path ? fileName(item.outbox_path) : "";
      return `
        <tr>
          <td class="file-cell"><span class="file-name" title="${query}">${query}</span></td>
          <td><span class="badge badge-${escapeHtml(item.status || "muted")}">${escapeHtml(statusLabel(item.status))}</span></td>
          <td>${escapeHtml(stats.notice_count ?? 0)}</td>
          <td>${escapeHtml(stats.trace_events ?? 0)}</td>
          <td>${escapeHtml(item.started_at || "-")}</td>
          <td>
            <div class="action-group">
              <button class="ghost-button" type="button" data-run-id="${id}">追踪</button>
              ${
                outboxName
                  ? `<a class="link-button" href="/api/outbox/${encodeURIComponent(outboxName)}" data-download-outbox-name="${escapeHtml(outboxName)}">下载</a>`
                  : ""
              }
              <button class="danger-button" type="button" data-delete-run-id="${id}">删除记录</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderNotifications() {
  const issues = notificationIssues();
  const activities = notificationActivities();
  if (el.notificationBadge) {
    const count = issues.length;
    el.notificationBadge.hidden = count === 0;
    el.notificationBadge.textContent = count > 99 ? "99+" : String(count);
  }
  if (!el.notificationList) return;
  const rows = [
    ...issues.map((item) => notificationRow(item, true)),
    ...activities.map((item) => notificationRow(item, false)),
  ];
  el.notificationList.className = rows.length ? "popover-list" : "popover-list empty-state";
  el.notificationList.innerHTML = rows.length ? rows.join("") : "当前没有待处理提醒";
}

function notificationIssues() {
  const failedRuns = state.runs.filter((item) => item.status === "failed");
  const runningRuns = state.runs.filter((item) => item.status === "running" || item.status === "queued");
  const sourceIssues = state.sources.filter((item) => !["configured", "ready", "active"].includes(item.status));
  const issues = [];
  if (failedRuns.length) {
    issues.push({
      title: `${failedRuns.length} 个运行失败`,
      detail: failedRuns[0].original_query || failedRuns[0].id,
      view: "historyView",
    });
  }
  if (runningRuns.length) {
    issues.push({
      title: `${runningRuns.length} 个任务仍在运行`,
      detail: runningRuns[0].original_query || runningRuns[0].id,
      view: "historyView",
    });
  }
  if (sourceIssues.length) {
    issues.push({
      title: `${sourceIssues.length} 个数据源需要处理`,
      detail: sourceIssues.map((item) => item.site || item.engine || item.status).join("、"),
      view: "sourcesView",
    });
  }
  if (state.evaluation?.status === "warn") {
    issues.push({
      title: "Agent 评测有提醒",
      detail: `当前总分 ${percent(state.evaluation.overall_score)}`,
      view: "evaluationView",
    });
  }
  return issues;
}

function notificationActivities() {
  const latestRun = state.runs[0];
  const latestOutbox = state.outbox[0];
  const activities = [];
  if (latestRun) {
    activities.push({
      title: `最近运行：${statusLabel(latestRun.status)}`,
      detail: latestRun.original_query || latestRun.id,
      view: "historyView",
    });
  }
  if (latestOutbox) {
    activities.push({
      title: "最新 Word 报告",
      detail: latestOutbox.name,
      view: "workbenchView",
    });
  }
  if (state.subscriptions.length) {
    activities.push({
      title: `${state.subscriptions.length} 个启用订阅`,
      detail: "增量去重由 sent_history 控制",
      view: "subscriptionsView",
    });
  }
  return activities;
}

function notificationRow(item, issue) {
  return `
    <div class="popover-row">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.detail || "")}</span>
      <div class="action-group">
        <button class="${issue ? "danger-button" : "ghost-button"}" type="button" data-popover-view="${escapeHtml(item.view)}">
          查看
        </button>
      </div>
    </div>
  `;
}

function renderHelpPanel() {
  if (!el.helpPanelContent) return;
  const config = state.health?.config || {};
  el.helpPanelContent.innerHTML = `
    <div class="popover-row">
      <strong>当前服务</strong>
      <span>${escapeHtml(config.host || "-")}:${escapeHtml(config.port || "-")} · ${escapeHtml(config.timezone || "-")}</span>
    </div>
    <div class="popover-row">
      <strong>常用入口</strong>
      <div class="action-group">
        <button class="ghost-button" type="button" data-popover-view="historyView">历史运行</button>
        <button class="ghost-button" type="button" data-popover-view="sourcesView">数据源</button>
        <button class="ghost-button" type="button" data-popover-view="evaluationView">Agent评测</button>
        <button class="ghost-button" type="button" data-popover-view="memoryView">用户记忆</button>
      </div>
    </div>
    <div class="popover-row">
      <strong>交付文档</strong>
      <span>docs/operation/操作文档.md</span>
      <span>docs/teaching/21_导航工作台删除与Agent评测.docx</span>
    </div>
  `;
}

function renderUserMenu() {
  if (!el.userMenuContent) return;
  const config = state.health?.config || {};
  if (el.userLabel) el.userLabel.textContent = "admin";
  el.userMenuContent.innerHTML = `
    <div class="popover-row">
      <strong>admin</strong>
      <span>${escapeHtml(config.app_env || "dev")} · ${escapeHtml(config.model_mode || "-")} · ${escapeHtml(config.scheduler_enabled ? "调度启用" : "调度关闭")}</span>
    </div>
    <div class="popover-row">
      <strong>本地目录</strong>
      <span>Outbox: ${escapeHtml(config.outbox_dir || "-")}</span>
      <span>DB: ${escapeHtml(config.db_path || "-")}</span>
    </div>
    <div class="popover-row">
      <strong>操作</strong>
      <div class="action-group">
        <button class="ghost-button" type="button" data-popover-view="settingsView">设置</button>
        <button class="ghost-button" type="button" data-popover-view="evaluationView">评测</button>
        <button class="ghost-button" type="button" data-popover-view="memoryView">记忆周报</button>
        <button class="ghost-button" type="button" data-refresh-all>刷新全部</button>
      </div>
    </div>
  `;
}

function renderEvaluation(report) {
  if (!report) return;
  if (el.evaluationSummary) {
    el.evaluationSummary.className = "eval-summary";
    el.evaluationSummary.innerHTML = [
      summaryTile("总分", percent(report.overall_score)),
      summaryTile("状态", statusLabel(report.status)),
      summaryTile("运行数", report.summary?.runs ?? 0),
      summaryTile("完成运行", report.summary?.finished_runs ?? 0),
      summaryTile("用例数", report.summary?.evaluated_cases ?? 0),
    ].join("");
  }
  renderMetricCard(el.ragMetrics, "RAG 评测", [
    ["证据通过率", percent(report.rag?.grounding_pass_rate)],
    ["证据检查", `${report.rag?.evidence_passed ?? 0} / ${report.rag?.evidence_checked ?? 0}`],
    ["附件抽取率", percent(report.rag?.attachment_extract_rate)],
    ["报告产出率", percent(report.rag?.report_yield_rate)],
  ]);
  renderMetricCard(el.agentMetrics, "Agent 评测", [
    ["检查点完成率", percent(report.agent?.checkpoint_completion_rate)],
    ["完整节点运行", report.agent?.complete_checkpoint_runs ?? 0],
    ["平均事件数", report.agent?.avg_trace_events ?? 0],
    ["失败率", percent(report.agent?.failure_rate)],
    ["模型审计", report.agent?.model_audit_count ?? 0],
  ]);
  renderMetricCard(el.harnessMetrics, "Harness", [
    ["字段准确率", percent(report.harness?.field_accuracy)],
    ["用例通过率", percent(report.harness?.case_pass_rate)],
    ["通过用例", `${report.harness?.passed_cases ?? 0} / ${report.harness?.case_count ?? 0}`],
  ]);
  renderMetricCard(el.recallMetrics, "召回覆盖", [
    ["严格 Recall@10", report.recall?.strict_recall_available ? percent(report.recall?.strict_recall_at_10) : "待标注"],
    ["严格 Precision@10", report.recall?.strict_recall_available ? percent(report.recall?.strict_precision_at_10) : "待标注"],
    ["召回代理分", percent(report.recall?.recall_proxy)],
    ["来源覆盖率", percent(report.recall?.source_coverage_rate)],
    ["FTS 覆盖率", percent(report.recall?.fts_coverage_rate)],
    ["本地复用率", percent(report.recall?.local_reuse_rate)],
    ["向量覆盖率", percent(report.recall?.vector_coverage_rate)],
    ["去重保留率", percent(report.recall?.dedup_retention_rate)],
    ["多源命中率", percent(report.recall?.multi_source_rate)],
    ["索引公告", `${report.recall?.fts_indexed_notices ?? 0} / ${report.recall?.indexed_notices ?? 0}`],
    ["金标用例", `${report.recall?.annotated_gold_case_count ?? 0} / ${report.recall?.gold_case_count ?? 0}`],
  ]);
  if (el.evaluationCases) {
    const cases = report.harness?.cases || [];
    el.evaluationCases.className = cases.length ? "case-list" : "case-list empty-state";
    el.evaluationCases.innerHTML = cases.length
      ? cases
          .map(
            (item) => `
              <div class="case-row">
                <strong>${escapeHtml(item.name)} · ${item.passed ? "通过" : "未通过"}</strong>
                <span>${escapeHtml(item.query)}</span>
                <span>字段：${escapeHtml(item.field_passed)} / ${escapeHtml(item.field_total)}</span>
              </div>
            `,
          )
          .join("")
      : "暂无用例";
  }
  if (el.evaluationNotes) {
    const notes = report.notes || [];
    el.evaluationNotes.className = notes.length ? "case-list" : "case-list empty-state";
    el.evaluationNotes.innerHTML = notes.length
      ? notes.map((note) => `<div class="note-row">${escapeHtml(note)}</div>`).join("")
      : "暂无说明";
  }
}

function renderMemory(report) {
  if (!report) return;
  const summary = report.summary || {};
  const period = report.period || {};
  const profile = report.knowledge_profile || {};
  const behavior = profile.behavior || {};
  const queryPatterns = profile.query_patterns || {};
  const recommendationPlan = report.recommendation_plan || [];
  const generatedAdvice = report.generated_advice || {};
  const riskSignals = report.risk_signals || [];
  renderMemoryDigest(report);
  if (el.memorySummary) {
    el.memorySummary.className = "eval-summary";
    el.memorySummary.innerHTML = [
      summaryTile("周期", `${period.from || "-"} 至 ${period.to || "-"}`),
      summaryTile("核心主题", firstCounterName(profile.topics, "暂无")),
      summaryTile("核心区域", firstCounterName(profile.regions, "暂无")),
      summaryTile("下载转化", percent(behavior.download_rate || 0)),
      summaryTile("建议数", recommendationPlan.length),
    ].join("");
  }
  renderMetricCard(el.memoryUsageMetrics, "使用行为", [
    ["总事件", summary.total_events ?? 0],
    ["活跃天数", summary.active_days ?? 0],
    ["点击次数", summary.clicks ?? 0],
    ["查看周报", summary.weekly_reports_viewed ?? 0],
  ]);
  renderMetricCard(el.memoryReportMetrics, "报告转化", [
    ["启动运行", summary.runs_started ?? 0],
    ["完成运行", summary.runs_finished ?? 0],
    ["失败运行", summary.failed_runs ?? 0],
    ["下载转化", percent(behavior.download_rate || 0)],
  ]);
  renderMetricCard(el.memorySubscriptionMetrics, "知识偏好", [
    ["新增订阅", summary.subscriptions_created ?? 0],
    ["重复查询", queryPatterns.repeat_queries?.length ?? 0],
    ["定时意图", queryPatterns.scheduled_intent_count ?? 0],
    ["澄清风险", queryPatterns.clarify_risk_count ?? 0],
  ]);
  renderMetricCard(el.memoryDailyMetrics, "每日节奏", memoryDailyRows(report.daily || []));
  renderMemoryProfile(profile);
  renderGeneratedAdvice(generatedAdvice, recommendationPlan);
  renderMemoryList(
    el.memoryQueries,
    report.top_queries || [],
    (item) => `<div class="case-row"><strong>${escapeHtml(item.query)}</strong><span>${escapeHtml(item.count)} 次</span></div>`,
    "暂无查询",
  );
  renderMemoryList(
    el.memorySuggestions,
    recommendationPlan.length ? recommendationPlan : report.suggestions || [],
    (item) => {
      if (typeof item === "string") return `<div class="note-row">${escapeHtml(item)}</div>`;
      return `
        <div class="case-row recommendation-row">
          <strong>${priorityBadge(item.priority)}${escapeHtml(item.title || "建议")}</strong>
          <span>${escapeHtml(item.reason || "")}</span>
          <span>${escapeHtml(item.action || "")}</span>
        </div>
      `;
    },
    "暂无建议",
  );
  renderMemoryList(
    el.memoryEvents,
    report.recent_events || [],
    (item) => `
      <div class="case-row">
        <strong>${escapeHtml(statusLabel(item.event_type))} · ${escapeHtml(item.target || "-")}</strong>
        <span>${escapeHtml(item.label || "-")}</span>
        <span>${escapeHtml(item.created_at || "")}</span>
      </div>
    `,
    "暂无事件",
  );
  renderMemoryList(
    el.memoryAnalysis,
    [...(report.analysis || []), ...riskSignals.map((item) => `${item.title}：${item.detail}`)],
    (item) => `<div class="note-row">${escapeHtml(item)}</div>`,
    "暂无分析",
  );
  renderSmartStart();
}

function renderSmartStart() {
  if (!el.smartStartPanel) return;
  const query = el.queryInput?.value.trim() || "";
  const mode = checkedValue("actionMode") === "subscribe" ? "订阅模式" : "立即运行";
  const strategy = modelStrategyLabel(checkedValue("modelStrategy") || "config");
  if (el.smartStartMeta) {
    el.smartStartMeta.textContent = query
      ? `${mode} · ${strategy} · 已准备解析当前问题`
      : `${mode} · ${strategy} · 请输入查询问题`;
  }
  const latest = state.outbox[0];
  if (el.smartLatestReport) {
    el.smartLatestReport.textContent = latest
      ? `${latest.name} · ${formatBytes(latest.size)}`
      : "暂无可下载 Word";
  }
  const suggestion =
    state.memory?.generated_advice?.headline ||
    state.memory?.recommendation_plan?.[0]?.action ||
    state.memory?.suggestions?.[0];
  if (el.smartRecommendation) {
    el.smartRecommendation.textContent =
      suggestion || "完成一次查询并下载 Word 后，我会依据你的行为生成下一步建议。";
  }
}

function renderMemoryDigest(report) {
  if (!el.memoryDigest) return;
  const summary = report.summary || {};
  const advice = report.generated_advice || {};
  const plan = report.recommendation_plan || [];
  const profile = report.knowledge_profile || {};
  const topQuery = report.top_queries?.[0]?.query || advice.headline || "暂无高频查询";
  el.memoryDigest.className = "source-list";
  el.memoryDigest.innerHTML = `
    <div class="insight-row">
      <strong>本周 ${escapeHtml(summary.total_events ?? 0)} 次交互</strong>
      <span>${escapeHtml(summary.downloads ?? 0)} 次下载，${escapeHtml(summary.runs_finished ?? 0)} 次完成运行</span>
    </div>
    <div class="insight-row">
      <strong>${escapeHtml(topQuery)}</strong>
      <span>${escapeHtml(plan[0]?.action || advice.summary || "继续积累使用记录，系统会给出更准确的建议。")}</span>
    </div>
    <div class="insight-row">
      <strong>${escapeHtml(firstCounterName(profile.topics, "暂无稳定主题"))}</strong>
      <span>${escapeHtml(firstCounterName(profile.regions, "暂无稳定区域"))}</span>
    </div>
  `;
}

function memoryDailyRows(daily) {
  const active = daily.filter((item) => item.events || item.runs);
  const latest = daily[daily.length - 1] || {};
  const busiest = active.reduce((best, item) => (item.events > (best.events || 0) ? item : best), {});
  return [
    ["今日事件", latest.events ?? 0],
    ["今日运行", latest.runs ?? 0],
    ["最高活跃日", busiest.date || "-"],
    ["最高日事件", busiest.events ?? 0],
  ];
}

function renderMemoryProfile(profile = {}) {
  if (!el.memoryProfile) return;
  const rows = [
    ["主题偏好", counterSummary(profile.topics, "暂无主题偏好")],
    ["区域偏好", counterSummary(profile.regions, "暂无区域偏好")],
    ["定时模式", counterSummary(profile.schedules, "暂无定时偏好")],
    ["来源命中", counterSummary(profile.sources, "暂无来源样本")],
  ];
  el.memoryProfile.className = "case-list profile-list";
  el.memoryProfile.innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="profile-row">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderGeneratedAdvice(advice = {}, plan = []) {
  if (!el.memoryGeneratedAdvice) return;
  const actions = Array.isArray(advice.next_actions) ? advice.next_actions.filter(Boolean) : [];
  const fallbackActions = plan.map((item) => item.action).filter(Boolean).slice(0, 3);
  const nextActions = actions.length ? actions : fallbackActions;
  el.memoryGeneratedAdvice.className = "case-list advice-list";
  el.memoryGeneratedAdvice.innerHTML = `
    <div class="advice-hero">
      <strong>${escapeHtml(advice.headline || "暂无稳定建议")}</strong>
      <span>${escapeHtml(advice.summary || "完成更多查询、下载和订阅后，系统会生成更具体的建议。")}</span>
    </div>
    ${
      nextActions.length
        ? nextActions
            .map(
              (item, index) => `
                <div class="advice-action">
                  <span>${index + 1}</span>
                  <strong>${escapeHtml(item)}</strong>
                </div>
              `,
            )
            .join("")
        : '<div class="note-row">暂无下一步动作</div>'
    }
  `;
}

function firstCounterName(items, fallback) {
  return Array.isArray(items) && items.length ? items[0].name : fallback;
}

function counterSummary(items, fallback) {
  if (!Array.isArray(items) || !items.length) return fallback;
  return items
    .slice(0, 3)
    .map((item) => `${item.name} ${item.count}`)
    .join(" / ");
}

function priorityBadge(priority) {
  const label = { high: "高", medium: "中", low: "低" }[priority] || "低";
  return `<span class="priority-badge priority-${escapeHtml(priority || "low")}">${escapeHtml(label)}</span>`;
}

function renderMemoryList(target, items, renderer, emptyText) {
  if (!target) return;
  target.className = items.length ? "case-list" : "case-list empty-state";
  target.innerHTML = items.length ? items.map(renderer).join("") : emptyText;
}

function renderMetricCard(target, title, rows) {
  if (!target) return;
  target.innerHTML = `
    <h2>${escapeHtml(title)}</h2>
    ${rows
      .map(
        ([label, value]) => `
          <div class="metric-line">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
          </div>
        `,
      )
      .join("")}
  `;
}

function summaryTile(label, value) {
  return `
    <div class="summary-tile">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderSettingsSummary(payload) {
  if (!el.settingsSummary) return;
  const config = payload.config || {};
  el.settingsSummary.className = "settings-grid";
  el.settingsSummary.innerHTML = [
    settingTile("运行环境", config.app_env || "-"),
    settingTile("监听地址", `${config.host || "-"}:${config.port || "-"}`),
    settingTile("时区", config.timezone || "-"),
    settingTile("发送渠道", (config.delivery_channels || []).join(", ") || "-"),
    settingTile("模型模式", config.model_mode || "-"),
    settingTile("模型增强", config.model_enhancement_enabled ? "启用" : "关闭"),
    settingTile("本地模型", config.ollama_model || "-"),
    settingTile("云端模型", `${config.openai_model || "-"} · ${config.openai_key_configured ? "已配置" : "未配置"}`),
    settingTile("调度器", config.scheduler_enabled ? "启用" : "关闭"),
    settingTile("Outbox", config.outbox_dir || "-"),
    settingTile("数据库", config.db_path || "-"),
    settingTile("登录态目录", config.secrets_dir || "-"),
  ].join("");
}

function settingTile(label, value) {
  return `
    <div class="setting-tile">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderIntentPreview(bidql) {
  if (!el.intentPreview) return;
  const region = bidql.region?.city || bidql.region?.province || "未识别区域";
  const topics = bidql.topic?.core?.length ? bidql.topic.core.join(" / ") : "全部主题";
  const time = bidql.time?.resolved_window
    ? `${bidql.time.resolved_window.from} 至 ${bidql.time.resolved_window.to}`
    : bidql.time?.kind || "默认时间";
  const schedule = bidql.schedule?.kind === "immediate" ? "立即执行" : bidql.schedule?.time || bidql.schedule?.kind;
  const clarifications = clarificationQuestions(bidql);
  el.intentPreview.className = `intent-preview${clarifications.length ? " needs-clarification" : ""}`;
  el.intentPreview.innerHTML = `
    <span>区域：${escapeHtml(region)}</span>
    <span>主题：${escapeHtml(topics)}</span>
    <span>时间：${escapeHtml(time)}</span>
    <span>计划：${escapeHtml(schedule)}</span>
    ${
      clarifications.length
        ? `<span class="clarify-chip">需确认：${escapeHtml(clarifications.map((item) => item.question).join("；"))}</span>`
        : ""
    }
  `;
}

function autoSelectActionMode(bidql) {
  if (state.actionModeTouched) return;
  setActionMode(hasScheduledIntent(bidql) ? "subscribe" : "run", { touched: false });
}

function hasScheduledIntent(bidql) {
  const schedule = bidql?.schedule || {};
  return Boolean(schedule.kind && schedule.kind !== "immediate");
}

function clarificationQuestions(bidql) {
  const questions = bidql?.meta?.clarification_questions;
  if (Array.isArray(questions) && questions.length) return questions;
  const fields = bidql?.meta?.clarify_needed;
  if (!Array.isArray(fields)) return [];
  return fields.map((field) => ({
    field,
    question: field === "topic" ? "请确认采购品类关键词" : "请确认地区",
  }));
}

async function ensureIntentReady(query) {
  const bidql = await api("/api/intent/parse", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
  renderIntentPreview(bidql);
  autoSelectActionMode(bidql);
  const clarifications = clarificationQuestions(bidql);
  if (!clarifications.length) return true;
  const message = clarifications.map((item) => item.question).join("；");
  appendMessage("assistant", `我需要先确认一下：${escapeHtml(message)}`);
  showToast(message);
  return false;
}

async function refreshHealth() {
  try {
    const payload = await api("/api/health");
    state.health = payload;
    setApiStatus(true, "已连接");
    if (el.footerTimezoneText) el.footerTimezoneText.textContent = payload.config?.timezone || "-";
    renderHelpPanel();
    renderUserMenu();
    return payload;
  } catch (error) {
    setApiStatus(false, "连接失败");
    showToast(`后端连接失败：${error.message}`);
    return null;
  }
}

async function refreshOutbox() {
  const payload = await api("/api/outbox");
  state.outbox = payload.items || [];
  renderOutbox(state.outbox);
  renderNotifications();
}

async function refreshSubscriptions() {
  const payload = await api("/api/subscriptions");
  state.subscriptions = payload.items || [];
  renderSubscriptions(state.subscriptions);
  renderNotifications();
}

async function refreshSources() {
  const payload = await api("/api/sources");
  state.sources = payload.items || [];
  renderSources(state.sources);
  renderNotifications();
}

async function refreshSourcesPanel() {
  await refreshSources();
}

async function refreshRuns() {
  const payload = await api("/api/runs");
  state.runs = payload.items || [];
  renderRuns(state.runs);
  renderNotifications();
}

async function refreshEvaluation() {
  state.evaluation = await api("/api/evaluations/agent");
  renderEvaluation(state.evaluation);
  renderNotifications();
}

async function refreshMemoryWeekly() {
  state.memory = await api("/api/memory/weekly");
  renderMemory(state.memory);
}

async function saveMemoryWeekly() {
  state.memory = await api("/api/memory/weekly", {
    method: "POST",
    body: JSON.stringify({ days: 7, user_id: "admin" }),
  });
  renderMemory(state.memory);
  showToast("用户记忆周报快照已保存");
}

async function refreshSettings() {
  const payload = await refreshHealth();
  if (payload) renderSettingsSummary(payload);
}

async function refreshTrace(runId = state.currentRunId) {
  if (!runId) {
    renderTimeline([]);
    renderCheckpoints([]);
    return;
  }
  state.currentRunId = runId;
  setText(el.runIdValue, runId);
  const [tracePayload, checkpointPayload, runPayload] = await Promise.all([
    api(`/api/traces/${encodeURIComponent(runId)}`),
    api(`/api/checkpoints/${encodeURIComponent(runId)}`),
    api(`/api/runs/${encodeURIComponent(runId)}`).catch(() => null),
  ]);
  renderTimeline(tracePayload.events || []);
  renderCheckpoints(checkpointPayload.checkpoints || []);
  if (runPayload) {
    const run = normalizeRunDetail(runPayload);
    setRunStatus(run.status);
    renderStats({ ...run.stats, notice_count: run.notice_count, trace_events: run.trace_events });
  }
}

async function refreshIntentPreview() {
  const query = el.queryInput?.value.trim() || "";
  if (!query) {
    if (el.intentPreview) {
      el.intentPreview.className = "intent-preview empty-state";
      el.intentPreview.textContent = "等待解析";
    }
    return;
  }
  try {
    const bidql = await api("/api/intent/parse", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
    renderIntentPreview(bidql);
    autoSelectActionMode(bidql);
  } catch (error) {
    if (el.intentPreview) {
      el.intentPreview.className = "intent-preview empty-state";
      el.intentPreview.textContent = `解析失败：${error.message}`;
    }
  }
}

function payloadFromComposer() {
  return {
    query: el.queryInput?.value.trim() || "",
    max_pages: Number(el.maxPagesInput?.value || 1),
    max_results: Number(el.maxResultsInput?.value || 10),
    model_strategy: checkedValue("modelStrategy"),
  };
}

async function submitRun(event) {
  event.preventDefault();
  const actionMode = checkedValue("actionMode");
  if (actionMode === "subscribe") {
    await createSubscriptionFromForm();
    return;
  }
  const payload = payloadFromComposer();
  if (!payload.query) {
    showToast("请输入自然语言问题");
    return;
  }
  try {
    if (!(await ensureIntentReady(payload.query))) return;
  } catch (error) {
    showToast(`解析失败：${error.message}`);
    return;
  }
  appendMessage("user", escapeHtml(payload.query));
  setRunning(true);
  appendProgressCard(payload.query);
  try {
    const start = await api("/api/runs/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentRunId = start.run_id;
    setText(el.runIdValue, start.run_id);
    updateProgressCard([], { status: "running", stats: {} });
    const result = await pollRunUntilFinished(start.run_id);
    renderRunSummary(result);
    await Promise.all([refreshOutbox(), refreshRuns(), refreshTrace(result.run_id), refreshEvaluation()]);
    appendMessage("assistant", completionMessageHtml(result));
    showToast("任务已完成，Word 已写入 outbox");
  } catch (error) {
    setRunStatus("failed");
    updateProgressCard([], { status: "failed", stats: {}, error: error.message });
    appendMessage("assistant", `运行失败：${escapeHtml(error.message)}`);
    showToast(`运行失败：${error.message}`);
  } finally {
    setRunning(false);
  }
}

async function pollRunUntilFinished(runId) {
  while (true) {
    await delay(1200);
    const snapshot = await loadRunSnapshot(runId);
    renderTimeline(snapshot.events);
    renderCheckpoints(snapshot.checkpoints);
    if (!snapshot.run) {
      updateProgressCard(snapshot.checkpoints, { status: "running", stats: {} });
      continue;
    }
    const run = normalizeRunDetail(snapshot.run);
    setRunStatus(run.status);
    renderStats({ ...run.stats, notice_count: run.notice_count, trace_events: run.trace_events });
    updateProgressCard(snapshot.checkpoints, run);
    if (run.status === "failed") throw new Error(run.error || "run failed");
    if (run.status === "finished") return run;
  }
}

async function loadRunSnapshot(runId) {
  const [tracePayload, checkpointPayload] = await Promise.all([
    api(`/api/traces/${encodeURIComponent(runId)}`),
    api(`/api/checkpoints/${encodeURIComponent(runId)}`),
  ]);
  let runPayload = null;
  try {
    runPayload = await api(`/api/runs/${encodeURIComponent(runId)}`);
  } catch (error) {
    if (!String(error.message || "").includes("run not found")) throw error;
  }
  return {
    events: tracePayload.events || [],
    checkpoints: checkpointPayload.checkpoints || [],
    run: runPayload,
  };
}

async function createSubscriptionFromForm() {
  const payload = { ...payloadFromComposer(), schedule: schedulePayload() };
  if (!payload.query) {
    showToast("请输入自然语言问题");
    return;
  }
  try {
    if (!(await ensureIntentReady(payload.query))) return;
  } catch (error) {
    showToast(`解析失败：${error.message}`);
    return;
  }
  appendMessage("user", escapeHtml(payload.query));
  setRunning(true);
  try {
    const subscription = await api("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshSubscriptions();
    appendMessage("assistant", `订阅已创建，计划：${escapeHtml(subscription.cron || subscription.schedule_kind)}。`);
    showToast(`订阅已创建：${subscription.cron || subscription.schedule_kind}`);
  } catch (error) {
    appendMessage("assistant", `创建订阅失败：${escapeHtml(error.message)}`);
    showToast(`创建订阅失败：${error.message}`);
  } finally {
    setRunning(false);
  }
}

async function triggerSubscription(subscriptionId) {
  setRunning(true);
  try {
    const result = await api(`/api/subscriptions/${encodeURIComponent(subscriptionId)}/run`, { method: "POST" });
    renderRunSummary(result);
    await Promise.all([refreshSubscriptions(), refreshOutbox(), refreshRuns(), refreshTrace(result.run_id), refreshEvaluation()]);
    const stats = result.stats || {};
    const newest = stats.new ?? result.notice_count ?? 0;
    const skipped = stats.skipped_sent ?? 0;
    appendMessage(
      "assistant",
      `订阅已触发，本次新增 ${escapeHtml(newest)} 条，跳过历史 ${escapeHtml(skipped)} 条。${downloadLinkHtml(result.outbox_path)}`,
    );
    showToast("订阅已触发，Word 已写入 outbox");
  } catch (error) {
    showToast(`订阅触发失败：${error.message}`);
  } finally {
    setRunning(false);
  }
}

async function deleteSubscription(subscriptionId) {
  if (!window.confirm("确认删除这个订阅？删除后调度器不会继续推送。")) return;
  await api(`/api/subscriptions/${encodeURIComponent(subscriptionId)}`, { method: "DELETE" });
  await refreshSubscriptions();
  showToast("订阅已删除");
}

async function deleteRun(runId) {
  if (!window.confirm("确认删除这条运行记录？Word 文件不会随记录一起删除。")) return;
  await api(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  if (state.currentRunId === runId) {
    state.currentRunId = null;
    renderTimeline([]);
    renderCheckpoints([]);
    setText(el.runIdValue, "-");
    renderStats({});
    setRunStatus("muted");
  }
  await Promise.all([refreshRuns(), refreshOutbox(), refreshEvaluation()]);
  showToast("运行记录已删除");
}

async function deleteOutboxFile(name) {
  if (!window.confirm("确认删除这个 Word 文件？该操作会移除 outbox 文件和下载记录。")) return;
  await api(`/api/outbox/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (el.latestDownload?.textContent.includes(name)) el.latestDownload.hidden = true;
  await Promise.all([refreshOutbox(), refreshRuns(), refreshEvaluation()]);
  showToast("Word 文件已删除");
}

function schedulePayload() {
  const frequency = el.scheduleFrequency?.value || "daily";
  const time = el.scheduleTime?.value || "09:00";
  if (frequency === "once_at") return { kind: "once_at", time };
  if (frequency === "weekly") return { kind: "recurring", frequency: "weekly", weekday: 1, time };
  if (frequency === "monthly") return { kind: "recurring", frequency: "monthly", day: 1, time };
  return { kind: "recurring", frequency: "daily", time };
}

function checkedValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function setActionMode(value, { touched = true } = {}) {
  const input = document.querySelector(`input[name="actionMode"][value="${value}"]`);
  if (!input) return;
  input.checked = true;
  if (touched) state.actionModeTouched = true;
  syncActionMode();
}

function downloadLinkHtml(path) {
  if (!path) return "";
  const name = fileName(path);
  return `<a class="inline-link" href="/api/outbox/${encodeURIComponent(name)}" data-download-outbox-name="${escapeHtml(name)}">下载 Word</a>`;
}

function subscriptionLatestDownloadHtml(item) {
  const url = item.last_download_url || "";
  if (!url) return "";
  const name = item.last_outbox_name || fileName(item.last_outbox_path || url);
  return `<a class="inline-link" href="${escapeHtml(url)}" data-download-outbox-name="${escapeHtml(name)}">最近 Word</a>`;
}

function completionMessageHtml(result) {
  const run = normalizeRunDetail(result);
  const regionNote = regionScopeText(run.stats);
  return `
    <strong>已完成，命中 ${escapeHtml(run.notice_count)} 条记录。</strong>
    ${regionNote ? `<p class="scope-note">${escapeHtml(regionNote)}</p>` : ""}
    ${downloadLinkHtml(run.outbox_path)}
  `;
}

function normalizeRunDetail(value = {}) {
  const stats = value.stats || {};
  return {
    ...value,
    run_id: value.run_id || value.id || state.currentRunId,
    status: value.status || "muted",
    notice_count: value.notice_count ?? stats.notice_count ?? 0,
    trace_events: value.trace_events ?? stats.trace_events ?? 0,
    outbox_path: value.outbox_path || value.output_docx_path || value.docx_path || "",
    stats,
  };
}

function subscriptionTitle(item) {
  const bidql = item.bidql || {};
  const region = bidql.region?.city || bidql.region?.province || "全国";
  const topics = bidql.topic?.core?.length ? bidql.topic.core.join("、") : "招标";
  const time = bidql.time?.text || bidql.time?.kind || "定时";
  return `${region} ${topics} ${time}`;
}

function scheduleText(item) {
  const schedule = item.bidql?.schedule || {};
  if (item.cron) return cronText(item.cron);
  if (schedule.frequency && schedule.time) return `${frequencyText(schedule.frequency)} ${schedule.time}`;
  return schedule.time || item.schedule_kind || "-";
}

function subscriptionLastRunText(item) {
  const value = item.last_run_finished_at || item.last_run_at;
  return compactDateTimeText(value) || "未运行";
}

function subscriptionNextRunText(item) {
  const value = compactDateTimeText(item.next_run_at);
  return value ? `下次 ${value}` : "下次待调度";
}

function subscriptionIncrementText(item) {
  const newest = Number(item.last_new_count ?? item.last_notice_count ?? 0);
  const skipped = Number(item.last_skipped_sent ?? 0);
  return `新增 ${Number.isFinite(newest) ? newest : 0} / 跳过 ${Number.isFinite(skipped) ? skipped : 0}`;
}

function subscriptionEmailText(item) {
  const status = item.last_email_status;
  if (!status) return "邮件未启用";
  return `邮件 ${emailStatusText(status)}`;
}

function emailStatusText(status) {
  return (
    {
      sent: "已发送",
      skipped: "跳过",
      failed: "失败",
    }[status] || status
  );
}

function compactDateTimeText(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace("T", " ").replace(/([+-]\d\d:\d\d|Z)$/u, "").slice(0, 16);
}

function cronText(value) {
  const parts = String(value || "").trim().split(/\s+/);
  if (parts.length !== 5) return value || "-";
  const [minute, hour, day, month, weekday] = parts;
  const time = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  if (day === "*" && month === "*" && weekday === "*") return `每天 ${time}`;
  if (day === "*" && month === "*" && weekday !== "*") return `每周${weekdayText(weekday)} ${time}`;
  if (day !== "*" && month === "*" && weekday === "*") return `每月${day}日 ${time}`;
  return value;
}

function frequencyText(value) {
  return (
    {
      daily: "每天",
      weekly: "每周",
      monthly: "每月",
      once_at: "一次",
    }[value] || value
  );
}

function weekdayText(value) {
  return (
    {
      "0": "日",
      "1": "一",
      "2": "二",
      "3": "三",
      "4": "四",
      "5": "五",
      "6": "六",
      "7": "日",
    }[String(value)] || value
  );
}

function modelStrategyLabel(value) {
  return (
    {
      config: "跟随配置",
      rules: "本地规则",
      local: "本地模型",
      cloud: "云端模型",
      hybrid: "规则 + 云端",
    }[value] || "跟随配置"
  );
}

function sourceStatsText(stats) {
  const sourceStats = Array.isArray(stats.source_stats) ? stats.source_stats : [];
  if (!sourceStats.length) return "等待来源返回";
  return sourceStats
    .map((item) => {
      const suffix = item.relaxed_city ? "，城市无结果后省内扩展" : "";
      if (item.status === "failed") return `${item.source} 失败`;
      return `${item.source} ${item.count ?? 0} 条${suffix}`;
    })
    .join(" · ");
}

function regionScopeText(stats) {
  const scope = stats?.region_scope;
  if (!scope || scope.status !== "relaxed_city") return "";
  return scope.message || `${scope.requested_city}城市级检索未命中样本，已扩大到${scope.fallback_region}省内检索。`;
}

function formatPayload(payload) {
  if (!payload || !Object.keys(payload).length) return "";
  return JSON.stringify(payload);
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function percent(value) {
  const number = Number(value || 0);
  return `${(number * 100).toFixed(1)}%`;
}

function stageLabel(key) {
  return pipelineStages.find((stage) => stage.key === key)?.label || key;
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).pop();
}

function setText(node, value) {
  if (node) node.textContent = String(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function applyDepthProfile(value) {
  const profile = depthProfiles[value] || depthProfiles.standard;
  if (el.maxPagesInput) el.maxPagesInput.value = String(profile.pages);
  if (el.maxResultsInput) el.maxResultsInput.value = String(profile.results);
}

function applyExampleQuery(query) {
  if (!query || !el.queryInput) return;
  el.queryInput.value = query;
  state.actionModeTouched = false;
  syncActionMode();
  refreshIntentPreview().catch(toastError("示例解析失败"));
  el.queryInput.focus();
  trackActivity("quick_example", {
    target: "smartStart",
    label: query,
    metadata: { query },
  });
}

function syncActionMode() {
  const subscribe = checkedValue("actionMode") === "subscribe";
  if (el.subscriptionControls) {
    el.subscriptionControls.hidden = !subscribe;
    el.subscriptionControls.setAttribute("aria-disabled", String(!subscribe));
    el.subscriptionControls.querySelectorAll("select, input").forEach((node) => {
      node.disabled = !subscribe;
    });
  }
  if (el.subscribeButton) el.subscribeButton.hidden = true;
  el.form?.classList.toggle("subscribe-mode", subscribe);
  renderSmartStart();
  if (!el.runButton || state.running) return;
  const hasQuery = Boolean(el.queryInput?.value.trim());
  el.runButton.disabled = !hasQuery;
  el.runButton.title = hasQuery
    ? subscribe
      ? "按计划启用增量订阅，后续只推送新增内容"
      : "立即运行一次检索并生成 Word"
    : "先输入招投标查询问题";
  el.runButton.innerHTML = subscribe
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>启用订阅'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>立即生成 Word';
}

async function refreshAll() {
  const health = await refreshHealth();
  if (health) renderSettingsSummary(health);
  const results = await Promise.allSettled([
    refreshIntentPreview(),
    refreshOutbox(),
    refreshSubscriptions(),
    refreshSourcesPanel(),
    refreshRuns(),
    refreshEvaluation(),
    refreshMemoryWeekly(),
  ]);
  const failed = results.filter((item) => item.status === "rejected");
  if (failed.length) showToast(`${failed.length} 个面板刷新失败，请查看网络或服务状态`);
  renderNotifications();
  renderHelpPanel();
  renderUserMenu();
}

function normalizeWorkbenchLayout() {
  const grid = document.querySelector(".workbench-grid");
  const chatPanel = document.querySelector(".chat-panel");
  if (!grid || !chatPanel || document.querySelector(".main-stack")) return;
  const stack = document.createElement("div");
  stack.className = "main-stack";
  grid.insertBefore(stack, chatPanel);
  stack.append(chatPanel);
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  el.notificationButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePopover("notifications");
  });
  el.themeToggleButton?.addEventListener("click", () => {
    applyTheme(state.theme === "dark" ? "light" : "dark");
  });
  el.helpButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePopover("help");
  });
  el.userMenuButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePopover("user");
  });
  el.refreshNotificationsButton?.addEventListener("click", () => {
    refreshAll().catch(toastError("通知刷新失败"));
  });
  document.addEventListener("click", (event) => {
    trackClick(event);
    const closeTarget = event.target.closest("[data-close-popover]");
    if (closeTarget) {
      closePopovers();
      return;
    }
    const popoverViewTarget = event.target.closest("[data-popover-view]");
    if (popoverViewTarget) {
      showView(popoverViewTarget.dataset.popoverView);
      closePopovers();
      return;
    }
    const refreshAllTarget = event.target.closest("[data-refresh-all]");
    if (refreshAllTarget) {
      refreshAll().catch(toastError("刷新失败"));
      return;
    }
    const deleteOutboxTarget = event.target.closest("[data-delete-outbox-name]");
    if (deleteOutboxTarget) {
      deleteOutboxFile(deleteOutboxTarget.dataset.deleteOutboxName).catch(toastError("删除 Word 失败"));
      return;
    }
    const deleteRunTarget = event.target.closest("[data-delete-run-id]");
    if (deleteRunTarget) {
      deleteRun(deleteRunTarget.dataset.deleteRunId).catch(toastError("删除运行记录失败"));
      return;
    }
    const deleteSubscriptionTarget = event.target.closest("[data-delete-subscription-id]");
    if (deleteSubscriptionTarget) {
      deleteSubscription(deleteSubscriptionTarget.dataset.deleteSubscriptionId).catch(toastError("删除订阅失败"));
      return;
    }
    const runTarget = event.target.closest("[data-run-id]");
    if (runTarget) {
      showView("historyView");
      refreshTrace(runTarget.dataset.runId).catch(toastError("追踪加载失败"));
      return;
    }
    const subscriptionTarget = event.target.closest("[data-subscription-id]");
    if (subscriptionTarget) {
      triggerSubscription(subscriptionTarget.dataset.subscriptionId);
      return;
    }
    if (!event.target.closest(".topbar-actions")) {
      closePopovers();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePopovers();
  });
  el.form?.addEventListener("submit", submitRun);
  el.subscribeButton?.addEventListener("click", createSubscriptionFromForm);
  el.queryInput?.addEventListener("input", () => {
    syncActionMode();
    renderSmartStart();
  });
  el.queryInput?.addEventListener("input", debounce(refreshIntentPreview, 450));
  el.searchDepthSelect?.addEventListener("change", () => applyDepthProfile(el.searchDepthSelect.value));
  document.querySelectorAll('input[name="actionMode"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.actionModeTouched = true;
      syncActionMode();
    });
  });
  document.querySelectorAll('input[name="modelStrategy"]').forEach((input) => {
    input.addEventListener("change", renderSmartStart);
  });
  document.querySelectorAll("[data-example-query]").forEach((button) => {
    button.addEventListener("click", () => applyExampleQuery(button.dataset.exampleQuery || ""));
  });
  el.refreshOutboxButton?.addEventListener("click", () => refreshOutbox().catch(toastError("Outbox 刷新失败")));
  el.refreshTraceButton?.addEventListener("click", () => refreshTrace().catch(toastError("事件流刷新失败")));
  el.refreshSourcesButton?.addEventListener("click", () =>
    refreshSourcesPanel().catch(toastError("来源刷新失败")),
  );
  el.refreshRunsButton?.addEventListener("click", () => refreshRuns().catch(toastError("历史刷新失败")));
  el.refreshEvaluationButton?.addEventListener("click", () =>
    refreshEvaluation().catch(toastError("评测刷新失败")),
  );
  el.refreshMemoryButton?.addEventListener("click", () =>
    refreshMemoryWeekly().catch(toastError("用户记忆刷新失败")),
  );
  el.saveMemoryButton?.addEventListener("click", () =>
    saveMemoryWeekly().catch(toastError("用户记忆保存失败")),
  );
  el.runSearchInput?.addEventListener(
    "input",
    debounce(() => {
      state.runFilters.query = el.runSearchInput.value;
      state.runFilters.expanded = false;
      renderRuns(state.runs);
    }, 120),
  );
  el.runStatusFilter?.addEventListener("change", () => {
    state.runFilters.status = el.runStatusFilter.value;
    state.runFilters.expanded = false;
    renderRuns(state.runs);
  });
  el.runSortSelect?.addEventListener("change", () => {
    state.runFilters.sort = el.runSortSelect.value;
    renderRuns(state.runs);
  });
  el.toggleRunsButton?.addEventListener("click", () => {
    state.runFilters.expanded = !state.runFilters.expanded;
    renderRuns(state.runs);
  });
  el.clearRunFiltersButton?.addEventListener("click", () => {
    state.runFilters = { query: "", status: "all", sort: "started_desc", expanded: false };
    if (el.runSearchInput) el.runSearchInput.value = "";
    if (el.runStatusFilter) el.runStatusFilter.value = "all";
    if (el.runSortSelect) el.runSortSelect.value = "started_desc";
    renderRuns(state.runs);
  });
  document.querySelectorAll("[data-refresh-sources]").forEach((button) => {
    button.addEventListener("click", () => refreshSourcesPanel().catch(toastError("来源刷新失败")));
  });
}

async function init() {
  normalizeWorkbenchLayout();
  bindEvents();
  applyTheme(loadTheme());
  applyDepthProfile(el.searchDepthSelect?.value || "standard");
  syncActionMode();
  await refreshAll();
}

init().catch((error) => showToast(`页面初始化失败：${error.message}`));
