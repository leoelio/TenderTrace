const state = {
  currentRunId: null,
  running: false,
  progressCard: null,
  health: null,
  runs: [],
  outbox: [],
  subscriptions: [],
  sources: [],
  model: null,
  modelDoctor: null,
  evaluation: null,
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
  traceTimeline: document.querySelector("#traceTimeline"),
  checkpointList: document.querySelector("#checkpointList"),
  checkpointCount: document.querySelector("#checkpointCount"),
  outboxBody: document.querySelector("#outboxBody"),
  refreshTraceButton: document.querySelector("#refreshTraceButton"),
  refreshOutboxButton: document.querySelector("#refreshOutboxButton"),
  refreshSubscriptionsButton: document.querySelector("#refreshSubscriptionsButton"),
  refreshSourcesButton: document.querySelector("#refreshSourcesButton"),
  refreshRunsButton: document.querySelector("#refreshRunsButton"),
  refreshEvaluationButton: document.querySelector("#refreshEvaluationButton"),
  modelDoctorButton: document.querySelector("#modelDoctorButton"),
  subscriptionBody: document.querySelector("#subscriptionBody"),
  subscriptionPageBody: document.querySelector("#subscriptionPageBody"),
  runHistoryBody: document.querySelector("#runHistoryBody"),
  sourceList: document.querySelector("#sourceList"),
  sourcePageList: document.querySelector("#sourcePageList"),
  modelStatus: document.querySelector("#modelStatus"),
  modelDoctorResult: document.querySelector("#modelDoctorResult"),
  evaluationSummary: document.querySelector("#evaluationSummary"),
  ragMetrics: document.querySelector("#ragMetrics"),
  agentMetrics: document.querySelector("#agentMetrics"),
  harnessMetrics: document.querySelector("#harnessMetrics"),
  recallMetrics: document.querySelector("#recallMetrics"),
  evaluationCases: document.querySelector("#evaluationCases"),
  evaluationNotes: document.querySelector("#evaluationNotes"),
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
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === viewId);
  });
  if (viewId === "historyView") refreshRuns().catch(toastError("历史运行加载失败"));
  if (viewId === "subscriptionsView") refreshSubscriptions().catch(toastError("订阅加载失败"));
  if (viewId === "sourcesView") refreshSourcesAndModel().catch(toastError("数据源加载失败"));
  if (viewId === "evaluationView") refreshEvaluation().catch(toastError("评测加载失败"));
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

function renderRunSummary(result) {
  const run = normalizeRunDetail(result);
  state.currentRunId = run.run_id;
  setText(el.runIdValue, run.run_id || "-");
  renderStats({ ...run.stats, notice_count: run.notice_count, trace_events: run.trace_events });
  setRunStatus(run.status || "muted");
  if (!run.outbox_path || !el.latestDownload) return;
  const name = fileName(run.outbox_path);
  el.latestDownload.hidden = false;
  el.latestDownload.innerHTML = `
    <strong>${escapeHtml(name)}</strong>
    <div class="action-group">
      <a class="link-button" href="/api/outbox/${encodeURIComponent(name)}">下载</a>
      <button class="ghost-button" type="button" data-run-id="${escapeHtml(run.run_id)}">追踪</button>
      <button class="danger-button" type="button" data-delete-outbox-name="${escapeHtml(name)}">删除文件</button>
    </div>
  `;
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
  if (!el.outboxBody) return;
  if (!items.length) {
    el.outboxBody.innerHTML = '<tr><td colspan="5" class="empty-cell">暂无 Word 文件</td></tr>';
    return;
  }
  el.outboxBody.innerHTML = items
    .map((item) => {
      const name = escapeHtml(item.name);
      return `
        <tr>
          <td class="file-cell"><span class="file-name" title="${name}">${name}</span></td>
          <td>${escapeHtml(item.created_at || "-")}</td>
          <td><span class="badge badge-${escapeHtml(item.status || "muted")}">${escapeHtml(statusLabel(item.status))}</span></td>
          <td>${escapeHtml(formatBytes(item.size))}</td>
          <td>
            <div class="action-group">
              <a class="link-button" href="${escapeHtml(item.download_url)}">下载</a>
              ${
                item.run_id
                  ? `<button class="ghost-button" type="button" data-run-id="${escapeHtml(item.run_id)}">追踪</button>`
                  : ""
              }
              <button class="danger-button" type="button" data-delete-outbox-name="${name}">删除</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderSubscriptions(items) {
  renderSubscriptionTable(el.subscriptionBody, items);
  renderSubscriptionTable(el.subscriptionPageBody, items);
}

function renderSubscriptionTable(target, items) {
  if (!target) return;
  if (!items.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无订阅任务</td></tr>';
    return;
  }
  target.innerHTML = items
    .map((item) => {
      const query = escapeHtml(item.original_query);
      const title = escapeHtml(subscriptionTitle(item));
      const schedule = escapeHtml(scheduleText(item));
      return `
        <tr>
          <td class="file-cell"><span class="file-name" title="${title}">${title}</span></td>
          <td class="file-cell"><span class="file-name" title="${query}">${query}</span></td>
          <td>${schedule}</td>
          <td><span class="badge badge-${escapeHtml(item.status || "muted")}">${escapeHtml(statusLabel(item.status))}</span></td>
          <td>${escapeHtml(item.last_run_at || "-")}</td>
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
      const validation = item.validation ? `<span>validation: ${escapeHtml(item.validation)}</span>` : "";
      const counts =
        item.cookie_count || item.origin_count
          ? `<span>cookies/origins: ${escapeHtml(item.cookie_count || 0)} / ${escapeHtml(item.origin_count || 0)}</span>`
          : "";
      const detail = item.detail ? `<span>${escapeHtml(item.detail)}</span>` : "";
      return `
        <div class="source-row">
          <strong>${site} · ${engine}</strong>
          <span><span class="badge badge-${status}">${escapeHtml(statusLabel(item.status))}</span></span>
          ${validation}
          ${counts}
          ${detail}
        </div>
      `;
    })
    .join("");
}

function renderModelStatus(item) {
  if (!el.modelStatus) return;
  if (!item) {
    el.modelStatus.className = "source-list empty-state";
    el.modelStatus.textContent = "Unavailable";
    return;
  }
  const status = item.configured ? "configured" : "login_required";
  el.modelStatus.className = "source-list";
  el.modelStatus.innerHTML = `
    <div class="source-row">
      <strong>${escapeHtml(item.provider || "none")} · ${escapeHtml(item.mode || "-")}</strong>
      <span><span class="badge badge-${status}">${escapeHtml(statusLabel(status))}</span></span>
      <span>model: ${escapeHtml(item.model || "-")}</span>
      <span>enhancement: ${escapeHtml(item.enhancement_enabled ? "enabled" : "disabled")}</span>
    </div>
  `;
}

function renderModelDoctor(report) {
  if (!el.modelDoctorResult) return;
  if (!report) {
    el.modelDoctorResult.className = "source-list empty-state";
    el.modelDoctorResult.textContent = "Not checked";
    return;
  }
  const checks = report.checks || [];
  el.modelDoctorResult.className = checks.length ? "source-list" : "source-list empty-state";
  el.modelDoctorResult.innerHTML = checks.length
    ? checks
        .map((check) => {
          const status = escapeHtml(check.status || "muted");
          return `
            <div class="source-row">
              <strong>${escapeHtml(check.name || "-")}</strong>
              <span><span class="badge badge-${status}">${escapeHtml(statusLabel(check.status))}</span></span>
              <span>${escapeHtml(check.detail || "")}</span>
            </div>
          `;
        })
        .join("")
    : "暂无检测项";
}

function renderRuns(items) {
  if (!el.runHistoryBody) return;
  if (!items.length) {
    el.runHistoryBody.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无运行记录</td></tr>';
    return;
  }
  el.runHistoryBody.innerHTML = items
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
              ${outboxName ? `<a class="link-button" href="/api/outbox/${encodeURIComponent(outboxName)}">下载</a>` : ""}
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
  const modelChecks = (state.modelDoctor?.checks || []).filter((item) => !["pass", "skipped"].includes(item.status));
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
  if (state.model && !state.model.configured) {
    issues.push({
      title: "模型配置未就绪",
      detail: `${state.model.mode || "-"} / ${state.model.provider || "-"}`,
      view: "settingsView",
    });
  }
  if (modelChecks.length) {
    issues.push({
      title: `${modelChecks.length} 个模型自检项需要关注`,
      detail: modelChecks.map((item) => `${item.name}: ${statusLabel(item.status)}`).join("；"),
      view: "settingsView",
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

async function refreshModel() {
  state.model = await api("/api/model");
  renderModelStatus(state.model);
  renderNotifications();
}

async function refreshModelDoctor() {
  state.modelDoctor = await api("/api/model/doctor");
  renderModelDoctor(state.modelDoctor);
  renderNotifications();
}

async function refreshSourcesAndModel() {
  await Promise.all([refreshSources(), refreshModel(), refreshModelDoctor()]);
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
    appendMessage(
      "assistant",
      `订阅已触发，本次新增 ${escapeHtml(result.notice_count)} 条。${downloadLinkHtml(result.outbox_path)}`,
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

function downloadLinkHtml(path) {
  if (!path) return "";
  const name = fileName(path);
  return `<a class="inline-link" href="/api/outbox/${encodeURIComponent(name)}">下载 Word</a>`;
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
  if (item.cron) return item.cron;
  if (schedule.frequency && schedule.time) return `${schedule.frequency} ${schedule.time}`;
  return schedule.time || item.schedule_kind || "-";
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

function syncActionMode() {
  const subscribe = checkedValue("actionMode") === "subscribe";
  if (el.subscriptionControls) el.subscriptionControls.hidden = !subscribe;
  if (el.subscribeButton) el.subscribeButton.hidden = true;
  el.form?.classList.toggle("subscribe-mode", subscribe);
  if (!el.runButton || state.running) return;
  el.runButton.innerHTML = subscribe
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>创建订阅'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>开始运行';
}

async function refreshAll() {
  const health = await refreshHealth();
  if (health) renderSettingsSummary(health);
  const results = await Promise.allSettled([
    refreshIntentPreview(),
    refreshOutbox(),
    refreshSubscriptions(),
    refreshSourcesAndModel(),
    refreshRuns(),
    refreshEvaluation(),
  ]);
  const failed = results.filter((item) => item.status === "rejected");
  if (failed.length) showToast(`${failed.length} 个面板刷新失败，请查看网络或服务状态`);
  renderNotifications();
  renderHelpPanel();
  renderUserMenu();
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
  el.queryInput?.addEventListener("input", debounce(refreshIntentPreview, 450));
  el.searchDepthSelect?.addEventListener("change", () => applyDepthProfile(el.searchDepthSelect.value));
  document.querySelectorAll('input[name="actionMode"]').forEach((input) => {
    input.addEventListener("change", syncActionMode);
  });
  el.refreshOutboxButton?.addEventListener("click", () => refreshOutbox().catch(toastError("Outbox 刷新失败")));
  el.refreshTraceButton?.addEventListener("click", () => refreshTrace().catch(toastError("事件流刷新失败")));
  el.refreshSubscriptionsButton?.addEventListener("click", () =>
    refreshSubscriptions().catch(toastError("订阅刷新失败")),
  );
  el.refreshSourcesButton?.addEventListener("click", () =>
    refreshSourcesAndModel().catch(toastError("来源刷新失败")),
  );
  el.refreshRunsButton?.addEventListener("click", () => refreshRuns().catch(toastError("历史刷新失败")));
  el.refreshEvaluationButton?.addEventListener("click", () =>
    refreshEvaluation().catch(toastError("评测刷新失败")),
  );
  el.modelDoctorButton?.addEventListener("click", () => refreshModelDoctor().catch(toastError("模型自检失败")));
  document.querySelectorAll("[data-refresh-sources]").forEach((button) => {
    button.addEventListener("click", () => refreshSourcesAndModel().catch(toastError("来源刷新失败")));
  });
}

async function init() {
  bindEvents();
  applyTheme(loadTheme());
  applyDepthProfile(el.searchDepthSelect?.value || "standard");
  syncActionMode();
  await refreshAll();
}

init().catch((error) => showToast(`页面初始化失败：${error.message}`));
