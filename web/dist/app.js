const state = {
  currentRunId: null,
  running: false,
  progressCard: null,
  health: null,
  runs: [],
  outbox: [],
  subscriptions: [],
  sources: [],
  sourceAlerts: null,
  evaluation: null,
  memory: null,
  organizationWorkspaces: [],
  organizationMemories: [],
  organizationWorkspaceId: "",
  organizationGroupMode: "create",
  organizationConvertMemoryId: "",
  feishu: null,
  opportunities: [],
  opportunitySummaryData: {},
  opportunityRequirementPayloads: {},
  opportunityVisible: 20,
  pendingOpportunityId: "",
  pendingOpportunityTeamId: "",
  pendingOpportunityStakeholderId: "",
  pendingRelationshipActionNoticeId: "",
  pendingRelationshipActionStakeholderId: "",
  pendingOpportunityOutcomeNoticeId: "",
  pendingOpportunityOutcomeAction: "",
  editingOpportunityOutcome: false,
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
  { key: "evidence", label: "证据研判", detail: "清洗、去重、证据与机会评分" },
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
  mobileNavButton: document.querySelector("#mobileNavButton"),
  topNavigation: document.querySelector("#topNavigation"),
  form: document.querySelector("#runForm"),
  queryInput: document.querySelector("#queryInput"),
  chatStream: document.querySelector("#chatStream"),
  smartStartPanel: document.querySelector("#smartStartPanel"),
  smartStartMeta: document.querySelector("#smartStartMeta"),
  intentPreview: document.querySelector("#intentPreview"),
  searchDepthSelect: document.querySelector("#searchDepthSelect"),
  modelStrategySelect: document.querySelector("#modelStrategySelect"),
  feishuDeliveryInput: document.querySelector("#feishuDeliveryInput"),
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
  refreshOpportunitiesButton: document.querySelector("#refreshOpportunitiesButton"),
  syncFeishuTasksButton: document.querySelector("#syncFeishuTasksButton"),
  sendOpportunityChangesButton: document.querySelector("#sendOpportunityChangesButton"),
  sendOpportunityBriefingButton: document.querySelector("#sendOpportunityBriefingButton"),
  opportunityTopicFilter: document.querySelector("#opportunityTopicFilter"),
  opportunityLevelFilter: document.querySelector("#opportunityLevelFilter"),
  opportunitySortSelect: document.querySelector("#opportunitySortSelect"),
  opportunitySummary: document.querySelector("#opportunitySummary"),
  opportunityDecisionBoard: document.querySelector("#opportunityDecisionBoard"),
  opportunityMarket: document.querySelector("#opportunityMarket"),
  openFeishuBitableButton: document.querySelector("#openFeishuBitableButton"),
  opportunityList: document.querySelector("#opportunityList"),
  opportunityFooter: document.querySelector("#opportunityFooter"),
  opportunityListHint: document.querySelector("#opportunityListHint"),
  loadMoreOpportunitiesButton: document.querySelector("#loadMoreOpportunitiesButton"),
  opportunityDetailDialog: document.querySelector("#opportunityDetailDialog"),
  opportunityDetailTitle: document.querySelector("#opportunityDetailTitle"),
  opportunityDetailContent: document.querySelector("#opportunityDetailContent"),
  opportunityOwnerDialog: document.querySelector("#opportunityOwnerDialog"),
  opportunityOwnerForm: document.querySelector("#opportunityOwnerForm"),
  opportunityOwnerProject: document.querySelector("#opportunityOwnerProject"),
  opportunityOwnerSelect: document.querySelector("#opportunityOwnerSelect"),
  opportunityOwnerName: document.querySelector("#opportunityOwnerName"),
  opportunityOwnerStatus: document.querySelector("#opportunityOwnerStatus"),
  opportunityCreateTask: document.querySelector("#opportunityCreateTask"),
  opportunityCreateCalendar: document.querySelector("#opportunityCreateCalendar"),
  submitOpportunityOwnerButton: document.querySelector("#submitOpportunityOwnerButton"),
  closeOpportunityOwnerButton: document.querySelector("#closeOpportunityOwnerButton"),
  cancelOpportunityOwnerButton: document.querySelector("#cancelOpportunityOwnerButton"),
  opportunityTeamDialog: document.querySelector("#opportunityTeamDialog"),
  opportunityTeamForm: document.querySelector("#opportunityTeamForm"),
  opportunityTeamProject: document.querySelector("#opportunityTeamProject"),
  opportunityTeamMemberSelect: document.querySelector("#opportunityTeamMemberSelect"),
  opportunityTeamMemberName: document.querySelector("#opportunityTeamMemberName"),
  opportunityTeamRole: document.querySelector("#opportunityTeamRole"),
  opportunityTeamOrganizationType: document.querySelector("#opportunityTeamOrganizationType"),
  opportunityTeamOrganizationName: document.querySelector("#opportunityTeamOrganizationName"),
  opportunityTeamResponsibility: document.querySelector("#opportunityTeamResponsibility"),
  opportunityTeamStatus: document.querySelector("#opportunityTeamStatus"),
  submitOpportunityTeamButton: document.querySelector("#submitOpportunityTeamButton"),
  closeOpportunityTeamButton: document.querySelector("#closeOpportunityTeamButton"),
  cancelOpportunityTeamButton: document.querySelector("#cancelOpportunityTeamButton"),
  opportunityStakeholderDialog: document.querySelector("#opportunityStakeholderDialog"),
  opportunityStakeholderForm: document.querySelector("#opportunityStakeholderForm"),
  opportunityStakeholderProject: document.querySelector("#opportunityStakeholderProject"),
  opportunityStakeholderName: document.querySelector("#opportunityStakeholderName"),
  opportunityStakeholderOrganization: document.querySelector("#opportunityStakeholderOrganization"),
  opportunityStakeholderTitleInput: document.querySelector("#opportunityStakeholderTitleInput"),
  opportunityStakeholderRole: document.querySelector("#opportunityStakeholderRole"),
  opportunityStakeholderInfluence: document.querySelector("#opportunityStakeholderInfluence"),
  opportunityStakeholderStance: document.querySelector("#opportunityStakeholderStance"),
  opportunityStakeholderRelationship: document.querySelector("#opportunityStakeholderRelationship"),
  opportunityStakeholderOwner: document.querySelector("#opportunityStakeholderOwner"),
  opportunityStakeholderNextAction: document.querySelector("#opportunityStakeholderNextAction"),
  opportunityStakeholderEvidenceSource: document.querySelector("#opportunityStakeholderEvidenceSource"),
  opportunityStakeholderEvidenceUrl: document.querySelector("#opportunityStakeholderEvidenceUrl"),
  opportunityStakeholderEvidenceText: document.querySelector("#opportunityStakeholderEvidenceText"),
  submitOpportunityStakeholderButton: document.querySelector("#submitOpportunityStakeholderButton"),
  closeOpportunityStakeholderButton: document.querySelector("#closeOpportunityStakeholderButton"),
  cancelOpportunityStakeholderButton: document.querySelector("#cancelOpportunityStakeholderButton"),
  relationshipActionDialog: document.querySelector("#relationshipActionDialog"),
  relationshipActionForm: document.querySelector("#relationshipActionForm"),
  relationshipActionProject: document.querySelector("#relationshipActionProject"),
  relationshipActionStakeholder: document.querySelector("#relationshipActionStakeholder"),
  relationshipActionTitle: document.querySelector("#relationshipActionTitle"),
  relationshipActionType: document.querySelector("#relationshipActionType"),
  relationshipActionPriority: document.querySelector("#relationshipActionPriority"),
  relationshipActionAssignee: document.querySelector("#relationshipActionAssignee"),
  relationshipActionDueAt: document.querySelector("#relationshipActionDueAt"),
  relationshipActionCreateFeishu: document.querySelector("#relationshipActionCreateFeishu"),
  submitRelationshipActionButton: document.querySelector("#submitRelationshipActionButton"),
  closeRelationshipActionButton: document.querySelector("#closeRelationshipActionButton"),
  cancelRelationshipActionButton: document.querySelector("#cancelRelationshipActionButton"),
  opportunityOutcomeDialog: document.querySelector("#opportunityOutcomeDialog"),
  opportunityOutcomeForm: document.querySelector("#opportunityOutcomeForm"),
  opportunityOutcomeTitle: document.querySelector("#opportunityOutcomeTitle"),
  opportunityOutcomeProject: document.querySelector("#opportunityOutcomeProject"),
  opportunityOutcomeReason: document.querySelector("#opportunityOutcomeReason"),
  opportunityOutcomeWinner: document.querySelector("#opportunityOutcomeWinner"),
  opportunityOutcomeAmount: document.querySelector("#opportunityOutcomeAmount"),
  opportunityOutcomeCurrency: document.querySelector("#opportunityOutcomeCurrency"),
  opportunityOutcomeSummary: document.querySelector("#opportunityOutcomeSummary"),
  opportunityOutcomeLessons: document.querySelector("#opportunityOutcomeLessons"),
  opportunityOutcomeFeedback: document.querySelector("#opportunityOutcomeFeedback"),
  opportunityOutcomeFollowUp: document.querySelector("#opportunityOutcomeFollowUp"),
  opportunityOutcomeEvidenceUrl: document.querySelector("#opportunityOutcomeEvidenceUrl"),
  opportunityOutcomeEvidenceText: document.querySelector("#opportunityOutcomeEvidenceText"),
  opportunityOutcomeStatus: document.querySelector("#opportunityOutcomeStatus"),
  submitOpportunityOutcomeButton: document.querySelector("#submitOpportunityOutcomeButton"),
  closeOpportunityOutcomeButton: document.querySelector("#closeOpportunityOutcomeButton"),
  cancelOpportunityOutcomeButton: document.querySelector("#cancelOpportunityOutcomeButton"),
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
  sourceAlertSummary: document.querySelector("#sourceAlertSummary"),
  evaluationSummary: document.querySelector("#evaluationSummary"),
  ragMetrics: document.querySelector("#ragMetrics"),
  agentMetrics: document.querySelector("#agentMetrics"),
  harnessMetrics: document.querySelector("#harnessMetrics"),
  recallMetrics: document.querySelector("#recallMetrics"),
  evaluationCases: document.querySelector("#evaluationCases"),
  evaluationHarnessCases: document.querySelector("#evaluationHarnessCases"),
  evaluationNotes: document.querySelector("#evaluationNotes"),
  refreshMemoryButton: document.querySelector("#refreshMemoryButton"),
  saveMemoryButton: document.querySelector("#saveMemoryButton"),
  sendMemoryFeishuButton: document.querySelector("#sendMemoryFeishuButton"),
  memorySummary: document.querySelector("#memorySummary"),
  memoryUsageMetrics: document.querySelector("#memoryUsageMetrics"),
  memoryReportMetrics: document.querySelector("#memoryReportMetrics"),
  memorySubscriptionMetrics: document.querySelector("#memorySubscriptionMetrics"),
  memoryDailyMetrics: document.querySelector("#memoryDailyMetrics"),
  memoryProfile: document.querySelector("#memoryProfile"),
  memoryGeneratedAdvice: document.querySelector("#memoryGeneratedAdvice"),
  memoryIngestCoverage: document.querySelector("#memoryIngestCoverage"),
  memoryQueries: document.querySelector("#memoryQueries"),
  memorySuggestions: document.querySelector("#memorySuggestions"),
  memoryEvents: document.querySelector("#memoryEvents"),
  memoryAnalysis: document.querySelector("#memoryAnalysis"),
  organizationWorkspaceSelect: document.querySelector("#organizationWorkspaceSelect"),
  organizationMemorySearch: document.querySelector("#organizationMemorySearch"),
  organizationMemoryTypeFilter: document.querySelector("#organizationMemoryTypeFilter"),
  organizationSummary: document.querySelector("#organizationSummary"),
  organizationMemoryMeta: document.querySelector("#organizationMemoryMeta"),
  organizationMemoryList: document.querySelector("#organizationMemoryList"),
  organizationMemoryForm: document.querySelector("#organizationMemoryForm"),
  organizationMemoryType: document.querySelector("#organizationMemoryType"),
  organizationMemoryTitleInput: document.querySelector("#organizationMemoryTitleInput"),
  organizationMemoryContent: document.querySelector("#organizationMemoryContent"),
  organizationMemoryNoticeId: document.querySelector("#organizationMemoryNoticeId"),
  organizationMemoryEvidenceUrl: document.querySelector("#organizationMemoryEvidenceUrl"),
  refreshOrganizationButton: document.querySelector("#refreshOrganizationButton"),
  openOrganizationWorkspaceButton: document.querySelector("#openOrganizationWorkspaceButton"),
  createOrganizationWorkspaceButton: document.querySelector("#createOrganizationWorkspaceButton"),
  inviteOrganizationMembersButton: document.querySelector("#inviteOrganizationMembersButton"),
  organizationGroupDialog: document.querySelector("#organizationGroupDialog"),
  organizationGroupForm: document.querySelector("#organizationGroupForm"),
  organizationGroupDialogTitle: document.querySelector("#organizationGroupDialogTitle"),
  organizationGroupDialogMeta: document.querySelector("#organizationGroupDialogMeta"),
  organizationGroupNameField: document.querySelector("#organizationGroupNameField"),
  organizationGroupName: document.querySelector("#organizationGroupName"),
  organizationMemberSelect: document.querySelector("#organizationMemberSelect"),
  organizationGroupStatus: document.querySelector("#organizationGroupStatus"),
  submitOrganizationGroupButton: document.querySelector("#submitOrganizationGroupButton"),
  closeOrganizationGroupButton: document.querySelector("#closeOrganizationGroupButton"),
  cancelOrganizationGroupButton: document.querySelector("#cancelOrganizationGroupButton"),
  organizationConvertDialog: document.querySelector("#organizationConvertDialog"),
  organizationConvertForm: document.querySelector("#organizationConvertForm"),
  organizationConvertMemoryTitle: document.querySelector("#organizationConvertMemoryTitle"),
  organizationConvertTarget: document.querySelector("#organizationConvertTarget"),
  organizationConvertNoticeId: document.querySelector("#organizationConvertNoticeId"),
  organizationConvertActionTitle: document.querySelector("#organizationConvertActionTitle"),
  organizationConvertDueAt: document.querySelector("#organizationConvertDueAt"),
  organizationConvertPriority: document.querySelector("#organizationConvertPriority"),
  organizationConvertFactField: document.querySelector("#organizationConvertFactField"),
  organizationConvertFactValue: document.querySelector("#organizationConvertFactValue"),
  organizationConvertEvidenceUrl: document.querySelector("#organizationConvertEvidenceUrl"),
  organizationConvertStatus: document.querySelector("#organizationConvertStatus"),
  closeOrganizationConvertButton: document.querySelector("#closeOrganizationConvertButton"),
  cancelOrganizationConvertButton: document.querySelector("#cancelOrganizationConvertButton"),
  settingsSummary: document.querySelector("#settingsSummary"),
  feishuCenterMeta: document.querySelector("#feishuCenterMeta"),
  feishuFeatureList: document.querySelector("#feishuFeatureList"),
  feishuIssueList: document.querySelector("#feishuIssueList"),
  feishuAttemptList: document.querySelector("#feishuAttemptList"),
  refreshFeishuButton: document.querySelector("#refreshFeishuButton"),
  testFeishuButton: document.querySelector("#testFeishuButton"),
  importFeishuLeadsButton: document.querySelector("#importFeishuLeadsButton"),
  configureFeishuReceiverButton: document.querySelector("#configureFeishuReceiverButton"),
  feishuReceiverEditor: document.querySelector("#feishuReceiverEditor"),
  feishuChatSelect: document.querySelector("#feishuChatSelect"),
  saveFeishuReceiverButton: document.querySelector("#saveFeishuReceiverButton"),
  cancelFeishuReceiverButton: document.querySelector("#cancelFeishuReceiverButton"),
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
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") return detail.error || detail.message || JSON.stringify(detail);
    return text;
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
    login_expired: "登录过期",
    pass: "通过",
    incomplete: "未就绪",
    warn: "提醒",
    skipped: "跳过",
    healthy: "健康",
    degraded: "降级",
    unhealthy: "异常",
    unknown: "暂无样本",
    sent: "已发送",
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

function sourceAccessStatus(item) {
  if (!item?.requires_login) return { label: "公开", badge: "pass" };
  if (item.status === "configured") return { label: "已登录", badge: "pass" };
  if (item.status === "login_expired") return { label: "登录过期", badge: "warn" };
  return { label: "待登录", badge: "warn" };
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
  el.topNavigation?.classList.remove("open");
  el.mobileNavButton?.setAttribute("aria-expanded", "false");
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === viewId);
  });
  if (viewId === "historyView") refreshRuns().catch(toastError("历史运行加载失败"));
  if (viewId === "opportunityView") refreshOpportunities().catch(toastError("机会情报加载失败"));
  if (viewId === "subscriptionsView") refreshSubscriptions().catch(toastError("订阅加载失败"));
  if (viewId === "sourcesView") refreshSourcesPanel().catch(toastError("数据源加载失败"));
  if (viewId === "evaluationView") refreshEvaluation().catch(toastError("评测加载失败"));
  if (viewId === "memoryView") {
    trackActivity("weekly_report_view", { target: "memoryView", label: "用户记忆" });
    refreshMemoryWeekly().catch(toastError("用户记忆加载失败"));
  }
  if (viewId === "organizationView") {
    refreshOrganizationWorkspaces().catch(toastError("组织协作加载失败"));
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
  const feishuDelivery = item.feishu_delivery;
  const feishuState = feishuDelivery?.status
    ? `<span class="delivery-state delivery-${escapeHtml(feishuDelivery.status)}">飞书 ${escapeHtml(statusLabel(feishuDelivery.status))}</span>`
    : '<span class="delivery-state">飞书未发送</span>';
  el.latestDownload.hidden = false;
  el.latestDownload.className = "download-strip";
  el.latestDownload.innerHTML = `
    <div class="download-main">
      <strong title="${name}">${name}</strong>
      <span>${createdAt}${size}${runId ? ` · Run ${runId}` : ""}</span>
      ${feishuState}
    </div>
    <div class="action-group">
      <a class="link-button" href="${escapeHtml(downloadUrl)}" data-download-outbox-name="${name}">下载</a>
      <button class="ghost-button" type="button" data-send-feishu-name="${name}" data-send-feishu-run="${runId}">发送飞书</button>
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
    target.innerHTML = '<tr><td colspan="8" class="empty-cell">暂无订阅任务</td></tr>';
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
      const delivery = escapeHtml(subscriptionDeliveryText(item));
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
          <td><span class="table-main-value">${delivery}</span></td>
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
      const delivery = escapeHtml(subscriptionDeliveryText(item));
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
          <div class="compact-cell" role="cell" data-label="交付">
            <span class="cell-label">交付</span>
            <span class="cell-value">${delivery}</span>
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

function renderSourceAlerts(payload) {
  if (!el.sourceAlertSummary) return;
  const issues = Array.isArray(payload?.issues) ? payload.issues : [];
  const policy = payload?.policy || {};
  const deliveryReady = Boolean(payload?.delivery_ready);
  const taskReady = Boolean(payload?.task_ready);
  const taskAssigneeReady = Boolean(payload?.task_assignee_ready);
  const incidentSlaHours = Number(payload?.incident_sla_hours || 0);
  const incidentSummary = payload?.incident_summary || {};
  const latestIncident = incidentSummary.latest || null;
  const activeIncidentCount = Number(incidentSummary.active_count || 0);
  const hasActiveIncident = activeIncidentCount > 0 && latestIncident?.status !== "resolved";
  const incidentText = latestIncident
    ? `${sourceIncidentStatusLabel(latestIncident.status)} · ${escapeHtml((latestIncident.source_sites || []).join("、") || "来源事件")} · 截止 ${escapeHtml(compactDateTimeText(latestIncident.due_at))}`
    : "";
  el.sourceAlertSummary.className = `source-alert-summary ${issues.length ? "is-attention" : "is-healthy"}`;
  el.sourceAlertSummary.innerHTML = `
    <div>
      <span>${issues.length ? "来源 SLO 需要处理" : "来源 SLO 正常"}</span>
      <strong>${escapeHtml(payload?.source_count || 0)} 个来源 · ${escapeHtml(issues.length)} 个异常</strong>
      <small>可靠度阈值 ${escapeHtml(percent(policy.minimum_reliability || 0))} · 新鲜度 ${escapeHtml(policy.stale_hours || 0)} 小时${incidentSlaHours ? ` · 处置 SLA ${escapeHtml(incidentSlaHours)} 小时` : ""}</small>
      ${incidentText ? `<small class="source-incident-state">处置台账：${incidentText}</small>` : ""}
    </div>
    <div class="source-alert-actions">
      ${issues.slice(0, 3).map((issue) => `<span class="badge badge-${issue.severity === "critical" ? "fail" : "warn"}">${escapeHtml(issue.site)}</span>`).join("")}
      ${hasActiveIncident
        ? `<button id="syncSourceIncidentButton" class="primary-lite-button" type="button">同步处置状态</button>`
        : `<button id="createSourceIncidentTaskButton" class="primary-lite-button" type="button" ${issues.length ? "" : "disabled"} title="同一来源状态当天只创建一次">${taskReady ? (taskAssigneeReady ? "创建处置任务" : "创建未指派任务") : "配置飞书任务"}</button>`}
      <button id="sendSourceAlertButton" class="ghost-button" type="button" ${issues.length ? "" : "disabled"}>${deliveryReady ? "发送飞书告警" : "配置接收目标"}</button>
    </div>
  `;
  document.querySelector("#sendSourceAlertButton")?.addEventListener("click", () => {
    if (!deliveryReady) {
      showView("settingsView");
      showToast("请先在飞书连接中心选择默认接收目标");
      return;
    }
    sendSourceAlertsToFeishu().catch(toastError("来源告警发送失败"));
  });
  document.querySelector("#createSourceIncidentTaskButton")?.addEventListener("click", () => {
    if (!taskReady) {
      showView("settingsView");
      showToast("请先完成飞书消息应用配置");
      return;
    }
    createSourceIncidentTask().catch(toastError("来源处置任务创建失败"));
  });
  document.querySelector("#syncSourceIncidentButton")?.addEventListener("click", () => {
    syncSourceIncidentTasks().catch(toastError("来源处置状态同步失败"));
  });
}

function sourceIncidentStatusLabel(status) {
  return ({
    open: "处理中",
    overdue: "已超时",
    recovered_pending_close: "来源已恢复，待关闭任务",
    verification_failed: "任务已完成，来源仍异常",
    resolved: "已解决",
  })[status] || status || "未知状态";
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
      const access = sourceAccessStatus(item);
      const health = item.health || {};
      const rules = item.discovery_rules || {};
      const site = escapeHtml(rules.authority || item.site || "-");
      const engine = escapeHtml(item.engine || "-");
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
      const hitRate = health.hit_rate === null || health.hit_rate === undefined ? "-" : percent(health.hit_rate);
      const reliability = health.runs ? percent(health.reliability_score || 0) : "-";
      const healthStatus = escapeHtml(health.health_status || "unknown");
      return `
        <div class="source-row source-health-card">
          <div class="source-row-head">
            <strong>${site} · ${engine}</strong>
            <span>
              <span class="badge badge-${healthStatus}">${escapeHtml(statusLabel(health.health_status))}</span>
              <span class="badge badge-${escapeHtml(access.badge)}">${escapeHtml(access.label)}</span>
            </span>
          </div>
          <div class="source-health-grid">
            <span><strong>${escapeHtml(health.runs ?? 0)}</strong><small>真实尝试</small></span>
            <span><strong>${escapeHtml(health.notices ?? 0)}</strong><small>累计命中</small></span>
            <span><strong>${escapeHtml(successRate)}</strong><small>请求成功</small></span>
            <span><strong>${escapeHtml(hitRate)}</strong><small>运行命中</small></span>
            <span><strong>${escapeHtml(reliability)}</strong><small>可靠性</small></span>
            <span><strong>${escapeHtml(health.avg_elapsed_ms ?? 0)} ms</strong><small>平均延迟</small></span>
          </div>
          <span class="source-route-line">入口：${escapeHtml(routeSummary)}</span>
          <span class="source-rule-line">发现规则：allow ${escapeHtml(allowRules || "-")}；deny ${escapeHtml(denyRules || "-")}</span>
          <span class="source-rule-line">最近成功：${escapeHtml(compactDateTimeText(health.last_success_at) || "暂无")}；正确跳过 ${escapeHtml(health.skipped_runs ?? 0)} 次</span>
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
      summaryTile("金标准备度", percent(report.gold_coverage?.annotation_completion || 0)),
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
    const cases = report.gold?.cases || [];
    el.evaluationCases.className = cases.length ? "case-list" : "case-list empty-state";
    el.evaluationCases.innerHTML = cases.length
      ? cases
          .map(
            (item) => `
              <div class="case-row">
                <strong>${escapeHtml(item.id || "-")} · ${escapeHtml(statusLabel(item.status))}</strong>
                <span>${escapeHtml(item.query)}</span>
                <span>金标 ${escapeHtml(item.expected_count || 0)} · 召回 ${escapeHtml(item.retrieved_count || 0)} · Recall@10 ${item.status === "evaluated" ? percent(item.recall_at?.["10"] || 0) : "待标注"}</span>
              </div>
            `,
          )
          .join("")
      : "暂无用例";
  }
  if (el.evaluationHarnessCases) {
    const cases = report.harness?.cases || [];
    el.evaluationHarnessCases.className = cases.length ? "case-list" : "case-list empty-state";
    el.evaluationHarnessCases.innerHTML = cases.length
      ? cases.map((item) => `
          <div class="case-row">
            <strong>${escapeHtml(item.name)} · ${item.passed ? "通过" : "未通过"}</strong>
            <span>${escapeHtml(item.query)}</span>
            <span>字段：${escapeHtml(item.field_passed)} / ${escapeHtml(item.field_total)}</span>
          </div>
        `).join("")
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

function renderOpportunities(payload) {
  const items = payload?.items || [];
  const summary = payload?.summary || {};
  state.opportunities = items;
  state.opportunitySummaryData = summary;
  const visibleItems = items.slice(0, state.opportunityVisible);
  if (el.opportunitySummary) {
    const levels = summary.levels || {};
    const actionQueue = summary.action_queue || {};
    el.opportunitySummary.className = "opportunity-summary";
    el.opportunitySummary.innerHTML = [
      summaryTile("当前线索", summary.total ?? items.length),
      summaryTile("A 级机会", levels.A ?? 0),
      summaryTile("团队 / 关系待补", (actionQueue.team_incomplete || 0) + (actionQueue.stakeholder_incomplete || 0)),
      summaryTile("待管理决策", actionQueue.decision_pending ?? 0),
      summaryTile("协同逾期", (actionQueue.decision_overdue || 0) + (actionQueue.task_overdue || 0) + (actionQueue.relationship_action_overdue || 0) + (actionQueue.change_review_overdue || 0)),
      summaryTile("Go 通过率", actionQueue.go_rate == null ? "-" : `${actionQueue.go_rate}%`),
    ].join("");
    renderOpportunityDecisionBoard(actionQueue);
  }
  if (!el.opportunityList) return;
  if (el.opportunityMarket) {
    const market = summary.market || {};
    const budget = market.budget || {};
    const purchaser = market.top_purchasers?.[0];
    const learning = market.outcome_learning || {};
    const topLossReason = learning.loss_reasons?.[0];
    el.opportunityMarket.className = "opportunity-market";
    el.opportunityMarket.innerHTML = [
      marketInsight("价格样本", market.budget_sample_count || 0, `${market.budget_coverage || 0}% 预算覆盖`),
      marketInsight("历史中位数", formatCny(budget.median_cny), `区间 ${formatCny(budget.min_cny)} - ${formatCny(budget.max_cny)}`),
      marketInsight("重点客户", purchaser?.name || "样本不足", purchaser ? `${purchaser.count} 条关联公告` : "待补充采购人"),
      marketInsight("复盘样本", learning.sample_count || 0, learning.win_rate == null ? "尚未形成胜率" : `胜率 ${learning.win_rate}%${topLossReason ? ` · ${topLossReason.name}` : ""}`),
    ].join("");
    if (el.opportunityTopicFilter) {
      const selected = market.selected_category || "";
      const categories = market.available_categories || [];
      el.opportunityTopicFilter.innerHTML = [
        '<option value="">全部品类</option>',
        ...categories.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${Number(item.count) || 0}</option>`),
      ].join("");
      el.opportunityTopicFilter.value = selected;
    }
  }
  el.opportunityList.className = items.length
    ? "opportunity-ledger-body"
    : "opportunity-ledger-body empty-state";
  el.opportunityList.innerHTML = items.length
    ? visibleItems
        .map((item) => {
          const intelligence = item.intelligence || {};
          const workflow = item.workflow || {};
          const actionState = item.action_state || {};
          const changeSummary = item.change_summary || {};
          const changeReview = item.change_review || {};
          const scores = intelligence.scores || {};
          const trust = intelligence.trust_assessment || {};
          const risks = Array.isArray(intelligence.risks) ? intelligence.risks : [];
          const qualification = item.qualification || {};
          const decision = workflow.decision || "pending";
          const actionSignal = changeReview.overdue
            ? `<small class="action-signal action-signal-danger">重大变更复核已逾期 · ${escapeHtml(changeReview.pending_count || 0)} 条</small>`
            : Number(changeReview.pending_count) > 0
            ? `<small class="action-signal action-signal-warning">重大变更待复核 · ${escapeHtml(changeReview.pending_count)} 条</small>`
            : actionState.feishu_task_overdue
            ? '<small class="action-signal action-signal-danger">飞书任务已逾期</small>'
            : Number(changeSummary.count) > 0
            ? `<small class="action-signal action-signal-warning">公告已修订 ${escapeHtml(changeSummary.count)} 次 · ${escapeHtml((changeSummary.changed_fields || []).map(noticeChangeFieldLabel).slice(0, 2).join("、"))}</small>`
            : actionState.decision_sla_status === "overdue"
            ? `<small class="action-signal action-signal-danger">决策已超时 ${escapeHtml(actionState.decision_wait_hours || 0)} 小时</small>`
            : actionState.decision_sla_status === "due_soon"
              ? `<small class="action-signal">决策剩余 ${escapeHtml(actionState.decision_remaining_hours || 0)} 小时</small>`
            : actionState.due_soon
            ? `<small class="action-signal">距截止 ${escapeHtml(actionState.days_to_deadline)} 天</small>`
            : actionState.owner_required && ["A", "B"].includes(intelligence.level)
              ? '<small class="action-signal">重点机会待认领</small>'
              : qualification.status === "ready" && decision === "pending"
                ? '<small class="action-signal">准入就绪 · 待 Go 决策</small>'
                : qualification.status === "blocked"
                  ? `<small class="action-signal action-signal-warning">准入待补 ${qualificationBlockerCount(qualification)} 项</small>`
              : "";
          return `
            <article class="opportunity-row" role="row">
              <div class="opportunity-grade grade-${escapeHtml(String(intelligence.level || "D").toLowerCase())}">
                <strong>${escapeHtml(intelligence.level || "D")}</strong>
                <span>${escapeHtml(intelligence.score ?? 0)} 分</span>
              </div>
              <div class="opportunity-project">
                <strong title="${escapeHtml(item.title || "")}">${escapeHtml(item.title || "未命名机会")}</strong>
                <span>${escapeHtml(item.source_site || "未知来源")} · ${escapeHtml(trust.verification_label || "证据待核验")} · ${escapeHtml(item.publish_time || "时间待确认")}</span>
              </div>
              <div class="opportunity-customer">
                <strong>${escapeHtml(item.purchaser || "采购人待确认")}</strong>
                <span>${escapeHtml(item.region || "地区待确认")} · ${escapeHtml(item.budget || "预算待确认")}</span>
              </div>
              <div class="opportunity-quality">
                ${qualityBar("时效", scores.freshness || 0)}
                ${qualityBar("完整", scores.completeness || 0)}
                ${qualityBar("可信", scores.credibility || 0)}
              </div>
              <div class="opportunity-strategy">
                <strong>${escapeHtml(workflow.stage_label || "线索识别")}</strong>
                <span>${escapeHtml(intelligence.project_target || "目标待确认")}</span>
                ${actionSignal}
                ${workflow.owner_name ? `<small>负责人：${escapeHtml(workflow.owner_name)}</small>` : ""}
                ${risks.length ? `<small>${escapeHtml(risks[0])}</small>` : ""}
              </div>
              <div class="opportunity-actions">
                <button class="primary-lite-button" type="button" data-send-opportunity-feishu="${escapeHtml(item.notice_id)}">${collaborationButtonLabel(workflow)}</button>
                <button class="text-link" type="button" data-view-opportunity="${escapeHtml(item.notice_id)}">数字档案</button>
              </div>
            </article>
          `;
        })
        .join("")
    : "本地知识库暂无可研判公告，请先运行检索或启用后台采集。";
  if (el.opportunityFooter && el.opportunityListHint && el.loadMoreOpportunitiesButton) {
    el.opportunityFooter.hidden = !items.length;
    el.opportunityListHint.textContent = `已展示 ${visibleItems.length} / ${items.length} 条机会`;
    el.loadMoreOpportunitiesButton.hidden = visibleItems.length >= items.length;
  }
}

function openOpportunityDetail(noticeId) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityDetailDialog || !el.opportunityDetailContent) return;
  const intelligence = item.intelligence || {};
  const workflow = item.workflow || {};
  const qualification = item.qualification || {};
  const actionState = item.action_state || {};
  const changeSummary = item.change_summary || {};
  const changeReview = item.change_review || {};
  const changedFields = Array.isArray(changeSummary.changed_fields)
    ? changeSummary.changed_fields
    : [];
  const qualificationGates = Array.isArray(qualification.gates) ? qualification.gates : [];
  const approvalBlockers = qualificationBlockers(qualification, "approve_bid");
  const scores = intelligence.scores || {};
  const trust = intelligence.trust_assessment || {};
  const trustComponents = Array.isArray(trust.components) ? trust.components : [];
  const market = intelligence.market_context || {};
  const benchmark = market.benchmark || {};
  const competition = intelligence.competition || market.competition || {};
  const review = intelligence.requirement_review || {};
  const dimensions = Array.isArray(review.dimensions) ? review.dimensions : [];
  const recommendations = Array.isArray(review.recommendations) ? review.recommendations : [];
  const actions = Array.isArray(intelligence.recommended_actions) ? intelligence.recommended_actions : [];
  const risks = Array.isArray(intelligence.risks) ? intelligence.risks : [];
  const suppliers = Array.isArray(competition.historical_suppliers)
    ? competition.historical_suppliers
    : [];
  const confirmedCompetitors = Array.isArray(competition.confirmed_competitors)
    ? competition.confirmed_competitors
    : [];
  const outcome = item.outcome || {};
  const factOverrides = Array.isArray(item.fact_overrides) ? item.fact_overrides : [];
  const team = item.team || {};
  const teamMembers = Array.isArray(team.members) ? team.members : [];
  const missingTeamRoles = Array.isArray(team.missing_roles) ? team.missing_roles : [];
  const stakeholderMap = item.stakeholder_map || {};
  const stakeholders = Array.isArray(stakeholderMap.stakeholders)
    ? stakeholderMap.stakeholders
    : [];
  const stakeholderRisks = Array.isArray(stakeholderMap.risks)
    ? stakeholderMap.risks
    : [];
  const stakeholderActions = Array.isArray(stakeholderMap.strategy_actions)
    ? stakeholderMap.strategy_actions
    : [];
  const missingStakeholderRoles = Array.isArray(stakeholderMap.missing_roles)
    ? stakeholderMap.missing_roles
    : [];
  const relationshipActionPlan = item.relationship_actions || {};
  const relationshipActionItems = Array.isArray(relationshipActionPlan.items)
    ? relationshipActionPlan.items
    : [];
  el.opportunityDetailTitle.textContent = item.title || "档案详情";
  el.opportunityDetailContent.innerHTML = `
    <div class="opportunity-detail-hero">
      <div class="opportunity-detail-grade grade-${escapeHtml(String(intelligence.level || "D").toLowerCase())}">
        <strong>${escapeHtml(intelligence.level || "D")}</strong><span>${escapeHtml(intelligence.score || 0)} 分</span>
      </div>
      <div>
        <strong>${escapeHtml(workflow.stage_label || "线索识别")}</strong>
        <span>${escapeHtml(item.purchaser || "采购人待确认")} · ${escapeHtml(item.region || "地区待确认")}</span>
        <small>${escapeHtml(workflow.owner_name || "负责人待认领")} · ${escapeHtml(item.source_site || "未知来源")} · ${escapeHtml(item.publish_time || "时间待确认")}</small>
      </div>
    </div>
    <div class="opportunity-detail-metrics">
      ${detailMetric("时效", scores.freshness || 0)}
      ${detailMetric("完整", scores.completeness || 0)}
      ${detailMetric("可信", scores.credibility || 0)}
      ${detailMetric("需求覆盖", review.coverage_score || 0)}
    </div>
    <section class="opportunity-detail-section trust-assessment-section">
      <div class="opportunity-detail-section-title">
        <h3>来源与证据可信度</h3>
        <span>${escapeHtml(trust.verification_label || "证据待核验")} · ${escapeHtml(trust.level_label || "待核验")}</span>
      </div>
      <div class="trust-component-grid">
        ${trustComponents.map((component) => `
          <div class="trust-component">
            <span>${escapeHtml(component.label || "未命名维度")}</span>
            <strong>${escapeHtml(component.score || 0)} / ${escapeHtml(component.maximum || 0)}</strong>
            <small>${escapeHtml(component.evidence || "暂无依据")}</small>
          </div>
        `).join("")}
      </div>
      ${detailLine("权威来源", trust.authority || item.source_site || "来源未分类")}
      ${detailLine("独立来源", `${trust.source_count || 1} 个${trust.source_count >= 2 ? "，已交叉印证" : "，尚无跨源印证"}`)}
    </section>
    <section class="opportunity-detail-section opportunity-team-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>协作团队</h3>
          <small>${escapeHtml(team.member_count || 0)} 名成员 · ${escapeHtml(team.partner_count || 0)} 名伙伴</small>
        </div>
        <div class="opportunity-team-heading-actions">
          <span class="team-coverage-state ${missingTeamRoles.length ? "is-incomplete" : "is-ready"}">${escapeHtml(team.coverage_score ?? 0)}% 覆盖</span>
          <button class="primary-lite-button" type="button" data-add-opportunity-team="${escapeHtml(item.notice_id)}">添加成员</button>
        </div>
      </div>
      ${missingTeamRoles.length ? `<p class="team-coverage-gap">当前阶段待补：${escapeHtml(missingTeamRoles.join("、"))}</p>` : '<p class="team-coverage-gap is-ready">当前阶段核心角色已覆盖。</p>'}
      <div class="opportunity-team-list">
        <div class="opportunity-team-member is-owner">
          <div><strong>${escapeHtml(workflow.owner_name || "待认领")}</strong><span>机会负责人</span></div>
          <small>${workflow.owner_open_id ? "已绑定飞书成员" : "尚未绑定飞书成员"}</small>
        </div>
        ${teamMembers.map(opportunityTeamMemberRow).join("")}
      </div>
    </section>
    <section class="opportunity-detail-section opportunity-stakeholder-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>客户关系图谱</h3>
          <small>${escapeHtml(stakeholderMap.stakeholder_count || 0)} 名关键人 · ${escapeHtml(stakeholderRisks.length)} 项风险</small>
        </div>
        <div class="stakeholder-heading-actions">
          <span class="stakeholder-health-state risk-${escapeHtml(stakeholderMap.risk_level || "normal")}">${escapeHtml(stakeholderMap.coverage_score ?? 0)}% 覆盖 · ${escapeHtml(stakeholderMap.relationship_score ?? 0)} 健康</span>
          <button class="primary-lite-button" type="button" data-add-opportunity-stakeholder="${escapeHtml(item.notice_id)}">添加关键人</button>
        </div>
      </div>
      ${missingStakeholderRoles.length ? `<p class="stakeholder-gap">当前阶段待识别：${escapeHtml(missingStakeholderRoles.join("、"))}</p>` : '<p class="stakeholder-gap is-ready">当前阶段关键关系已覆盖。</p>'}
      <div class="stakeholder-matrix" role="table" aria-label="客户关键人关系图谱">
        <div class="stakeholder-matrix-head" role="row">
          <span>关键人 / 角色</span><span>影响与立场</span><span>关系</span><span>责任与行动</span><span>操作</span>
        </div>
        <div class="stakeholder-matrix-body">
          ${stakeholders.length ? stakeholders.map(opportunityStakeholderRow).join("") : '<div class="stakeholder-empty">尚未录入可验证的客户关键人</div>'}
        </div>
      </div>
      ${stakeholderRisks.length ? `<div class="stakeholder-risk-list">${stakeholderRisks.map((risk) => `<p class="risk-${escapeHtml(risk.level || "warning")}">${escapeHtml(risk.message || "关系风险待核对")}</p>`).join("")}</div>` : ""}
      ${stakeholderActions.length ? `<div class="stakeholder-strategy-list">${stakeholderActions.map((action) => `<p>${escapeHtml(action)}</p>`).join("")}</div>` : ""}
    </section>
    <section class="opportunity-detail-section relationship-action-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>关系行动计划</h3>
          <small>${escapeHtml(relationshipActionPlan.open_count || 0)} 项待办 · ${escapeHtml(relationshipActionPlan.completed_count || 0)} 项完成</small>
        </div>
        <div class="relationship-action-heading-actions">
          <span class="relationship-action-health ${Number(relationshipActionPlan.overdue_count) ? "is-overdue" : ""}">${escapeHtml(relationshipActionPlan.completion_rate || 0)}% 闭环 · ${escapeHtml(relationshipActionPlan.overdue_count || 0)} 逾期</span>
          <button class="primary-lite-button" type="button" data-add-relationship-action="${escapeHtml(item.notice_id)}">创建行动</button>
        </div>
      </div>
      <div class="relationship-action-signals">
        <span>未指派 <strong>${escapeHtml(relationshipActionPlan.unassigned_count || 0)}</strong></span>
        <span>结果待补 <strong>${escapeHtml(relationshipActionPlan.outcome_pending_count || 0)}</strong></span>
        <span>飞书同步 <strong>${escapeHtml(relationshipActionItems.filter((action) => action.feishu_task_guid).length)}</strong></span>
      </div>
      <div class="relationship-action-matrix" role="table" aria-label="客户关系行动计划">
        <div class="relationship-action-matrix-head" role="row">
          <span>行动 / 关键人</span><span>责任人</span><span>截止时间</span><span>状态</span><span>操作</span>
        </div>
        <div class="relationship-action-matrix-body">
          ${relationshipActionItems.length ? relationshipActionItems.map((action) => opportunityRelationshipActionRow(action, item.notice_id)).join("") : '<div class="relationship-action-empty">把关系策略转成有负责人、有时限、可回写的行动</div>'}
        </div>
      </div>
    </section>
    <section class="opportunity-detail-section opportunity-change-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>档案时间线</h3>
          <small>公告、附件、关键事实与决策影响均保留版本依据</small>
        </div>
        <span>${Number(changeSummary.count) > 0 ? `累计 ${escapeHtml(changeSummary.count)} 次修订` : "当前为首个版本"}</span>
      </div>
      <div class="opportunity-archive-current">
        <span>当前有效版本</span>
        <strong>${escapeHtml(item.publish_time || "发布时间待确认")}</strong>
        <small>${escapeHtml(item.source_site || "未知来源")} · ${escapeHtml(item.project_no || "项目编号待确认")} · 截止 ${escapeHtml(item.bid_deadline || "待确认")}</small>
      </div>
      ${changeImpactPanel(changedFields, changeReview)}
      <div class="opportunity-revision-history" data-opportunity-revisions="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在加载完整版本记录</div>
      </div>
      ${Number(changeSummary.count) > 0 ? `
        ${Number(changeReview.pending_count) > 0 ? `
          <div class="change-review-status ${changeReview.overdue ? "is-overdue" : ""}">
            <div>
              <strong>${changeReview.overdue ? "复核已逾期" : "需要负责人复核"}</strong>
              <span>${escapeHtml(changeReview.pending_count)} 条重大变更 · 截止 ${escapeHtml(changeReview.required_by || "-")}</span>
            </div>
            <small>原决策已失效，确认复核后需要重新完成 Go/Hold/No-Go 判断。</small>
          </div>
        ` : changeReview.acknowledged_at ? `<p class="change-review-acknowledged">最近复核：${escapeHtml(changeReview.acknowledged_by || "-")} · ${escapeHtml(changeReview.acknowledged_at)}</p>` : ""}
      ` : ""}
    </section>
    <section class="opportunity-detail-section opportunity-facts-section">
      <div class="opportunity-detail-section-title">
        <h3>事实核验</h3>
        <span>${escapeHtml(factOverrides.length)} 项已核验</span>
      </div>
      <form class="opportunity-facts-form" data-opportunity-facts="${escapeHtml(item.notice_id)}">
        <div class="opportunity-facts-grid">
          ${opportunityFactInput("采购主体", "purchaser", item.purchaser)}
          ${opportunityFactInput("项目编号", "project_no", item.project_no)}
          ${opportunityFactInput("预算", "budget", item.budget)}
          ${opportunityFactInput("投标截止", "bid_deadline", item.bid_deadline, "date")}
          ${opportunityFactInput("地区", "region", item.region)}
        </div>
        <div class="opportunity-fact-provenance">
          <label class="fact-source-field">
            <span>证据链接</span>
            <input name="source_url" type="url" value="${escapeHtml(item.source_url || "")}" required />
          </label>
          <label>
            <span>证据摘录</span>
            <textarea name="evidence_text" rows="2" maxlength="2000" placeholder="原文中的对应事实"></textarea>
          </label>
          <label>
            <span>核验备注</span>
            <input name="note" maxlength="1000" placeholder="核验依据或更正原因" />
          </label>
        </div>
        <div class="opportunity-fact-footer">
          <div class="verified-fact-list">
            ${factOverrides.length ? factOverrides.map(verifiedFactTag).join("") : "<span>暂无人工核验记录</span>"}
          </div>
          <button class="primary-lite-button" type="submit">保存并重新研判</button>
        </div>
      </form>
    </section>
    <section class="opportunity-detail-section opportunity-requirements-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>投标要求账本</h3>
          <small>每条要求均需保留原文、定位、责任与处理状态</small>
        </div>
        <span>人工维护</span>
      </div>
      <div class="opportunity-requirement-ledger" data-opportunity-requirements="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在加载要求账本</div>
      </div>
    </section>
    <section class="opportunity-detail-section">
      <h3>市场与竞争</h3>
      ${detailLine("价格位置", benchmark.message || "同品类预算样本不足")}
      ${detailLine("竞争结论", competition.message || "同品类结果样本不足")}
      ${suppliers.length ? detailLine("历史竞争者", suppliers.slice(0, 4).map((value) => `${value.name}（${value.count} 次）`).join("、")) : ""}
      ${confirmedCompetitors.length ? detailLine("内部复盘确认", confirmedCompetitors.slice(0, 4).map((value) => `${value.name}（${value.count} 次）`).join("、")) : ""}
      ${competition.evidence_excerpt ? `<blockquote>${escapeHtml(competition.evidence_excerpt)}</blockquote>` : ""}
    </section>
    ${outcome.result ? `
      <section class="opportunity-detail-section outcome-review-section">
        <div class="opportunity-detail-section-title">
          <div>
            <h3>投标结果复盘</h3>
            <small>${escapeHtml(outcome.recorded_by || "记录人待确认")} · ${escapeHtml(outcome.finalized_at || "时间待确认")}</small>
          </div>
          <button class="primary-lite-button" type="button" data-edit-opportunity-outcome="${escapeHtml(item.notice_id)}">修订复盘</button>
        </div>
        <div class="outcome-review-hero result-${escapeHtml(outcome.result)}">
          <strong>${outcome.result === "won" ? "已中标" : "未中标"}</strong>
          <span>${escapeHtml(outcome.reason_label || "主因待确认")}</span>
        </div>
        ${detailLine("中标供应商", outcome.winner_name || "未披露")}
        ${detailLine("成交金额", outcome.award_amount ? `${formatNumber(outcome.award_amount)} ${outcome.currency || ""}` : "未披露")}
        ${detailLine("结果结论", outcome.summary)}
        ${detailLine("经验沉淀", outcome.lessons)}
        ${outcome.customer_feedback ? detailLine("客户反馈", outcome.customer_feedback) : ""}
        ${outcome.follow_up_action ? detailLine("后续行动", outcome.follow_up_action) : ""}
        ${outcome.evidence_url ? `<a class="text-link" href="${escapeHtml(outcome.evidence_url)}" target="_blank" rel="noreferrer">查看结果证据</a>` : ""}
        ${outcome.evidence_text ? `<blockquote>${escapeHtml(outcome.evidence_text)}</blockquote>` : ""}
      </section>
    ` : ""}
    <section class="opportunity-detail-section">
      <div class="opportunity-detail-section-title"><h3>需求覆盖</h3><span>${escapeHtml(review.covered_count || 0)} / ${escapeHtml(review.total_count || 0)} 项</span></div>
      <div class="requirement-dimensions">
        ${dimensions.map((value) => `
          <div class="requirement-${value.status === "covered" ? "covered" : "verify"}">
            <span>${value.status === "covered" ? "已覆盖" : "待核对"}</span>
            <strong>${escapeHtml(value.name || "未命名维度")}</strong>
          </div>
        `).join("")}
      </div>
      ${recommendations.length ? `<div class="opportunity-detail-advice">${recommendations.map((value) => `<p>${escapeHtml(value)}</p>`).join("")}</div>` : ""}
      <small class="opportunity-detail-basis">${escapeHtml(review.basis || "")}</small>
    </section>
    <section class="opportunity-detail-section">
      <h3>目标与行动</h3>
      ${detailLine("项目目标", intelligence.project_target || "待确认")}
      ${detailLine("建议策略", intelligence.strategy || "待确认")}
      <div class="opportunity-detail-actions-list">
        ${actions.map((value) => `<p><span>${escapeHtml(value.role || "负责人")}</span><strong>${escapeHtml(value.action || "")}</strong></p>`).join("")}
      </div>
      ${risks.length ? `<div class="opportunity-detail-risks">${risks.map((value) => `<p>${escapeHtml(value)}</p>`).join("")}</div>` : ""}
    </section>
    <section class="opportunity-detail-section qualification-section">
      <div class="opportunity-detail-section-title">
        <h3>销售准入与投标决策</h3>
        <span class="qualification-state qualification-${escapeHtml(qualification.status || "blocked")}">${escapeHtml(qualificationStatusLabel(qualification.status))}</span>
      </div>
      <div class="qualification-summary">
        ${detailMetric("资格评分", qualification.score || 0)}
        ${detailMetric("系统建议", decisionLabel(qualification.recommended_decision))}
        ${detailMetric("人工决策", decisionLabel(workflow.decision))}
      </div>
      <div class="qualification-gates">
        ${qualificationGates.map((gate) => `
          <div class="qualification-gate gate-${gate.status === "passed" ? "passed" : "blocked"}">
            <span>${gate.status === "passed" ? "通过" : "待补"}</span>
            <strong>${escapeHtml(gate.label || "未命名门禁")}</strong>
            <small>${escapeHtml(gate.actual || "未识别")} · ${escapeHtml(gate.requirement || "")}</small>
          </div>
        `).join("")}
      </div>
      ${approvalBlockers.length ? `<p class="qualification-blockers">Go 决策前需补齐：${escapeHtml(approvalBlockers.join("、"))}</p>` : '<p class="qualification-blockers qualification-ready">资料门禁已满足，可以提交 Go 决策。</p>'}
      ${workflow.decision_reason ? detailLine("决策依据", workflow.decision_reason) : ""}
      ${workflow.decision_by ? detailLine("决策记录", `${workflow.decision_by}${workflow.decision_at ? ` · ${workflow.decision_at}` : ""}`) : ""}
      ${actionState.decision_required ? detailLine("决策 SLA", decisionSlaLabel(actionState)) : ""}
      <div class="qualification-decision-actions">
        ${opportunityActionButtons(item)}
      </div>
    </section>
    <section class="opportunity-detail-section">
      <h3>飞书协同</h3>
      ${detailLine("销售阶段", workflow.stage_label || "线索识别")}
      ${detailLine("机会负责人", workflow.owner_name || "待认领")}
      ${detailLine("下一步行动", workflow.next_action || "启动协同后自动生成")}
      ${detailLine("任务状态", feishuTaskStatusLabel(workflow))}
      ${workflow.feishu_task_completed_at ? detailLine("完成时间", workflow.feishu_task_completed_at) : ""}
      ${workflow.feishu_task_synced_at ? detailLine("最近同步", workflow.feishu_task_synced_at) : ""}
      ${detailLine("截止日程", workflow.feishu_event_id ? "已创建" : (item.bid_deadline ? "待创建" : "未识别截止时间"))}
    </section>
    <div class="opportunity-detail-footer">
      <button class="primary-lite-button" type="button" data-send-opportunity-feishu="${escapeHtml(item.notice_id)}">${collaborationButtonLabel(workflow)}</button>
      ${item.source_url ? `<a class="ghost-button" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">查看原文</a>` : ""}
    </div>
  `;
  if (!el.opportunityDetailDialog.open) el.opportunityDetailDialog.showModal();
  loadOpportunityRevisionHistory(noticeId).catch((error) => {
    const container = currentOpportunityRevisionContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">版本记录加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityRequirements(noticeId).catch((error) => {
    const container = currentOpportunityRequirementContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">要求账本加载失败：${escapeHtml(error.message || error)}</div>`;
  });
}

function opportunityFactInput(label, name, value, type = "text") {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input name="${escapeHtml(name)}" type="${escapeHtml(type)}" value="${escapeHtml(value || "")}" />
    </label>
  `;
}

function verifiedFactTag(item) {
  return `
    <span title="${escapeHtml(`${item.actor || "系统"} · ${item.updated_at || ""}`)}">
      ${escapeHtml(item.field_label || item.field_name)}：${escapeHtml(item.field_value || "-")}
    </span>
  `;
}

function detailMetric(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function opportunityTeamMemberRow(member) {
  const organization = member.organization_type === "partner"
    ? (member.organization_name || "合作伙伴")
    : "内部团队";
  return `
    <div class="opportunity-team-member">
      <div>
        <strong>${escapeHtml(member.member_name || "未命名成员")}</strong>
        <span>${escapeHtml(member.role_label || member.role || "协作成员")} · ${escapeHtml(organization)}</span>
        ${member.responsibility ? `<small>${escapeHtml(member.responsibility)}</small>` : ""}
      </div>
      <div class="opportunity-team-member-status">
        <span>${escapeHtml(teamSyncLabel(member.feishu_sync_status, member.member_open_id))}</span>
        <button class="icon-close-button team-remove-button" type="button" aria-label="移除成员" data-remove-opportunity-team="${escapeHtml(member.id || "")}" data-opportunity-id="${escapeHtml(member.notice_id || "")}">×</button>
      </div>
    </div>
  `;
}

function opportunityStakeholderRow(stakeholder) {
  const evidence = [stakeholder.evidence_source, stakeholder.evidence_text]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="stakeholder-matrix-row" role="row">
      <div>
        <strong>${escapeHtml(stakeholder.stakeholder_name || "未命名关键人")}</strong>
        <span>${escapeHtml(stakeholder.role_label || stakeholder.role || "角色待确认")}${stakeholder.job_title ? ` · ${escapeHtml(stakeholder.job_title)}` : ""}</span>
        ${stakeholder.organization_name ? `<small>${escapeHtml(stakeholder.organization_name)}</small>` : ""}
      </div>
      <div><strong>影响${escapeHtml(stakeholder.influence_label || "待确认")}</strong><span class="stance-${escapeHtml(stakeholder.stance || "unknown")}">${escapeHtml(stakeholder.stance_label || "待确认")}</span></div>
      <div><strong>${escapeHtml(stakeholder.relationship_label || "未建立")}</strong><small title="${escapeHtml(evidence)}">${escapeHtml(stakeholder.evidence_source || "证据待补")}</small></div>
      <div><strong>${escapeHtml(stakeholder.owner_member_name || "责任人待分配")}</strong><span>${escapeHtml(stakeholder.next_action || "行动待明确")}</span></div>
      <div class="stakeholder-row-actions">
        <button class="icon-close-button stakeholder-action-button" type="button" aria-label="为该关键人创建行动" title="创建关系行动" data-create-stakeholder-action="${escapeHtml(stakeholder.id || "")}" data-opportunity-id="${escapeHtml(stakeholder.notice_id || "")}">+</button>
        <button class="icon-close-button stakeholder-remove-button" type="button" aria-label="移除关键人" data-remove-opportunity-stakeholder="${escapeHtml(stakeholder.id || "")}" data-opportunity-id="${escapeHtml(stakeholder.notice_id || "")}">×</button>
      </div>
    </div>
  `;
}

function opportunityRelationshipActionRow(action, noticeId) {
  const effectiveStatus = action.effective_status || action.status || "open";
  const statusLabel = {
    open: "进行中",
    overdue: "已逾期",
    completed: action.outcome_note ? "已闭环" : "结果待补",
    cancelled: "已取消",
  }[effectiveStatus] || "待处理";
  const remoteLabel = action.feishu_task_guid
    ? `飞书 ${action.feishu_task_status === "completed" ? "已完成" : "已同步"}`
    : action.feishu_sync_error
      ? "飞书待重试"
      : "仅本地";
  const operations = [];
  if (action.status === "open" && !action.feishu_task_guid) {
    operations.push(`<button class="text-link" type="button" data-sync-relationship-action="${escapeHtml(action.id)}" data-opportunity-id="${escapeHtml(noticeId)}">同步飞书</button>`);
    operations.push(`<button class="text-link" type="button" data-complete-relationship-action="${escapeHtml(action.id)}" data-opportunity-id="${escapeHtml(noticeId)}">完成</button>`);
  }
  if (action.status === "completed" && !action.outcome_note) {
    operations.push(`<button class="text-link" type="button" data-complete-relationship-action="${escapeHtml(action.id)}" data-opportunity-id="${escapeHtml(noticeId)}">补结果</button>`);
  }
  return `
    <div class="relationship-action-row status-${escapeHtml(effectiveStatus)}" role="row">
      <div><strong>${escapeHtml(action.title || "未命名行动")}</strong><span>${escapeHtml(action.stakeholder_name || action.action_type_label || "通用关系行动")}</span></div>
      <div><strong>${escapeHtml(action.assignee_member_name || "待分配")}</strong><span>${escapeHtml(action.priority_label || "普通")}优先</span></div>
      <div><strong>${escapeHtml(compactDateTimeText(action.due_at || "-"))}</strong><span>${escapeHtml(remoteLabel)}</span></div>
      <div><strong>${escapeHtml(statusLabel)}</strong>${action.outcome_note ? `<span title="${escapeHtml(action.outcome_note)}">结果已记录</span>` : ""}</div>
      <div class="relationship-action-row-actions">${operations.join("") || "<span>—</span>"}</div>
    </div>
  `;
}

function teamSyncLabel(status, openId) {
  if (!openId) return "仅本地记录";
  if (status === "synced") return "已同步 Task";
  if (status === "failed") return "同步待重试";
  return "等待 Task 同步";
}

function detailLine(label, value) {
  return `<div class="opportunity-detail-line"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function qualificationBlockers(qualification, action) {
  const blockers = qualification?.blockers?.[action];
  return Array.isArray(blockers) ? blockers : [];
}

function qualificationBlockerCount(qualification) {
  return qualificationBlockers(qualification, "approve_bid").length;
}

function qualificationStatusLabel(status) {
  return status === "ready" ? "可决策" : "有阻断项";
}

function decisionLabel(decision) {
  return { go: "Go", hold: "Hold", no_go: "No-Go", pending: "待决策" }[decision] || "待决策";
}

function feishuTaskStatusLabel(workflow) {
  if (!workflow.feishu_task_guid) return "待创建";
  return {
    open: "进行中",
    overdue: "已逾期",
    completed: "已完成",
    not_created: "待创建",
  }[workflow.feishu_task_status] || "待同步";
}

function collaborationButtonLabel(workflow) {
  if (!workflow.owner_name) return "分配负责人";
  if (!workflow.feishu_task_guid) return "启动协同";
  return "同步协同";
}

function decisionSlaLabel(actionState) {
  const status = actionState.decision_sla_status;
  if (status === "overdue") return `已超时 · 已等待 ${actionState.decision_wait_hours || 0} 小时`;
  if (status === "due_soon") return `即将到期 · 剩余 ${actionState.decision_remaining_hours || 0} 小时`;
  if (status === "on_track") return `计时中 · 截止 ${actionState.decision_due_at || "-"}`;
  return "计时起点待确认";
}

function escalationIssueLabel(item) {
  const labels = { decision: "决策超时", task: "任务逾期", relationship_action: "关系行动逾期", change_review: "变更复核逾期" };
  const rawType = String(item.issue_type || "decision");
  const types = Array.isArray(item.issue_types)
    ? item.issue_types
    : Object.keys(labels).filter((value) => rawType.includes(value));
  return types.map((value) => labels[value]).filter(Boolean).join(" + ") || "协同逾期";
}

function renderOpportunityDecisionBoard(actionQueue) {
  if (!el.opportunityDecisionBoard) return;
  const decisions = actionQueue.decisions || {};
  const stages = actionQueue.stage_counts || {};
  const allEscalations = Array.isArray(actionQueue.escalations) ? actionQueue.escalations : [];
  const escalations = allEscalations.slice(0, 5);
  el.opportunityDecisionBoard.className = "opportunity-decision-board";
  el.opportunityDecisionBoard.innerHTML = `
    <section>
      <span class="decision-board-kicker">资格与决策</span>
      <strong>${escapeHtml(actionQueue.qualification_ready || 0)} 条可决策</strong>
      <div class="decision-board-lines">
        ${decisionBoardLine("阻断待补", actionQueue.qualification_blocked || 0)}
        ${decisionBoardLine("关键关系待补", actionQueue.stakeholder_incomplete || 0)}
        ${decisionBoardLine("关键关系高风险", actionQueue.stakeholder_critical || 0, actionQueue.stakeholder_critical ? "danger" : "")}
        ${decisionBoardLine("关系行动逾期", actionQueue.relationship_action_overdue || 0, actionQueue.relationship_action_overdue ? "danger" : "")}
        ${decisionBoardLine("行动结果待补", actionQueue.relationship_action_outcome_pending || 0)}
        ${decisionBoardLine("公告变更待复核", actionQueue.change_review_pending || 0, actionQueue.change_review_overdue ? "danger" : "")}
        ${decisionBoardLine("待管理决策", actionQueue.decision_pending || 0)}
        ${decisionBoardLine(`超过 ${actionQueue.decision_sla_hours || 0} 小时`, actionQueue.decision_overdue || 0, actionQueue.decision_overdue ? "danger" : "")}
      </div>
    </section>
    <section>
      <span class="decision-board-kicker">决策与转化</span>
      <strong>${actionQueue.go_rate == null ? "暂无闭环决策" : `Go 通过率 ${escapeHtml(actionQueue.go_rate)}%`}</strong>
      <div class="decision-board-pipeline">
        ${decisionPipelineValue("Go", decisions.go || 0, "go")}
        ${decisionPipelineValue("Hold", decisions.hold || 0, "hold")}
        ${decisionPipelineValue("No-Go", decisions.no_go || 0, "no-go")}
      </div>
      <small>主任务：进行 ${escapeHtml(actionQueue.task_open || 0)} · 完成 ${escapeHtml(actionQueue.task_completed || 0)} · 逾期 ${escapeHtml(actionQueue.task_overdue || 0)}；关系行动：进行 ${escapeHtml(actionQueue.relationship_action_open || 0)} · 完成 ${escapeHtml(actionQueue.relationship_action_completed || 0)} · 未指派 ${escapeHtml(actionQueue.relationship_action_unassigned || 0)}</small>
    </section>
    <section>
      <span class="decision-board-kicker">协同升级队列</span>
      <div class="decision-board-heading">
        <strong>${allEscalations.length ? `${allEscalations.length} 条需要管理介入` : "当前无协同逾期"}</strong>
        ${allEscalations.length ? '<button class="text-link" type="button" data-send-opportunity-escalations>发送飞书摘要</button>' : ""}
      </div>
      <div class="decision-escalation-list">
        ${escalations.length ? escalations.map((item) => `
          <button type="button" data-view-opportunity="${escapeHtml(item.notice_id)}">
            <span>${escapeHtml(item.title || "未命名机会")}</span>
            <small>${escapeHtml(escalationIssueLabel(item))} · ${escapeHtml(item.owner || "待分配")}</small>
          </button>
        `).join("") : '<small>决策、主任务、关系行动与公告变更复核会自动识别需要管理介入的机会。</small>'}
      </div>
    </section>
  `;
}

function decisionBoardLine(label, value, tone = "") {
  return `<p class="${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></p>`;
}

function decisionPipelineValue(label, value, tone) {
  return `<div class="pipeline-${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function opportunityActionButtons(item) {
  const actions = item.action_contract?.actions || [];
  return actions.map((descriptor) => {
    const className = descriptor.intent === "primary"
      ? "primary-lite-button"
      : descriptor.intent === "danger" ? "danger-button" : "ghost-button";
    const reasons = descriptor.blocked_reasons || [];
    const title = reasons.length ? ` title="${escapeHtml(reasons.join("；"))}"` : "";
    const disabled = descriptor.enabled ? "" : " disabled";
    return `<button class="${className}" type="button" data-opportunity-action="${escapeHtml(descriptor.action)}" data-opportunity-id="${escapeHtml(item.notice_id)}"${title}${disabled}>${escapeHtml(descriptor.label)}</button>`;
  }).join("");
}

function noticeChangeFieldLabel(field) {
  return {
    attachment_fingerprints: "附件内容",
    attachments: "附件列表",
    bid_deadline: "投标截止",
    budget: "预算",
    content_text: "公告正文",
    core_content: "核心内容",
    project_no: "项目编号",
    publish_time: "发布时间",
    purchaser: "采购主体",
    region: "地区",
    source_url: "来源链接",
    title: "标题",
  }[field] || field;
}

function noticeChangeLine(field, before, after) {
  const beforeText = noticeChangeValue(before);
  const afterText = noticeChangeValue(after);
  return `
    <div>
      <strong>${escapeHtml(noticeChangeFieldLabel(field))}</strong>
      <span>${escapeHtml(beforeText || "未提供")}</span>
      <i aria-hidden="true">→</i>
      <span>${escapeHtml(afterText || "未提供")}</span>
    </div>
  `;
}

function changeImpactPanel(changedFields, changeReview) {
  const impacts = noticeChangeImpacts(changedFields, changeReview);
  return `
    <div class="change-impact-panel">
      <div class="change-impact-heading">
        <strong>变化影响</strong>
        <span>${changedFields.length ? "按最新版本差异生成" : "当前没有待处理差异"}</span>
      </div>
      <div class="change-impact-grid">
        ${impacts.map((impact) => `
          <div class="change-impact-item impact-${escapeHtml(impact.level)}">
            <strong>${escapeHtml(impact.title)}</strong>
            <span>${escapeHtml(impact.detail)}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function noticeChangeImpacts(changedFields, changeReview) {
  const fields = new Set(changedFields);
  const impacts = [];
  if (Number(changeReview?.pending_count) > 0) {
    impacts.push({
      level: "critical",
      title: "原投标决策已失效",
      detail: "负责人完成变更复核后，需重新提交 Go、Hold 或 No-Go 判断。",
    });
  }
  if (fields.has("bid_deadline")) {
    impacts.push({
      level: "critical",
      title: "投标截止时间发生变化",
      detail: "需复核倒排计划、飞书任务和日历安排，系统不会静默覆盖人工计划。",
    });
  }
  if (fields.has("attachments") || fields.has("attachment_fingerprints")) {
    impacts.push({
      level: "warning",
      title: "附件或附件内容发生变化",
      detail: "需重新检查资格材料、技术参数和附件清单。",
    });
  }
  if (fields.has("budget")) {
    impacts.push({
      level: "warning",
      title: "预算发生变化",
      detail: "需重新评估投入规模、报价策略和机会优先级。",
    });
  }
  if (fields.has("content_text") || fields.has("core_content")) {
    impacts.push({
      level: "warning",
      title: "公告正文发生变化",
      detail: "需重新执行需求覆盖与证据核验。",
    });
  }
  if (!impacts.length && changedFields.length) {
    impacts.push({
      level: "info",
      title: "项目事实发生变化",
      detail: "请核对最新版本后再推进机会判断。",
    });
  }
  if (!impacts.length) {
    impacts.push({
      level: "stable",
      title: "当前版本稳定",
      detail: "尚未记录影响投标判断的公告修订。",
    });
  }
  return impacts;
}

async function loadOpportunityRevisionHistory(noticeId) {
  const payload = await api(`/api/opportunities/changes?notice_id=${encodeURIComponent(noticeId)}&limit=100`);
  const container = currentOpportunityRevisionContainer(noticeId);
  if (!container) return;
  const revisions = Array.isArray(payload.items) ? payload.items : [];
  container.innerHTML = revisions.length
    ? revisions.map((revision, index) => opportunityRevisionCard(revision, index === 0)).join("")
    : '<div class="opportunity-revision-empty">当前公告是首个有效版本，尚无历史修订。</div>';
}

function currentOpportunityRevisionContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-opportunity-revisions]");
  return container?.dataset.opportunityRevisions === noticeId ? container : null;
}

async function loadOpportunityRequirements(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements`);
  const container = currentOpportunityRequirementContainer(noticeId);
  if (!container) return;
  state.opportunityRequirementPayloads[noticeId] = payload;
  const item = state.opportunities.find((value) => value.notice_id === noticeId) || {};
  container.innerHTML = renderOpportunityRequirements(payload, item);
}

function currentOpportunityRequirementContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-opportunity-requirements]");
  return container?.dataset.opportunityRequirements === noticeId ? container : null;
}

function renderOpportunityRequirements(payload, item) {
  const requirements = Array.isArray(payload.items) ? payload.items : [];
  const summary = payload.summary || {};
  const impact = payload.impact || {};
  const impactsByRequirementId = new Map(
    (Array.isArray(impact.items) ? impact.items : []).map((value) => [value.id, value]),
  );
  const members = Array.isArray(item.team?.members) ? item.team.members : [];
  const noticeId = item.notice_id || "";
  return `
    <div class="opportunity-requirement-summary">
      <span>共 <strong>${escapeHtml(summary.total_count || 0)}</strong> 项</span>
      <span>已确认 <strong>${escapeHtml(summary.confirmed_count || 0)}</strong> 项</span>
      <span class="${Number(summary.mandatory_pending_count) ? "is-warning" : ""}">强制待处理 <strong>${escapeHtml(summary.mandatory_pending_count || 0)}</strong> 项</span>
    </div>
    <div class="opportunity-requirement-list">
      ${requirements.length ? requirements.map((requirement) => opportunityRequirementRow(requirement, impactsByRequirementId.get(requirement.id))).join("") : '<div class="opportunity-requirement-empty">尚未录入要求。请从公告或附件原文开始建立可复核账本。</div>'}
    </div>
    ${impact.review_required ? `<div class="opportunity-requirement-impact"><strong>公告变化影响：${escapeHtml(impact.affected_count || 0)} 项要求待复核</strong><span>${escapeHtml((impact.items || []).map((item) => item.requirement_key).join("、"))}</span><small>${escapeHtml(impact.items?.[0]?.reason || "请回看原文证据")}</small></div>` : ""}
    ${opportunityRequirementForm(noticeId, item, members)}
  `;
}

function opportunityRequirementRow(requirement, impact = null) {
  const displayStatus = impact?.review_status || requirement.status || "pending";
  const displayStatusLabel = impact
    ? `${impact.review_status_label || "待复核"}（原：${impact.status_label || requirement.status_label || requirement.status || "待确认"}）`
    : requirement.status_label || requirement.status || "待确认";
  return `
    <article class="opportunity-requirement-row status-${escapeHtml(displayStatus)}">
      <div class="opportunity-requirement-heading">
        <strong>${escapeHtml(requirement.requirement_key || "要求编号待确认")}</strong>
        <span>${escapeHtml(requirement.requirement_type_label || requirement.requirement_type || "类型待确认")}</span>
        ${requirement.mandatory ? '<em>强制项</em>' : ""}
        <button class="link-button" type="button" data-edit-opportunity-requirement="${escapeHtml(requirement.id || "")}" data-opportunity-id="${escapeHtml(requirement.notice_id || "")}">编辑</button>
      </div>
      <strong>${escapeHtml(requirement.title || "未命名要求")}</strong>
      <p>${escapeHtml(requirement.evidence_text || "原文待补")}</p>
      <small>${escapeHtml(requirement.source_locator || "定位待补")} · 置信度 ${escapeHtml(requirement.confidence || 0)}% · ${escapeHtml(displayStatusLabel)}${requirement.due_at ? ` · 截止 ${escapeHtml(requirement.due_at)}` : ""}</small>
    </article>
  `;
}

function opportunityRequirementForm(noticeId, item, members) {
  const memberOptions = [
    '<option value="">暂不分配</option>',
    ...members.map((member) => `<option value="${escapeHtml(member.id || "")}">${escapeHtml(member.member_name || "未命名成员")} · ${escapeHtml(member.role_label || "协作成员")}</option>`),
  ].join("");
  return `
    <form class="opportunity-requirement-form" data-opportunity-requirements-form="${escapeHtml(noticeId)}">
      <div class="opportunity-requirement-form-heading">
        <strong>录入或修订要求</strong>
        <button class="link-button" type="button" data-extract-opportunity-requirements="${escapeHtml(noticeId)}">规则提取</button>
        <button class="link-button" type="button" data-reset-opportunity-requirement="${escapeHtml(noticeId)}">清空</button>
      </div>
      <div class="opportunity-requirement-form-grid">
        <label><span>要求编号</span><input name="requirement_key" required maxlength="80" placeholder="例如 QUAL-01" /></label>
        <label><span>类型</span><select name="requirement_type"><option value="qualification">资格条件</option><option value="deadline">截止时间</option><option value="scoring">评分项</option><option value="disqualification">废标条款</option><option value="attachment">附件清单</option></select></label>
        <label class="requirement-wide"><span>要求概述</span><input name="title" required maxlength="300" placeholder="可执行、可判断的要求描述" /></label>
        <label class="requirement-wide"><span>原文摘录</span><textarea name="evidence_text" required rows="2" maxlength="2000" placeholder="复制对应原文，不以模型概括代替证据"></textarea></label>
        <label><span>原文定位</span><input name="source_locator" required maxlength="300" placeholder="文件名第 3 页，第 2.1 条" /></label>
        <label><span>证据链接</span><input name="source_url" type="url" required value="${escapeHtml(item.source_url || "")}" /></label>
        <label><span>置信度</span><input name="confidence" type="number" min="0" max="100" value="0" /></label>
        <label><span>处理状态</span><select name="status"><option value="pending">待确认</option><option value="confirmed">已确认</option><option value="assigned">待准备</option><option value="in_progress">准备中</option><option value="review">待复核</option><option value="completed">已完成</option></select></label>
        <label><span>责任人</span><select name="assignee_member_id">${memberOptions}</select></label>
        <label><span>截止时间</span><input name="due_at" type="datetime-local" /></label>
        <label class="requirement-checkbox"><input name="mandatory" type="checkbox" /><span>强制项 / 废标风险</span></label>
        <label class="requirement-wide"><span>备注</span><input name="note" maxlength="1000" placeholder="待补材料、核验说明或人工判断" /></label>
      </div>
      <div class="opportunity-requirement-form-actions"><button class="primary-lite-button" type="submit">保存要求</button></div>
    </form>
  `;
}

function editOpportunityRequirement(noticeId, requirementId) {
  const requirement = state.opportunityRequirementPayloads[noticeId]?.items?.find(
    (item) => item.id === requirementId,
  );
  const form = currentOpportunityRequirementContainer(noticeId)?.querySelector("form");
  if (!requirement || !form) return;
  for (const field of ["requirement_key", "requirement_type", "title", "evidence_text", "source_url", "source_locator", "confidence", "status", "assignee_member_id", "due_at", "note"]) {
    if (form.elements[field]) form.elements[field].value = requirement[field] || "";
  }
  form.elements.mandatory.checked = Boolean(requirement.mandatory);
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function resetOpportunityRequirementForm(noticeId) {
  const form = currentOpportunityRequirementContainer(noticeId)?.querySelector("form");
  if (!form) return;
  form.reset();
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (form.elements.source_url) form.elements.source_url.value = item?.source_url || "";
}

async function saveOpportunityRequirement(form) {
  const noticeId = form.dataset.opportunityRequirementsForm || "";
  if (!noticeId) return;
  const values = new FormData(form);
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements`, {
      method: "POST",
      body: JSON.stringify({
        requirement_key: values.get("requirement_key") || "",
        requirement_type: values.get("requirement_type") || "qualification",
        title: values.get("title") || "",
        evidence_text: values.get("evidence_text") || "",
        source_url: values.get("source_url") || "",
        source_locator: values.get("source_locator") || "",
        mandatory: values.get("mandatory") === "on",
        confidence: Number(values.get("confidence") || 0),
        status: values.get("status") || "pending",
        assignee_member_id: values.get("assignee_member_id") || "",
        due_at: values.get("due_at") || "",
        note: values.get("note") || "",
        actor: "web:admin",
      }),
    });
    await loadOpportunityRequirements(noticeId);
    showToast("要求已保存，并保留原文证据与处理状态");
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function extractOpportunityRequirements(noticeId) {
  if (!noticeId) return;
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements/extract`, {
    method: "POST",
  });
  await loadOpportunityRequirements(noticeId);
  showToast(`规则提取完成：新增或更新 ${result.created_or_updated_count || 0} 项，人工内容保留 ${result.preserved_count || 0} 项`);
}

function opportunityRevisionCard(revision, latest) {
  const fields = Array.isArray(revision.changed_fields) ? revision.changed_fields : [];
  return `
    <article class="opportunity-revision-card">
      <div class="opportunity-revision-heading">
        <div>
          <span>${latest ? "最近一次修订" : "历史修订"}</span>
          <strong>${escapeHtml(revision.created_at || "时间待确认")}</strong>
        </div>
        <small>${escapeHtml(fields.length)} 个字段变化</small>
      </div>
      <div class="opportunity-change-list">
        ${fields.map((field) => noticeChangeLine(
          field,
          revision.before?.[field],
          revision.after?.[field],
        )).join("")}
      </div>
    </article>
  `;
}

function noticeChangeValue(value) {
  if (Array.isArray(value)) return `${value.length} 项`;
  if (value && typeof value === "object") return value.excerpt || "内容已更新";
  const text = String(value ?? "").trim();
  return text.length > 140 ? `${text.slice(0, 140)}…` : text;
}

function marketInsight(label, value, detail) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></div>`;
}

function formatCny(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "待确认";
  if (amount >= 100000000) return `${Number((amount / 100000000).toFixed(2))} 亿元`;
  if (amount >= 10000) return `${Number((amount / 10000).toFixed(1))} 万元`;
  return `${Math.round(amount)} 元`;
}

function formatNumber(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : "-";
}

function qualityBar(label, value) {
  const score = Math.max(0, Math.min(Number(value) || 0, 100));
  return `
    <div class="quality-line">
      <span>${escapeHtml(label)}</span>
      <i><b style="width:${score}%"></b></i>
      <strong>${score}</strong>
    </div>
  `;
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
  const opportunities = report.opportunity_summary || {};
  const knowledgeCoverage = report.knowledge_coverage || {};
  const opportunityLevels = opportunities.levels || {};
  renderMemoryDigest(report);
  if (el.memorySummary) {
    el.memorySummary.className = "eval-summary";
    el.memorySummary.innerHTML = [
      summaryTile("周期", `${period.from || "-"} 至 ${period.to || "-"}`),
      summaryTile("核心主题", firstCounterName(profile.topics, "暂无")),
      summaryTile("核心区域", firstCounterName(profile.regions, "暂无")),
      summaryTile("下载转化", percent(behavior.download_rate || 0)),
      summaryTile("A / B 机会", `${opportunityLevels.A || 0} / ${opportunityLevels.B || 0}`),
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
    ["智能采集", knowledgeCoverage.active_count ?? 0],
    ["重复查询", queryPatterns.repeat_queries?.length ?? 0],
    ["澄清风险", queryPatterns.clarify_risk_count ?? 0],
  ]);
  renderMetricCard(el.memoryDailyMetrics, "机会质量", [
    ["本周线索", opportunities.total ?? 0],
    ["平均评分", opportunities.average_score ?? 0],
    ["平均可信", opportunities.average_credibility ?? 0],
    ["风险项", opportunities.risk_count ?? 0],
  ]);
  renderMemoryProfile(profile, opportunities);
  renderGeneratedAdvice(generatedAdvice, recommendationPlan);
  renderIngestCoverage(knowledgeCoverage);
  renderMemoryList(
    el.memoryQueries,
    report.top_queries || [],
    (item) => `<div class="case-row"><strong>${escapeHtml(item.query)}</strong><span>${escapeHtml(item.count)} 次</span></div>`,
    "暂无查询",
  );
  renderMemoryList(
    el.memorySuggestions,
    riskSignals,
    (item) => {
      return `
        <div class="case-row risk-row risk-${escapeHtml(item.severity || "low")}">
          <strong>${escapeHtml(item.title || "风险信号")}</strong>
          <span>${escapeHtml(item.detail || "")}</span>
          <span>${escapeHtml(formatAdviceEvidence(item.evidence))}</span>
        </div>
      `;
    },
    "当前周期未发现需要优先处理的风险",
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

function renderIngestCoverage(coverage = {}) {
  if (!el.memoryIngestCoverage) return;
  const items = Array.isArray(coverage.items) ? coverage.items : [];
  if (!items.length) {
    el.memoryIngestCoverage.className = "ingest-coverage-list empty-state";
    el.memoryIngestCoverage.textContent = "暂无智能采集计划";
    return;
  }
  el.memoryIngestCoverage.className = "ingest-coverage-list";
  el.memoryIngestCoverage.innerHTML = items
    .map(
      (item) => `
        <div class="ingest-coverage-row">
          <div>
            <strong>${escapeHtml(item.name || "智能采集")}</strong>
            <span>${escapeHtml((item.regions || []).join("、") || "全部区域")} · ${escapeHtml((item.topics || []).join("、") || "全部主题")}</span>
          </div>
          <div>
            <b>${escapeHtml(cronText(item.cron || ""))}</b>
            <span>${escapeHtml(item.last_run_at ? `最近运行 ${compactDateTimeText(item.last_run_at)}` : "等待首次运行")}</span>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderSmartStart() {
  if (!el.smartStartPanel) return;
  const query = el.queryInput?.value.trim() || "";
  const mode = checkedValue("actionMode") === "subscribe" ? "订阅模式" : "立即运行";
  const strategy = modelStrategyLabel(el.modelStrategySelect?.value || "config");
  if (el.smartStartMeta) {
    el.smartStartMeta.textContent = query
      ? `${mode} · ${strategy} · 当前问题已就绪`
      : "选择模板后可继续修改";
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

function renderMemoryProfile(profile = {}, opportunities = {}) {
  if (!el.memoryProfile) return;
  const rows = [
    ["主题偏好", counterSummary(profile.topics, "暂无主题偏好")],
    ["区域偏好", counterSummary(profile.regions, "暂无区域偏好")],
    ["定时模式", counterSummary(profile.schedules, "暂无定时偏好")],
    ["来源命中", counterSummary(profile.sources, "暂无来源样本")],
    ["信息缺口", counterSummary(opportunities.missing_fields, "关键字段较完整")],
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
  const nextActions = plan
    .filter((item) => !["completed", "dismissed"].includes(item.feedback_status || "pending"))
    .slice(0, 3);
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
              (item) => `
                <div class="advice-action">
                  <div class="advice-action-copy">
                    <div class="advice-action-title">
                      ${priorityBadge(item.priority)}
                      <strong>${escapeHtml(item.title || "行动建议")}</strong>
                      ${adviceStatusBadge(item.feedback_status)}
                    </div>
                    <p>${escapeHtml(item.reason || "")}</p>
                    <b>${escapeHtml(item.action || "")}</b>
                    <small>${escapeHtml(formatAdviceEvidence(item.evidence))}</small>
                  </div>
                  <div class="advice-feedback-actions">
                    ${adviceFeedbackButtons(item)}
                  </div>
                </div>
              `,
            )
            .join("")
        : '<div class="note-row">暂无下一步动作</div>'
    }
  `;
}

function adviceFeedbackButtons(item) {
  const id = escapeHtml(item.id || "");
  const status = item.feedback_status || "pending";
  if (!id) return "";
  const buttons = [];
  if (status === "pending") {
    buttons.push(`<button type="button" data-advice-id="${id}" data-advice-status="accepted">采纳</button>`);
  }
  if (["pending", "accepted"].includes(status)) {
    buttons.push(`<button type="button" data-advice-id="${id}" data-advice-status="completed">完成</button>`);
    buttons.push(`<button type="button" data-advice-id="${id}" data-advice-status="dismissed">忽略</button>`);
  }
  return buttons.join("");
}

function adviceStatusBadge(status = "pending") {
  const label = { pending: "待处理", accepted: "已采纳", completed: "已完成", dismissed: "已忽略" }[status];
  return `<span class="advice-status advice-status-${escapeHtml(status)}">${escapeHtml(label || status)}</span>`;
}

function formatAdviceEvidence(evidence = {}) {
  if (!evidence || typeof evidence !== "object") return "依据：当前周期行为与机会数据";
  const labels = {
    level: "机会等级",
    count: "数量",
    query: "查询",
    topic: "主题",
    region: "区域",
    run_ids: "失败运行",
  };
  const parts = Object.entries(evidence).map(([key, value]) => {
    const rendered = formatAdviceEvidenceValue(value);
    return `${labels[key] || key}=${rendered}`;
  });
  return parts.length ? `依据：${parts.join(" · ")}` : "依据：当前周期行为与机会数据";
}

function formatAdviceEvidenceValue(value) {
  if (Array.isArray(value)) return value.map(formatAdviceEvidenceValue).join("、");
  if (value && typeof value === "object") {
    if (value.query) return `“${value.query}”×${value.count || 1}`;
    return Object.entries(value)
      .map(([key, item]) => `${key}:${formatAdviceEvidenceValue(item)}`)
      .join(" / ");
  }
  return String(value ?? "-");
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
    settingTile(
      "销售准入策略",
      config.qualification_policy
        ? `机会 ${config.qualification_policy.minimum_opportunity_score} · 可信 ${config.qualification_policy.minimum_credibility} · 完整 ${config.qualification_policy.minimum_completeness} · 需求 ${config.qualification_policy.minimum_requirement_coverage} · 团队 ${config.qualification_policy.minimum_team_coverage} · 关系 ${config.qualification_policy.minimum_stakeholder_coverage}`
        : "-",
    ),
    settingTile(
      "决策 SLA",
      config.qualification_policy
        ? `${config.qualification_policy.decision_sla_hours} 小时 · ${config.qualification_policy.escalation_enabled ? `自动 ${config.qualification_policy.escalation_cron}` : "手动升级"}`
        : "-",
    ),
    settingTile("Outbox", config.outbox_dir || "-"),
    settingTile("数据库", config.db_path || "-"),
    settingTile("登录态目录", config.secrets_dir || "-"),
  ].join("");
}

function renderFeishuOverview(payload) {
  if (!el.feishuFeatureList) return;
  state.feishu = payload;
  const features = payload.features || {};
  const partnerLeadImport = features.partner_lead_ingest || {};
  const partnerLeadLastRun = partnerLeadImport.last_run;
  const partnerLeadDetail = partnerLeadLastRun
    ? `${partnerLeadImport.automation_enabled ? `自动 ${partnerLeadImport.cron}` : "手动"} · 最近${statusLabel(partnerLeadLastRun.status)} · 导入 ${partnerLeadLastRun.imported_count || 0} 条 · 核验 ${partnerLeadLastRun.verified_count || 0} 条 · 失败 ${partnerLeadLastRun.verification_failed_count || 0} 条`
    : `${partnerLeadImport.automation_enabled ? `自动 ${partnerLeadImport.cron}` : "手动触发"} · 暂无同步记录`;
  const conversationCommands = features.conversation_commands || {};
  const latestCommand = conversationCommands.last_event;
  const conversationDetail = latestCommand
    ? `${latestCommand.command_kind === "subscription" ? "订阅" : "即时查询"} · ${statusLabel(latestCommand.status)} · ${compactDateTimeText(latestCommand.updated_at)}`
    : `长连接${conversationCommands.long_connection_available ? "可启动" : "不可用"} · HTTP 回调${conversationCommands.webhook_ready ? "已就绪" : "待配置"}`;
  const rows = [
    ["报告与周报", features.report_delivery, "Word 文件和使用周报"],
    ["多维表格", features.bitable_sync, features.bitable_sync?.detail || "公告明细同步"],
    ["伙伴线索入口", partnerLeadImport, partnerLeadDetail],
    ["事实核验闭环", features.fact_verification, "记录视图提交 · 本地重算 · 审计回写"],
    ["会话自然语言指令", conversationCommands, conversationDetail],
    ["机会卡片", features.opportunity_cards, "可操作机会卡片与原文入口"],
    [
      "决策 SLA 升级",
      features.decision_escalation,
      features.decision_escalation?.automation_enabled
        ? `自动 ${features.decision_escalation.cron}`
        : "机会页手动发送，自动提醒默认关闭",
    ],
    [
      "机会经营晨报",
      features.opportunity_briefing,
      features.opportunity_briefing?.automation_enabled
        ? `工作日自动 ${features.opportunity_briefing.cron}`
        : "机会池、负责人、资格门禁、决策时效与来源风险合并推送",
    ],
    [
      "销售任务双向同步",
      features.task_sync,
      features.task_sync?.automation_enabled
        ? `自动 ${features.task_sync.cron} · 完成与逾期状态回写机会台账`
        : "机会页手动同步，支持完成与逾期状态回写",
    ],
    [
      "客户关系行动",
      features.relationship_actions,
      features.relationship_actions?.automation_enabled
        ? `自动 ${features.relationship_actions.cron} · 关键人行动完成、逾期与结果回写`
        : "从关键人图谱生成可分派行动，支持飞书任务执行",
    ],
    [
      "来源健康告警",
      features.source_health_alert,
      features.source_health_alert?.automation_enabled
        ? `自动 ${features.source_health_alert.cron} · 可靠度与新鲜度异常去重推送`
        : `手动发送 · 可靠度阈值 ${percent(features.source_health_alert?.minimum_reliability || 0)} · 新鲜度 ${features.source_health_alert?.stale_hours || 0} 小时`,
    ],
    [
      "来源异常处置任务",
      features.source_incident_task,
      `${features.source_incident_task?.active_count || 0} 个活动事件 · ${features.source_incident_task?.assigned ? "默认负责人已绑定" : "可创建未指派任务"} · ${features.source_incident_task?.sla_hours || 0} 小时 SLA${features.source_incident_task?.sync_enabled ? " · 自动回收状态" : ""}`,
    ],
    ["截止日程", features.deadline_calendar, "投标截止自动进入日历"],
    ["状态回调", features.card_callback, "卡片动作回写台账与审计流"],
    ["智能体服务", features.agent_service, "独立智能体应用"],
  ];
  el.feishuFeatureList.className = "integration-list";
  el.feishuFeatureList.innerHTML = rows
    .map(
      ([name, feature, detail]) => `
        <div class="integration-row">
          <div class="integration-copy"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(detail)}</span></div>
          <div class="integration-actions">
            ${feature?.url ? `<a class="text-link" href="${escapeHtml(feature.url)}" target="_blank" rel="noreferrer">打开</a>` : ""}
            <span class="badge badge-${feature?.ready ? "pass" : "warn"}">${feature?.ready ? "可用" : "待配置"}</span>
          </div>
        </div>
      `,
    )
    .join("");
  if (el.feishuCenterMeta) {
    const receiverLabel = payload.receiver?.label;
    el.feishuCenterMeta.textContent = payload.status === "ready"
      ? `报告与周报将发送到 ${receiverLabel || "默认接收目标"}`
      : "存在待处理配置，发送失败时会保留诊断记录";
  }
  const issues = payload.issues || [];
  if (el.feishuIssueList) {
    el.feishuIssueList.hidden = !issues.length;
    el.feishuIssueList.innerHTML = issues
      .map((item) => `<div class="integration-issue"><strong>${escapeHtml(feishuIssueLabel(item.code))}</strong><span>${escapeHtml(item.message)}</span></div>`)
      .join("");
  }
  const attempts = payload.recent_attempts || [];
  if (el.feishuAttemptList) {
    el.feishuAttemptList.hidden = !attempts.length;
    el.feishuAttemptList.innerHTML = `
      <h3>最近交付</h3>
      ${attempts
        .map(
          (item) => `
            <div class="delivery-attempt-row">
              <span title="${escapeHtml(item.artifact_key)}">${escapeHtml(item.artifact_key)}</span>
              <span class="badge badge-${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
              <time>${escapeHtml(compactDateTimeText(item.created_at))}</time>
              ${item.error ? `<small title="${escapeHtml(item.error)}">${escapeHtml(item.error)}</small>` : ""}
            </div>
          `,
        )
        .join("")}
    `;
  }
}

function feishuIssueLabel(code) {
  return (
    {
      message_app: "消息应用",
      receiver: "接收目标",
      bitable: "多维表格",
      agent: "智能体服务",
    }[code] || code
  );
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
  const [payload, alerts] = await Promise.all([
    api("/api/sources"),
    api("/api/sources/alerts"),
  ]);
  state.sources = payload.items || [];
  state.sourceAlerts = alerts;
  renderSources(state.sources);
  renderSourceAlerts(alerts);
  renderNotifications();
}

async function sendSourceAlertsToFeishu() {
  const result = await api("/api/sources/alerts/send-feishu", {
    method: "POST",
    body: JSON.stringify({}),
  });
  const message = result.status === "sent"
    ? `已发送 ${result.issue_count} 个来源异常`
    : result.issue_count
      ? "相同来源状态今天已发送"
      : "当前没有需要发送的来源异常";
  showToast(message);
  await Promise.all([refreshSources(), refreshFeishu()]);
}

async function createSourceIncidentTask() {
  const result = await api("/api/sources/alerts/create-feishu-task", {
    method: "POST",
    body: JSON.stringify({}),
  });
  const message = result.status === "sent"
    ? result.assigned
      ? `已创建并指派 ${result.issue_count} 个来源异常处置任务`
      : `已创建 ${result.issue_count} 个来源异常处置任务，等待指派负责人`
    : result.issue_count
      ? "相同来源状态今天已创建处置任务"
      : "当前没有需要处置的来源异常";
  showToast(message);
  await Promise.all([refreshSources(), refreshFeishu()]);
}

async function syncSourceIncidentTasks() {
  const result = await api("/api/sources/incidents/sync", {
    method: "POST",
    body: JSON.stringify({}),
  });
  const message = result.status === "skipped"
    ? "当前没有待同步的来源处置任务"
    : result.failed_count
      ? `已同步 ${result.scanned_count} 项，${result.failed_count} 项失败`
      : result.resolved_count
        ? `已验证并关闭 ${result.resolved_count} 个来源事件`
        : result.verification_failed_count
          ? "飞书任务已完成，但来源仍异常，事件保持打开"
          : `已同步 ${result.scanned_count} 个来源处置任务`;
  showToast(message);
  await Promise.all([refreshSources(), refreshFeishu()]);
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

async function refreshOpportunities() {
  const level = el.opportunityLevelFilter?.value || "";
  const topic = el.opportunityTopicFilter?.value || "";
  const sort = el.opportunitySortSelect?.value || "priority";
  const query = new URLSearchParams({ limit: "80" });
  if (level) query.set("level", level);
  if (topic) query.set("topic", topic);
  query.set("sort", sort);
  const payload = await api(`/api/opportunities?${query.toString()}`);
  state.opportunityVisible = opportunityPageSize();
  renderOpportunities(payload);
  return payload;
}

function opportunityPageSize() {
  return window.innerWidth <= 700 ? 6 : 20;
}

async function refreshOrganizationWorkspaces() {
  const payload = await api("/api/organization/workspaces");
  state.organizationWorkspaces = payload.items || [];
  const requested = new URLSearchParams(window.location.search).get("workspace") || "";
  const current = state.organizationWorkspaceId || requested;
  state.organizationWorkspaceId = state.organizationWorkspaces.some((item) => item.id === current)
    ? current
    : state.organizationWorkspaces[0]?.id || "";
  renderOrganizationWorkspaceOptions();
  renderOrganizationSummary();
  await refreshOrganizationMemories();
}

function renderOrganizationWorkspaceOptions() {
  if (!el.organizationWorkspaceSelect) return;
  if (!state.organizationWorkspaces.length) {
    el.organizationWorkspaceSelect.innerHTML = '<option value="">暂无协作空间</option>';
    el.organizationWorkspaceSelect.disabled = true;
    return;
  }
  el.organizationWorkspaceSelect.disabled = false;
  el.organizationWorkspaceSelect.innerHTML = state.organizationWorkspaces
    .map(
      (item) =>
        `<option value="${escapeHtml(item.id)}" ${item.id === state.organizationWorkspaceId ? "selected" : ""}>${escapeHtml(item.name)}</option>`,
    )
    .join("");
}

function renderOrganizationSummary() {
  if (!el.organizationSummary) return;
  const workspace = state.organizationWorkspaces.find(
    (item) => item.id === state.organizationWorkspaceId,
  );
  if (!workspace) {
    el.organizationSummary.className = "organization-summary empty-state";
    el.organizationSummary.textContent = "请选择或创建协作空间";
    if (el.openOrganizationWorkspaceButton) {
      el.openOrganizationWorkspaceButton.hidden = true;
      el.openOrganizationWorkspaceButton.removeAttribute("href");
    }
    return;
  }
  if (el.openOrganizationWorkspaceButton) {
    const chatUrl = workspace.feishu_chat_url || "";
    el.openOrganizationWorkspaceButton.hidden = !chatUrl;
    if (chatUrl) el.openOrganizationWorkspaceButton.href = chatUrl;
    else el.openOrganizationWorkspaceButton.removeAttribute("href");
  }
  el.organizationSummary.className = "organization-summary";
  el.organizationSummary.innerHTML = `
    <div><span>当前空间</span><strong>${escapeHtml(workspace.name)}</strong></div>
    <div><span>协作成员</span><strong>${Number(workspace.member_count || 0)}</strong></div>
    <div><span>共享知识</span><strong>${Number(workspace.memory_count || 0)}</strong></div>
    <div><span>连接状态</span><strong class="organization-online">飞书已连接</strong></div>`;
}

async function refreshOrganizationMemories() {
  if (!state.organizationWorkspaceId) {
    state.organizationMemories = [];
    renderOrganizationMemories();
    return;
  }
  const params = new URLSearchParams();
  const query = el.organizationMemorySearch?.value.trim() || "";
  const memoryType = el.organizationMemoryTypeFilter?.value || "";
  if (query) params.set("query", query);
  if (memoryType) params.set("memory_type", memoryType);
  const payload = await api(
    `/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/memories?${params}`,
  );
  state.organizationMemories = payload.items || [];
  renderOrganizationMemories();
}

function renderOrganizationMemories() {
  if (!el.organizationMemoryList) return;
  const items = state.organizationMemories;
  if (el.organizationMemoryMeta) el.organizationMemoryMeta.textContent = `${items.length} 条`;
  if (!items.length) {
    el.organizationMemoryList.className = "organization-memory-list empty-state";
    el.organizationMemoryList.textContent = state.organizationWorkspaceId
      ? "当前筛选条件下暂无组织记忆"
      : "请先创建飞书项目群";
    return;
  }
  const labels = {
    note: "记录",
    decision: "决策",
    customer_signal: "客户信号",
    competitor: "竞争情报",
    risk: "风险",
    lesson: "经验",
  };
  el.organizationMemoryList.className = "organization-memory-list";
  el.organizationMemoryList.innerHTML = items
    .map(
      (item) => `
        <article class="organization-memory-row">
          <div class="organization-memory-row-head">
            <span class="badge badge-muted">${escapeHtml(labels[item.memory_type] || item.memory_type)}</span>
            <time>${escapeHtml(item.created_at || "")}</time>
          </div>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.content)}</p>
          <div class="organization-memory-evidence">
            <span>${item.source_type === "feishu_message" ? "飞书群消息" : "网页记录"}</span>
            ${item.related_notice_id ? `<span>机会 ${escapeHtml(item.related_notice_id)}</span>` : ""}
            ${item.evidence_url ? `<a href="${escapeHtml(item.evidence_url)}" target="_blank" rel="noreferrer">查看证据</a>` : ""}
            <button class="text-button" type="button" data-convert-organization-memory="${escapeHtml(item.id)}">转为机会工作</button>
          </div>
        </article>`,
    )
    .join("");
}

async function saveOrganizationMemory(event) {
  event.preventDefault();
  if (!state.organizationWorkspaceId) throw new Error("请先创建或选择协作空间");
  await api(
    `/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/memories`,
    {
      method: "POST",
      body: JSON.stringify({
        memory_type: el.organizationMemoryType?.value || "note",
        title: el.organizationMemoryTitleInput?.value.trim() || "",
        content: el.organizationMemoryContent?.value.trim() || "",
        related_notice_id: el.organizationMemoryNoticeId?.value.trim() || "",
        evidence_url: el.organizationMemoryEvidenceUrl?.value.trim() || "",
      }),
    },
  );
  el.organizationMemoryForm?.reset();
  showToast("组织记忆已保存");
  await refreshOrganizationWorkspaces();
}

async function openOrganizationGroupDialog(mode) {
  if (mode === "invite" && !state.organizationWorkspaceId) {
    throw new Error("请先选择协作空间");
  }
  state.organizationGroupMode = mode;
  const payload = await api("/api/integrations/feishu/users?limit=100");
  const users = payload.items || [];
  if (el.organizationMemberSelect) {
    el.organizationMemberSelect.innerHTML = users
      .map(
        (user) =>
          `<option value="${escapeHtml(user.open_id)}" data-name="${escapeHtml(user.name)}">${escapeHtml(user.name)}</option>`,
      )
      .join("");
  }
  const creating = mode === "create";
  if (el.organizationGroupDialogTitle) {
    el.organizationGroupDialogTitle.textContent = creating ? "创建飞书项目群" : "邀请协作成员";
  }
  if (el.organizationGroupDialogMeta) {
    el.organizationGroupDialogMeta.textContent = creating ? "机器人将自动加入项目群" : "成员将同步到当前协作空间";
  }
  if (el.organizationGroupNameField) el.organizationGroupNameField.hidden = !creating;
  if (el.organizationGroupName) el.organizationGroupName.required = creating;
  if (el.submitOrganizationGroupButton) {
    el.submitOrganizationGroupButton.textContent = creating ? "创建并邀请" : "确认邀请";
  }
  if (el.organizationGroupStatus) el.organizationGroupStatus.textContent = "";
  el.organizationGroupDialog?.showModal();
}

function closeOrganizationGroupDialog() {
  el.organizationGroupDialog?.close();
  el.organizationGroupForm?.reset();
}

async function submitOrganizationGroup(event) {
  event.preventDefault();
  const members = [...(el.organizationMemberSelect?.selectedOptions || [])].map((option) => ({
    open_id: option.value,
    name: option.dataset.name || option.textContent || "",
    role: "member",
  }));
  if (!members.length) throw new Error("请至少选择一名成员");
  if (el.organizationGroupStatus) el.organizationGroupStatus.textContent = "正在同步飞书...";
  let successMessage = "成员邀请已发送";
  if (state.organizationGroupMode === "create") {
    const result = await api("/api/organization/workspaces", {
      method: "POST",
      body: JSON.stringify({ name: el.organizationGroupName?.value.trim() || "", members }),
    });
    state.organizationWorkspaceId = result.workspace.id;
    successMessage = result.notification?.status === "sent"
      ? `${result.workspace.name}已创建，群内通知已发送`
      : result.notification?.message || `${result.workspace.name}已创建`;
  } else {
    await api(
      `/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/members`,
      { method: "POST", body: JSON.stringify({ members }) },
    );
  }
  closeOrganizationGroupDialog();
  await refreshOrganizationWorkspaces();
  showToast(successMessage);
}

function openOrganizationConvertDialog(memoryId) {
  const memory = state.organizationMemories.find((item) => item.id === memoryId);
  if (!memory) throw new Error("组织记忆不存在或已刷新");
  state.organizationConvertMemoryId = memory.id;
  el.organizationConvertForm?.reset();
  if (el.organizationConvertMemoryTitle) el.organizationConvertMemoryTitle.textContent = memory.title;
  if (el.organizationConvertNoticeId) el.organizationConvertNoticeId.value = memory.related_notice_id || "";
  if (el.organizationConvertActionTitle) el.organizationConvertActionTitle.value = memory.title;
  if (el.organizationConvertEvidenceUrl) el.organizationConvertEvidenceUrl.value = memory.evidence_url || "";
  if (el.organizationConvertStatus) el.organizationConvertStatus.textContent = "";
  syncOrganizationConvertFields();
  el.organizationConvertDialog?.showModal();
}

function syncOrganizationConvertFields() {
  const factMode = el.organizationConvertTarget?.value === "opportunity_fact";
  document.querySelectorAll(".organization-fact-convert-field").forEach((field) => {
    field.hidden = !factMode;
  });
  document.querySelectorAll(".organization-action-convert-field").forEach((field) => {
    field.hidden = factMode;
  });
  if (el.organizationConvertFactValue) el.organizationConvertFactValue.required = factMode;
  if (el.organizationConvertEvidenceUrl) el.organizationConvertEvidenceUrl.required = factMode;
  if (el.organizationConvertActionTitle) el.organizationConvertActionTitle.required = !factMode;
  if (el.organizationConvertDueAt) el.organizationConvertDueAt.required = !factMode;
}

function closeOrganizationConvertDialog() {
  el.organizationConvertDialog?.close();
  state.organizationConvertMemoryId = "";
}

async function submitOrganizationConversion(event) {
  event.preventDefault();
  const targetType = el.organizationConvertTarget?.value || "relationship_action";
  const body = {
    target_type: targetType,
    notice_id: el.organizationConvertNoticeId?.value.trim() || "",
  };
  if (targetType === "opportunity_fact") {
    body.facts = {
      [el.organizationConvertFactField?.value || "purchaser"]:
        el.organizationConvertFactValue?.value.trim() || "",
    };
    body.evidence_url = el.organizationConvertEvidenceUrl?.value.trim() || "";
  } else {
    body.title = el.organizationConvertActionTitle?.value.trim() || "";
    body.due_at = el.organizationConvertDueAt?.value || "";
    body.priority = el.organizationConvertPriority?.value || "normal";
  }
  if (el.organizationConvertStatus) el.organizationConvertStatus.textContent = "正在写入机会台账...";
  await api(
    `/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/memories/${encodeURIComponent(state.organizationConvertMemoryId)}/convert`,
    { method: "POST", body: JSON.stringify(body) },
  );
  closeOrganizationConvertDialog();
  showToast(targetType === "opportunity_fact" ? "机会事实已核验" : "机会行动已创建");
}

async function refreshMemoryWeekly() {
  state.memory = await api("/api/memory/weekly");
  renderMemory(state.memory);
}

async function saveOpportunityFacts(form) {
  const noticeId = form.dataset.opportunityFacts;
  const data = new FormData(form);
  const facts = {};
  for (const field of ["purchaser", "project_no", "budget", "bid_deadline", "region"]) {
    const value = String(data.get(field) || "").trim();
    if (value) facts[field] = value;
  }
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/facts`, {
      method: "PATCH",
      body: JSON.stringify({
        facts,
        source_url: String(data.get("source_url") || "").trim(),
        evidence_text: String(data.get("evidence_text") || "").trim(),
        note: String(data.get("note") || "").trim(),
        actor: el.userLabel?.textContent?.trim() || "admin",
        channel: "web",
      }),
    });
    state.opportunities = state.opportunities.map((item) =>
      item.notice_id === noticeId ? result.opportunity : item,
    );
    renderOpportunities({ items: state.opportunities, summary: state.opportunitySummaryData });
    openOpportunityDetail(noticeId);
    showToast(
      result.bitable_status === "sent"
        ? "事实已核验，资格结果与飞书多维表格已更新"
        : "事实已核验，资格结果已更新",
    );
  } finally {
    if (button) button.disabled = false;
  }
}

async function updateAdviceFeedback(adviceId, status) {
  const result = await api(`/api/memory/advice/${encodeURIComponent(adviceId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({
      status,
      user_id: el.userLabel?.textContent?.trim() || "admin",
      source: "web",
    }),
  });
  state.memory = result.report;
  renderMemory(state.memory);
  const label = { accepted: "建议已采纳", completed: "建议已完成", dismissed: "建议已忽略" }[status];
  showToast(result.automation?.message || label || "建议状态已更新");
}

async function refreshFeishu() {
  const [payload, bitableCheck] = await Promise.all([
    api("/api/integrations/feishu/overview"),
    api("/api/integrations/feishu/bitable/check").catch((error) => ({
      status: "failed",
      message: error.message,
    })),
  ]);
  payload.bitable_check = bitableCheck;
  if (payload.features?.bitable_sync) {
    payload.features.bitable_sync.ready = bitableCheck.status === "pass";
    payload.features.bitable_sync.detail = bitableCheck.table_name
      ? `${bitableCheck.table_name} · ${bitableCheck.field_count || 0} 个字段 · ${bitableCheck.record_count || 0} 条线索`
      : bitableCheck.message;
    if (el.openFeishuBitableButton) {
      const url = payload.features.bitable_sync.url || "";
      el.openFeishuBitableButton.hidden = !url;
      if (url) el.openFeishuBitableButton.href = url;
    }
  }
  renderFeishuOverview(payload);
  return payload;
}

async function testFeishuConnection() {
  const result = await api("/api/integrations/feishu/test-message", {
    method: "POST",
    body: JSON.stringify({ text: `TenderTrace 连接测试 ${new Date().toLocaleString("zh-CN")}` }),
  });
  await refreshFeishu();
  showToast(result.status === "sent" ? "飞书测试消息已发送" : "飞书测试未完成");
}

async function importFeishuPartnerLeads() {
  const preview = await api("/api/integrations/feishu/bitable/import-leads", {
    method: "POST",
    body: JSON.stringify({ dry_run: true }),
  });
  if (!preview.candidate_count) {
    showToast(`未发现待导入伙伴线索，已扫描 ${preview.scanned_count || 0} 条记录`);
    return;
  }
  const invalidText = preview.invalid_records?.length
    ? `，另有 ${preview.invalid_records.length} 条字段不完整`
    : "";
  const confirmed = window.confirm(
    `发现 ${preview.candidate_count} 条候选线索，其中 ${preview.existing_count || 0} 条已入库${invalidText}。确认导入？`,
  );
  if (!confirmed) return;
  const result = await api("/api/integrations/feishu/bitable/import-leads", {
    method: "POST",
    body: JSON.stringify({ dry_run: false }),
  });
  await Promise.all([refreshFeishu(), refreshOpportunities()]);
  showToast(`已导入 ${result.imported_count || 0} 条伙伴线索，飞书回写 ${result.updated_count || 0} 条`);
}

async function openFeishuReceiverEditor() {
  if (!el.feishuReceiverEditor || !el.feishuChatSelect) return;
  const [chats, users] = await Promise.all([
    api("/api/integrations/feishu/chats?page_size=100").catch((error) => ({ items: [], error })),
    api("/api/integrations/feishu/users?limit=100").catch((error) => ({ items: [], error })),
  ]);
  const chatItems = Array.isArray(chats.items) ? chats.items : [];
  const userItems = Array.isArray(users.items) ? users.items : [];
  if (!chatItems.length && !userItems.length) {
    throw chats.error || users.error || new Error("没有可用的飞书会话或授权成员");
  }
  const chatOptions = chatItems
    .map((item) => {
      const id = item.chat_id || "";
      const label = item.name || id || "未命名会话";
      return `<option value="${escapeHtml(id)}" data-receive-type="chat_id" data-label="${escapeHtml(label)}">${escapeHtml(label)}</option>`;
    })
    .join("");
  const userOptions = userItems
    .map((item) => {
      const id = item.open_id || "";
      const label = item.name || "未命名成员";
      return `<option value="${escapeHtml(id)}" data-receive-type="open_id" data-label="${escapeHtml(label)}">${escapeHtml(label)}</option>`;
    })
    .join("");
  el.feishuChatSelect.innerHTML = [
    chatOptions ? `<optgroup label="机器人会话">${chatOptions}</optgroup>` : "",
    userOptions ? `<optgroup label="授权成员">${userOptions}</optgroup>` : "",
  ].join("");
  el.feishuReceiverEditor.hidden = false;
}

async function saveFeishuReceiverSelection() {
  const option = el.feishuChatSelect?.selectedOptions?.[0];
  if (!option?.value) throw new Error("请选择接收目标");
  const receiveType = option.dataset.receiveType || "chat_id";
  const label = option.dataset.label || option.textContent || "飞书接收目标";
  await api("/api/integrations/feishu/receiver", {
    method: "POST",
    body: JSON.stringify({
      receive_id: option.value,
      receive_id_type: receiveType,
      label,
    }),
  });
  el.feishuReceiverEditor.hidden = true;
  await refreshFeishu();
  showToast(`默认接收目标已设为：${label}`);
}

async function sendReportToFeishu(name, runId = "", subscriptionId = "") {
  const result = await api(`/api/outbox/${encodeURIComponent(name)}/send-feishu`, {
    method: "POST",
    body: JSON.stringify({ run_id: runId || null, subscription_id: subscriptionId || null }),
  });
  await Promise.all([refreshOutbox(), refreshFeishu()]);
  showToast(result.status === "sent" ? "Word 报告已发送到飞书" : "飞书发送未完成");
}

async function sendMemoryWeeklyToFeishu() {
  const result = await api("/api/memory/weekly/send-feishu", {
    method: "POST",
    body: JSON.stringify({ days: 7, user_id: "admin" }),
  });
  await refreshFeishu();
  showToast(result.status === "sent" ? "本周使用周报已发送到飞书" : "周报发送未完成");
}

async function openOpportunityOwnerDialog(noticeId) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityOwnerDialog) return;
  const workflow = item.workflow || {};
  state.pendingOpportunityId = noticeId;
  el.opportunityOwnerProject.textContent = item.title || "未命名机会";
  el.opportunityOwnerName.value = workflow.owner_name || "";
  el.opportunityOwnerSelect.innerHTML = '<option value="">正在读取通讯录</option>';
  el.opportunityOwnerStatus.textContent = "正在读取应用授权范围";
  el.opportunityCreateTask.checked = true;
  el.opportunityCreateCalendar.checked = Boolean(item.bid_deadline);
  if (!el.opportunityOwnerDialog.open) el.opportunityOwnerDialog.showModal();
  try {
    const directory = await api("/api/integrations/feishu/users?limit=200");
    if (state.pendingOpportunityId !== noticeId) return;
    const users = Array.isArray(directory.items) ? directory.items : [];
    el.opportunityOwnerSelect.innerHTML = [
      '<option value="">仅记录姓名，不绑定飞书成员</option>',
      ...users.map(
        (user) => `<option value="${escapeHtml(user.open_id || "")}" data-owner-name="${escapeHtml(user.name || "")}">${escapeHtml(user.name || "未命名成员")}</option>`,
      ),
    ].join("");
    if (workflow.owner_open_id && users.some((user) => user.open_id === workflow.owner_open_id)) {
      el.opportunityOwnerSelect.value = workflow.owner_open_id;
    }
    el.opportunityOwnerStatus.textContent = users.length
      ? `可分配 ${users.length} 名授权成员`
      : "授权范围内暂无成员，可仅记录负责人姓名";
  } catch (error) {
    if (state.pendingOpportunityId !== noticeId) return;
    el.opportunityOwnerSelect.innerHTML = '<option value="">仅记录姓名，不绑定飞书成员</option>';
    el.opportunityOwnerStatus.textContent = "通讯录暂不可用，任务将保持未指派";
  }
}

function closeOpportunityOwnerDialog() {
  state.pendingOpportunityId = "";
  el.opportunityOwnerDialog?.close();
}

async function submitOpportunityOwner(event) {
  event.preventDefault();
  const noticeId = state.pendingOpportunityId;
  const ownerName = el.opportunityOwnerName?.value.trim() || "";
  if (!noticeId || !ownerName) throw new Error("请填写负责人姓名");
  if (el.submitOpportunityOwnerButton) el.submitOpportunityOwnerButton.disabled = true;
  try {
    await sendOpportunityToFeishu(noticeId, {
      owner_open_id: el.opportunityOwnerSelect?.value || "",
      owner_name: ownerName,
      create_task: Boolean(el.opportunityCreateTask?.checked),
      create_calendar_event: Boolean(el.opportunityCreateCalendar?.checked),
    });
    closeOpportunityOwnerDialog();
  } finally {
    if (el.submitOpportunityOwnerButton) el.submitOpportunityOwnerButton.disabled = false;
  }
}

async function sendOpportunityToFeishu(noticeId, assignment = {}) {
  const result = await api("/api/opportunities/send-feishu", {
    method: "POST",
    body: JSON.stringify({
      notice_id: noticeId,
      owner_open_id: assignment.owner_open_id || "",
      owner_name: assignment.owner_name || "",
      create_task: assignment.create_task !== false,
      create_calendar_event: assignment.create_calendar_event !== false,
    }),
  });
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (item && result.workflow) item.workflow = result.workflow;
  renderOpportunities({ items: state.opportunities, summary: state.opportunitySummaryData });
  await refreshFeishu();
  const created = [result.task_guid && "任务", result.event_id && "日程"].filter(Boolean).join("与");
  const assignmentText = result.task_guid
    ? (result.task_assigned ? "，任务已绑定负责人" : "，任务未绑定飞书成员")
    : "";
  showToast(["sent", "started"].includes(result.status) ? `协同已更新${created ? `，已关联${created}` : ""}${assignmentText}` : "飞书协同未完成");
}

async function openOpportunityTeamDialog(noticeId) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityTeamDialog) return;
  state.pendingOpportunityTeamId = noticeId;
  el.opportunityTeamProject.textContent = item.title || "未命名机会";
  el.opportunityTeamMemberName.value = "";
  el.opportunityTeamOrganizationName.value = "";
  el.opportunityTeamResponsibility.value = "";
  el.opportunityTeamOrganizationType.value = "internal";
  el.opportunityTeamMemberSelect.innerHTML = '<option value="">正在读取通讯录</option>';
  el.opportunityTeamStatus.textContent = "正在读取应用授权范围";
  if (!el.opportunityTeamDialog.open) el.opportunityTeamDialog.showModal();
  try {
    const directory = await api("/api/integrations/feishu/users?limit=200");
    if (state.pendingOpportunityTeamId !== noticeId) return;
    const users = Array.isArray(directory.items) ? directory.items : [];
    el.opportunityTeamMemberSelect.innerHTML = [
      '<option value="">仅记录姓名，不绑定飞书成员</option>',
      ...users.map(
        (user) => `<option value="${escapeHtml(user.open_id || "")}" data-member-name="${escapeHtml(user.name || "")}">${escapeHtml(user.name || "未命名成员")}</option>`,
      ),
    ].join("");
    el.opportunityTeamStatus.textContent = users.length
      ? `可选择 ${users.length} 名授权成员，添加后作为飞书任务关注人`
      : "授权范围内暂无成员，可先保留本地团队记录";
  } catch (error) {
    if (state.pendingOpportunityTeamId !== noticeId) return;
    el.opportunityTeamMemberSelect.innerHTML = '<option value="">仅记录姓名，不绑定飞书成员</option>';
    el.opportunityTeamStatus.textContent = "通讯录暂不可用，可先保留本地团队记录";
  }
}

function closeOpportunityTeamDialog() {
  state.pendingOpportunityTeamId = "";
  el.opportunityTeamDialog?.close();
}

async function submitOpportunityTeam(event) {
  event.preventDefault();
  const noticeId = state.pendingOpportunityTeamId;
  const memberName = el.opportunityTeamMemberName?.value.trim() || "";
  const organizationType = el.opportunityTeamOrganizationType?.value || "internal";
  const organizationName = el.opportunityTeamOrganizationName?.value.trim() || "";
  if (!noticeId || !memberName) throw new Error("请填写成员姓名");
  if (organizationType === "partner" && !organizationName) throw new Error("伙伴成员必须填写所属组织");
  if (el.submitOpportunityTeamButton) el.submitOpportunityTeamButton.disabled = true;
  try {
    await api(`/api/opportunities/${encodeURIComponent(noticeId)}/team`, {
      method: "POST",
      body: JSON.stringify({
        member_open_id: el.opportunityTeamMemberSelect?.value || "",
        member_name: memberName,
        role: el.opportunityTeamRole?.value || "solution",
        organization_type: organizationType,
        organization_name: organizationName,
        responsibility: el.opportunityTeamResponsibility?.value.trim() || "",
        actor: "web:admin",
      }),
    });
    closeOpportunityTeamDialog();
    await refreshOpportunities();
    openOpportunityDetail(noticeId);
    showToast("团队成员已添加，飞书协同状态已刷新");
  } finally {
    if (el.submitOpportunityTeamButton) el.submitOpportunityTeamButton.disabled = false;
  }
}

async function removeOpportunityTeamMember(noticeId, memberId) {
  if (!noticeId || !memberId) return;
  if (!window.confirm("确认移除该协作成员？")) return;
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/team/${encodeURIComponent(memberId)}`, {
    method: "DELETE",
  });
  await refreshOpportunities();
  openOpportunityDetail(noticeId);
  showToast("团队成员已移除，飞书协同状态已刷新");
}

function openOpportunityStakeholderDialog(noticeId) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityStakeholderDialog) return;
  state.pendingOpportunityStakeholderId = noticeId;
  el.opportunityStakeholderProject.textContent = item.title || "未命名机会";
  el.opportunityStakeholderName.value = "";
  el.opportunityStakeholderOrganization.value = item.purchaser || "";
  el.opportunityStakeholderTitleInput.value = "";
  el.opportunityStakeholderRole.value = "economic_buyer";
  el.opportunityStakeholderInfluence.value = "medium";
  el.opportunityStakeholderStance.value = "unknown";
  el.opportunityStakeholderRelationship.value = "unknown";
  el.opportunityStakeholderNextAction.value = "";
  el.opportunityStakeholderEvidenceSource.value = "";
  el.opportunityStakeholderEvidenceUrl.value = "";
  el.opportunityStakeholderEvidenceText.value = "";
  const members = Array.isArray(item.team?.members) ? item.team.members : [];
  el.opportunityStakeholderOwner.innerHTML = [
    '<option value="">暂未指定</option>',
    ...members.map(
      (member) => `<option value="${escapeHtml(member.id || "")}">${escapeHtml(member.member_name || "未命名成员")} · ${escapeHtml(member.role_label || "协作成员")}</option>`,
    ),
  ].join("");
  if (!el.opportunityStakeholderDialog.open) el.opportunityStakeholderDialog.showModal();
}

function closeOpportunityStakeholderDialog() {
  state.pendingOpportunityStakeholderId = "";
  el.opportunityStakeholderDialog?.close();
}

async function submitOpportunityStakeholder(event) {
  event.preventDefault();
  const noticeId = state.pendingOpportunityStakeholderId;
  if (!noticeId) return;
  if (el.submitOpportunityStakeholderButton) el.submitOpportunityStakeholderButton.disabled = true;
  try {
    await api(`/api/opportunities/${encodeURIComponent(noticeId)}/stakeholders`, {
      method: "POST",
      body: JSON.stringify({
        stakeholder_name: el.opportunityStakeholderName?.value.trim() || "",
        organization_name: el.opportunityStakeholderOrganization?.value.trim() || "",
        job_title: el.opportunityStakeholderTitleInput?.value.trim() || "",
        role: el.opportunityStakeholderRole?.value || "economic_buyer",
        influence: el.opportunityStakeholderInfluence?.value || "medium",
        stance: el.opportunityStakeholderStance?.value || "unknown",
        relationship_strength: el.opportunityStakeholderRelationship?.value || "unknown",
        owner_member_id: el.opportunityStakeholderOwner?.value || "",
        next_action: el.opportunityStakeholderNextAction?.value.trim() || "",
        evidence_source: el.opportunityStakeholderEvidenceSource?.value.trim() || "",
        evidence_url: el.opportunityStakeholderEvidenceUrl?.value.trim() || "",
        evidence_text: el.opportunityStakeholderEvidenceText?.value.trim() || "",
        actor: "web:admin",
      }),
    });
    closeOpportunityStakeholderDialog();
    await refreshOpportunities();
    openOpportunityDetail(noticeId);
    showToast("关键人关系已保存，机会策略与准入已重新计算");
  } finally {
    if (el.submitOpportunityStakeholderButton) el.submitOpportunityStakeholderButton.disabled = false;
  }
}

async function removeOpportunityStakeholder(noticeId, stakeholderId) {
  if (!noticeId || !stakeholderId) return;
  if (!window.confirm("确认移除该关键人记录？历史审计仍会保留。")) return;
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/stakeholders/${encodeURIComponent(stakeholderId)}`, {
    method: "DELETE",
  });
  await refreshOpportunities();
  openOpportunityDetail(noticeId);
  showToast("关键人已移除，关系覆盖与资格门禁已刷新");
}

function openRelationshipActionDialog(noticeId, stakeholderId = "") {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.relationshipActionDialog) return;
  state.pendingRelationshipActionNoticeId = noticeId;
  state.pendingRelationshipActionStakeholderId = stakeholderId;
  el.relationshipActionProject.textContent = item.title || "未命名机会";
  const stakeholders = Array.isArray(item.stakeholder_map?.stakeholders)
    ? item.stakeholder_map.stakeholders
    : [];
  const members = Array.isArray(item.team?.members) ? item.team.members : [];
  el.relationshipActionStakeholder.innerHTML = [
    '<option value="">通用关系行动</option>',
    ...stakeholders.map(
      (stakeholder) => `<option value="${escapeHtml(stakeholder.id || "")}">${escapeHtml(stakeholder.stakeholder_name || "未命名关键人")} · ${escapeHtml(stakeholder.role_label || "角色待确认")}</option>`,
    ),
  ].join("");
  el.relationshipActionAssignee.innerHTML = [
    '<option value="">暂未指定</option>',
    ...members.map(
      (member) => `<option value="${escapeHtml(member.id || "")}">${escapeHtml(member.member_name || "未命名成员")} · ${escapeHtml(member.role_label || "协作成员")}</option>`,
    ),
  ].join("");
  el.relationshipActionStakeholder.value = stakeholderId;
  el.relationshipActionDueAt.value = relationshipActionDueDefault(item.bid_deadline);
  el.relationshipActionCreateFeishu.checked = true;
  applyRelationshipActionStakeholderDefaults();
  if (!el.relationshipActionDialog.open) el.relationshipActionDialog.showModal();
}

function applyRelationshipActionStakeholderDefaults() {
  const noticeId = state.pendingRelationshipActionNoticeId;
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  const stakeholderId = el.relationshipActionStakeholder?.value || "";
  state.pendingRelationshipActionStakeholderId = stakeholderId;
  const stakeholders = Array.isArray(item?.stakeholder_map?.stakeholders)
    ? item.stakeholder_map.stakeholders
    : [];
  const stakeholder = stakeholders.find((value) => value.id === stakeholderId);
  el.relationshipActionTitle.value = stakeholder?.next_action || "";
  el.relationshipActionAssignee.value = stakeholder?.owner_member_id || "";
  const resistant = stakeholder?.stance === "resistant" || stakeholder?.role === "blocker";
  const uncertain = stakeholder?.stance === "unknown";
  const weak = ["unknown", "weak"].includes(stakeholder?.relationship_strength);
  el.relationshipActionType.value = resistant ? "mitigation" : uncertain ? "validation" : "engagement";
  el.relationshipActionPriority.value = resistant && stakeholder?.influence === "high"
    ? "critical"
    : stakeholder?.influence === "high" || resistant || weak
      ? "high"
      : "normal";
}

function relationshipActionDueDefault(bidDeadline) {
  const now = new Date();
  let due = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000);
  due.setHours(17, 0, 0, 0);
  const deadline = bidDeadline ? new Date(bidDeadline.replace(" ", "T")) : null;
  if (deadline && !Number.isNaN(deadline.getTime()) && deadline < due) {
    due = new Date(deadline.getTime() - 24 * 60 * 60 * 1000);
  }
  if (due <= now) due = new Date(now.getTime() + 60 * 60 * 1000);
  const pad = (value) => String(value).padStart(2, "0");
  return `${due.getFullYear()}-${pad(due.getMonth() + 1)}-${pad(due.getDate())}T${pad(due.getHours())}:${pad(due.getMinutes())}`;
}

function closeRelationshipActionDialog() {
  state.pendingRelationshipActionNoticeId = "";
  state.pendingRelationshipActionStakeholderId = "";
  el.relationshipActionDialog?.close();
}

async function submitRelationshipAction(event) {
  event.preventDefault();
  const noticeId = state.pendingRelationshipActionNoticeId;
  if (!noticeId) return;
  if (el.submitRelationshipActionButton) el.submitRelationshipActionButton.disabled = true;
  try {
    const stakeholderId = el.relationshipActionStakeholder?.value || "";
    const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/relationship-actions`, {
      method: "POST",
      body: JSON.stringify({
        stakeholder_id: stakeholderId,
        title: el.relationshipActionTitle?.value.trim() || "",
        action_type: el.relationshipActionType?.value || "engagement",
        priority: el.relationshipActionPriority?.value || "normal",
        assignee_member_id: el.relationshipActionAssignee?.value || "",
        due_at: el.relationshipActionDueAt?.value || "",
        source_type: stakeholderId ? "stakeholder_strategy" : "manual",
        source_ref: stakeholderId,
        create_feishu_task: Boolean(el.relationshipActionCreateFeishu?.checked),
        actor: "web:admin",
      }),
    });
    closeRelationshipActionDialog();
    await refreshOpportunities();
    openOpportunityDetail(noticeId);
    showToast(result.status === "partial" ? "行动已保存，飞书任务待重试" : "关系行动已创建并进入跟踪");
  } finally {
    if (el.submitRelationshipActionButton) el.submitRelationshipActionButton.disabled = false;
  }
}

async function syncRelationshipActionTask(noticeId, actionId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/relationship-actions/${encodeURIComponent(actionId)}/feishu-task`, {
    method: "POST",
  });
  await refreshOpportunities();
  openOpportunityDetail(noticeId);
  showToast("关系行动已同步到飞书任务");
}

async function completeRelationshipAction(noticeId, actionId) {
  const outcome = window.prompt("请记录行动结果或客户反馈，该内容将进入机会审计。", "");
  if (outcome === null) return;
  if (!outcome.trim()) throw new Error("完成行动前必须记录结果");
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/relationship-actions/${encodeURIComponent(actionId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: "completed",
      outcome_note: outcome.trim(),
      actor: "web:admin",
    }),
  });
  await refreshOpportunities();
  openOpportunityDetail(noticeId);
  showToast("行动结果已记录，资格门禁已重新计算");
}

function openOpportunityOutcomeDialog(noticeId, action = "", editing = false) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityOutcomeDialog) return;
  const existing = item.outcome || {};
  const resolvedAction = action || (existing.result === "won" ? "mark_won" : "mark_lost");
  const won = resolvedAction === "mark_won";
  state.pendingOpportunityOutcomeNoticeId = noticeId;
  state.pendingOpportunityOutcomeAction = resolvedAction;
  state.editingOpportunityOutcome = Boolean(editing);
  el.opportunityOutcomeTitle.textContent = editing ? "修订投标复盘" : won ? "记录中标复盘" : "记录失标复盘";
  el.opportunityOutcomeProject.textContent = item.title || "未命名机会";
  el.opportunityOutcomeReason.value = existing.reason_code || (won ? "technical_fit" : "price");
  el.opportunityOutcomeWinner.value = existing.winner_name || "";
  el.opportunityOutcomeAmount.value = existing.award_amount || "";
  el.opportunityOutcomeCurrency.value = existing.currency || "";
  el.opportunityOutcomeSummary.value = existing.summary || "";
  el.opportunityOutcomeLessons.value = existing.lessons || "";
  el.opportunityOutcomeFeedback.value = existing.customer_feedback || "";
  el.opportunityOutcomeFollowUp.value = existing.follow_up_action || "";
  el.opportunityOutcomeEvidenceUrl.value = existing.evidence_url || "";
  el.opportunityOutcomeEvidenceText.value = existing.evidence_text || "";
  el.opportunityOutcomeStatus.textContent = won
    ? "中标结论将进入胜因分析、价格基准和后续策略知识库。"
    : "失标结论将进入败因分布、竞争者画像和后续策略知识库。";
  if (!el.opportunityOutcomeDialog.open) el.opportunityOutcomeDialog.showModal();
}

function closeOpportunityOutcomeDialog() {
  state.pendingOpportunityOutcomeNoticeId = "";
  state.pendingOpportunityOutcomeAction = "";
  state.editingOpportunityOutcome = false;
  el.opportunityOutcomeDialog?.close();
}

async function submitOpportunityOutcome(event) {
  event.preventDefault();
  const noticeId = state.pendingOpportunityOutcomeNoticeId;
  const action = state.pendingOpportunityOutcomeAction;
  const editing = state.editingOpportunityOutcome;
  if (!noticeId || !action) return;
  const amount = el.opportunityOutcomeAmount?.value.trim() || "";
  const currency = el.opportunityOutcomeCurrency?.value.trim().toUpperCase() || "";
  const evidenceUrl = el.opportunityOutcomeEvidenceUrl?.value.trim() || "";
  const evidenceText = el.opportunityOutcomeEvidenceText?.value.trim() || "";
  if (amount && !currency) throw new Error("填写成交金额时必须填写三位币种代码");
  if (!evidenceUrl && !evidenceText) throw new Error("请填写结果证据链接或证据摘录");
  const outcome = {
    result: action === "mark_won" ? "won" : "lost",
    reason_code: el.opportunityOutcomeReason?.value || "other",
    winner_name: el.opportunityOutcomeWinner?.value.trim() || "",
    award_amount: amount || null,
    currency,
    summary: el.opportunityOutcomeSummary?.value.trim() || "",
    lessons: el.opportunityOutcomeLessons?.value.trim() || "",
    customer_feedback: el.opportunityOutcomeFeedback?.value.trim() || "",
    follow_up_action: el.opportunityOutcomeFollowUp?.value.trim() || "",
    evidence_url: evidenceUrl,
    evidence_text: evidenceText,
  };
  if (el.submitOpportunityOutcomeButton) el.submitOpportunityOutcomeButton.disabled = true;
  try {
    if (editing) {
      await api(`/api/opportunities/${encodeURIComponent(noticeId)}/outcome`, {
        method: "PUT",
        body: JSON.stringify({ actor_name: "admin", outcome }),
      });
    } else {
      await api(`/api/opportunities/${encodeURIComponent(noticeId)}/actions`, {
        method: "POST",
        body: JSON.stringify({ action, actor_name: "admin", outcome }),
      });
    }
    closeOpportunityOutcomeDialog();
    await refreshOpportunities();
    if (el.opportunityDetailDialog?.open) openOpportunityDetail(noticeId);
    showToast(editing ? "投标复盘已修订并同步" : "投标结果已确认，复盘样本已进入策略知识库");
  } finally {
    if (el.submitOpportunityOutcomeButton) el.submitOpportunityOutcomeButton.disabled = false;
  }
}

async function applyOpportunityAction(noticeId, action) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  const descriptor = item?.action_contract?.actions?.find((value) => value.action === action);
  if (descriptor?.requires_outcome) {
    openOpportunityOutcomeDialog(noticeId, action);
    return;
  }
  let reason = "";
  if (descriptor?.accepts_reason) {
    const input = window.prompt(
      action === "acknowledge_change" ? "请填写复核结论或影响说明（可留空）" : "请填写决策依据（可留空）",
      "",
    );
    if (input === null) return;
    reason = input.trim();
  }
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, actor_name: "admin", reason }),
  });
  await refreshOpportunities();
  if (el.opportunityDetailDialog?.open) openOpportunityDetail(noticeId);
  const workflow = result.workflow || {};
  showToast(action === "acknowledge_change" ? "公告变更已复核，请重新完成投标决策" : `机会已更新：${workflow.stage_label || decisionLabel(workflow.decision)}`);
}

async function sendOpportunityEscalations() {
  const result = await api("/api/opportunities/escalations/send-feishu", {
    method: "POST",
    body: JSON.stringify({ force: true }),
  });
  showToast(
    result.status === "sent"
      ? `已发送 ${result.escalation_count} 条协同升级 · 决策 ${result.decision_count || 0} · 主任务 ${result.task_count || 0} · 关系行动 ${result.relationship_action_count || 0} · 变更复核 ${result.change_review_count || 0}`
      : "当前没有需要发送的协同升级",
  );
}

async function sendOpportunityBriefing() {
  const result = await api("/api/opportunities/briefing/send-feishu", {
    method: "POST",
    body: JSON.stringify({ force: true }),
  });
  await refreshFeishu();
  showToast(
    result.status === "sent"
      ? `机会经营晨报已发送，共 ${result.opportunity_count} 条机会`
      : "当前机会池为空，未发送晨报",
  );
}

async function sendOpportunityChanges() {
  if (el.sendOpportunityChangesButton) el.sendOpportunityChangesButton.disabled = true;
  try {
    const result = await api("/api/opportunities/changes/send-feishu", {
      method: "POST",
      body: JSON.stringify({ limit: 100 }),
    });
    showToast(
      result.status === "sent"
        ? `已向 ${result.receiver_count || 0} 位负责人推送 ${result.sent_count || 0} 条公告变更`
        : result.status === "partial"
          ? `已推送 ${result.sent_count || 0} 条，${result.failed_count || 0} 条将在下次继续重试`
          : result.status === "failed"
            ? `公告变更推送失败 ${result.failed_count || 0} 条，将在下次继续重试`
            : "当前没有待推送的公告变更",
    );
  } finally {
    if (el.sendOpportunityChangesButton) el.sendOpportunityChangesButton.disabled = false;
  }
}

async function syncFeishuTasks() {
  if (el.syncFeishuTasksButton) el.syncFeishuTasksButton.disabled = true;
  try {
    const result = await api("/api/opportunities/tasks/sync", {
      method: "POST",
      body: JSON.stringify({ limit: 200 }),
    });
    await Promise.all([refreshOpportunities(), refreshFeishu()]);
    const relationship = result.relationship_actions || {};
    if (!result.scanned_count && !relationship.scanned_count) {
      showToast("当前没有已关联的飞书任务");
      return;
    }
    showToast(
      `主任务 ${result.scanned_count || 0} · 完成 ${result.completed_count || 0} · 逾期 ${result.overdue_count || 0}；关系行动 ${relationship.scanned_count || 0} · 完成 ${relationship.completed_count || 0} · 逾期 ${relationship.overdue_count || 0} · 结果待补 ${relationship.outcome_pending_count || 0}`,
    );
  } finally {
    if (el.syncFeishuTasksButton) el.syncFeishuTasksButton.disabled = false;
  }
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
  const [payload] = await Promise.all([refreshHealth(), refreshFeishu()]);
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
    model_strategy: el.modelStrategySelect?.value || "config",
    delivery_channels: el.feishuDeliveryInput?.checked
      ? ["web", "outbox", "feishu"]
      : ["web", "outbox"],
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

function subscriptionDeliveryText(item) {
  const channels = Array.isArray(item.delivery_channels) ? item.delivery_channels : ["web", "outbox"];
  if (!channels.includes("feishu")) return "Web 下载";
  const status = item.last_feishu_status;
  if (status === "sent") return "Web + 飞书已发送";
  if (status === "failed") return "Web + 飞书失败";
  return "Web + 飞书";
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
  const intervalHours = hour.match(/^\*\/(\d+)$/u)?.[1];
  if (minute === "0" && intervalHours && day === "*" && month === "*" && weekday === "*") {
    return `每 ${intervalHours} 小时整点`;
  }
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
    refreshOpportunities(),
    refreshMemoryWeekly(),
    refreshFeishu(),
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
  document.addEventListener("submit", (event) => {
    const requirementForm = event.target.closest("[data-opportunity-requirements-form]");
    if (requirementForm) {
      event.preventDefault();
      saveOpportunityRequirement(requirementForm).catch(toastError("要求账本保存失败"));
      return;
    }
    const form = event.target.closest("[data-opportunity-facts]");
    if (!form) return;
    event.preventDefault();
    saveOpportunityFacts(form).catch(toastError("事实核验保存失败"));
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  el.notificationButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePopover("notifications");
  });
  el.mobileNavButton?.addEventListener("click", () => {
    const open = el.topNavigation?.classList.toggle("open") || false;
    el.mobileNavButton.setAttribute("aria-expanded", String(open));
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
    const convertOrganizationMemoryTarget = event.target.closest(
      "[data-convert-organization-memory]",
    );
    if (convertOrganizationMemoryTarget) {
      try {
        openOrganizationConvertDialog(
          convertOrganizationMemoryTarget.dataset.convertOrganizationMemory,
        );
      } catch (error) {
        toastError("组织记忆转换失败")(error);
      }
      return;
    }
    const deleteOutboxTarget = event.target.closest("[data-delete-outbox-name]");
    if (deleteOutboxTarget) {
      deleteOutboxFile(deleteOutboxTarget.dataset.deleteOutboxName).catch(toastError("删除 Word 失败"));
      return;
    }
    const sendFeishuTarget = event.target.closest("[data-send-feishu-name]");
    if (sendFeishuTarget) {
      sendReportToFeishu(
        sendFeishuTarget.dataset.sendFeishuName,
        sendFeishuTarget.dataset.sendFeishuRun || "",
        sendFeishuTarget.dataset.sendFeishuSubscription || "",
      ).catch(toastError("飞书发送失败"));
      return;
    }
    const sendOpportunityTarget = event.target.closest("[data-send-opportunity-feishu]");
    if (sendOpportunityTarget) {
      openOpportunityOwnerDialog(sendOpportunityTarget.dataset.sendOpportunityFeishu).catch(
        toastError("负责人目录加载失败"),
      );
      return;
    }
    const opportunityActionTarget = event.target.closest("[data-opportunity-action]");
    if (opportunityActionTarget) {
      applyOpportunityAction(
        opportunityActionTarget.dataset.opportunityId,
        opportunityActionTarget.dataset.opportunityAction,
      ).catch(toastError("机会状态更新失败"));
      return;
    }
    const editOutcomeTarget = event.target.closest("[data-edit-opportunity-outcome]");
    if (editOutcomeTarget) {
      openOpportunityOutcomeDialog(editOutcomeTarget.dataset.editOpportunityOutcome, "", true);
      return;
    }
    const addOpportunityTeamTarget = event.target.closest("[data-add-opportunity-team]");
    if (addOpportunityTeamTarget) {
      openOpportunityTeamDialog(addOpportunityTeamTarget.dataset.addOpportunityTeam).catch(
        toastError("团队成员目录加载失败"),
      );
      return;
    }
    const removeOpportunityTeamTarget = event.target.closest("[data-remove-opportunity-team]");
    if (removeOpportunityTeamTarget) {
      removeOpportunityTeamMember(
        removeOpportunityTeamTarget.dataset.opportunityId || "",
        removeOpportunityTeamTarget.dataset.removeOpportunityTeam,
      ).catch(toastError("移除团队成员失败"));
      return;
    }
    const editRequirementTarget = event.target.closest("[data-edit-opportunity-requirement]");
    if (editRequirementTarget) {
      editOpportunityRequirement(
        editRequirementTarget.dataset.opportunityId || "",
        editRequirementTarget.dataset.editOpportunityRequirement || "",
      );
      return;
    }
    const resetRequirementTarget = event.target.closest("[data-reset-opportunity-requirement]");
    if (resetRequirementTarget) {
      resetOpportunityRequirementForm(resetRequirementTarget.dataset.resetOpportunityRequirement || "");
      return;
    }
    const extractRequirementsTarget = event.target.closest("[data-extract-opportunity-requirements]");
    if (extractRequirementsTarget) {
      extractOpportunityRequirements(
        extractRequirementsTarget.dataset.extractOpportunityRequirements || "",
      ).catch(toastError("规则提取失败"));
      return;
    }
    const addStakeholderTarget = event.target.closest("[data-add-opportunity-stakeholder]");
    if (addStakeholderTarget) {
      openOpportunityStakeholderDialog(addStakeholderTarget.dataset.addOpportunityStakeholder);
      return;
    }
    const addRelationshipActionTarget = event.target.closest("[data-add-relationship-action]");
    if (addRelationshipActionTarget) {
      openRelationshipActionDialog(addRelationshipActionTarget.dataset.addRelationshipAction);
      return;
    }
    const stakeholderActionTarget = event.target.closest("[data-create-stakeholder-action]");
    if (stakeholderActionTarget) {
      openRelationshipActionDialog(
        stakeholderActionTarget.dataset.opportunityId || "",
        stakeholderActionTarget.dataset.createStakeholderAction || "",
      );
      return;
    }
    const syncRelationshipActionTarget = event.target.closest("[data-sync-relationship-action]");
    if (syncRelationshipActionTarget) {
      syncRelationshipActionTask(
        syncRelationshipActionTarget.dataset.opportunityId || "",
        syncRelationshipActionTarget.dataset.syncRelationshipAction || "",
      ).catch(toastError("关系行动同步失败"));
      return;
    }
    const completeRelationshipActionTarget = event.target.closest("[data-complete-relationship-action]");
    if (completeRelationshipActionTarget) {
      completeRelationshipAction(
        completeRelationshipActionTarget.dataset.opportunityId || "",
        completeRelationshipActionTarget.dataset.completeRelationshipAction || "",
      ).catch(toastError("关系行动完成失败"));
      return;
    }
    const removeStakeholderTarget = event.target.closest("[data-remove-opportunity-stakeholder]");
    if (removeStakeholderTarget) {
      removeOpportunityStakeholder(
        removeStakeholderTarget.dataset.opportunityId || "",
        removeStakeholderTarget.dataset.removeOpportunityStakeholder,
      ).catch(toastError("移除关键人失败"));
      return;
    }
    const opportunityEscalationTarget = event.target.closest("[data-send-opportunity-escalations]");
    if (opportunityEscalationTarget) {
      sendOpportunityEscalations().catch(toastError("飞书升级摘要发送失败"));
      return;
    }
    const viewOpportunityTarget = event.target.closest("[data-view-opportunity]");
    if (viewOpportunityTarget) {
      openOpportunityDetail(viewOpportunityTarget.dataset.viewOpportunity);
      return;
    }
    const closeOpportunityTarget = event.target.closest("[data-close-opportunity-detail]");
    if (closeOpportunityTarget) {
      el.opportunityDetailDialog?.close();
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
  el.opportunityDetailDialog?.addEventListener("click", (event) => {
    if (event.target === el.opportunityDetailDialog) el.opportunityDetailDialog.close();
  });
  el.opportunityOwnerDialog?.addEventListener("click", (event) => {
    if (event.target === el.opportunityOwnerDialog) closeOpportunityOwnerDialog();
  });
  el.opportunityOwnerDialog?.addEventListener("close", () => {
    state.pendingOpportunityId = "";
  });
  el.opportunityOwnerSelect?.addEventListener("change", () => {
    const option = el.opportunityOwnerSelect.selectedOptions?.[0];
    const ownerName = option?.dataset.ownerName || "";
    if (ownerName && el.opportunityOwnerName) el.opportunityOwnerName.value = ownerName;
  });
  el.opportunityOwnerForm?.addEventListener("submit", (event) =>
    submitOpportunityOwner(event).catch(toastError("负责人分配失败")),
  );
  el.closeOpportunityOwnerButton?.addEventListener("click", closeOpportunityOwnerDialog);
  el.cancelOpportunityOwnerButton?.addEventListener("click", closeOpportunityOwnerDialog);
  el.opportunityTeamDialog?.addEventListener("click", (event) => {
    if (event.target === el.opportunityTeamDialog) closeOpportunityTeamDialog();
  });
  el.opportunityTeamDialog?.addEventListener("close", () => {
    state.pendingOpportunityTeamId = "";
  });
  el.opportunityTeamMemberSelect?.addEventListener("change", () => {
    const option = el.opportunityTeamMemberSelect.selectedOptions?.[0];
    const memberName = option?.dataset.memberName || "";
    if (memberName && el.opportunityTeamMemberName) el.opportunityTeamMemberName.value = memberName;
  });
  el.opportunityTeamOrganizationType?.addEventListener("change", () => {
    const partner = el.opportunityTeamOrganizationType.value === "partner";
    if (el.opportunityTeamOrganizationName) el.opportunityTeamOrganizationName.required = partner;
  });
  el.opportunityTeamForm?.addEventListener("submit", (event) =>
    submitOpportunityTeam(event).catch(toastError("团队成员添加失败")),
  );
  el.closeOpportunityTeamButton?.addEventListener("click", closeOpportunityTeamDialog);
  el.cancelOpportunityTeamButton?.addEventListener("click", closeOpportunityTeamDialog);
  el.opportunityStakeholderDialog?.addEventListener("click", (event) => {
    if (event.target === el.opportunityStakeholderDialog) closeOpportunityStakeholderDialog();
  });
  el.opportunityStakeholderDialog?.addEventListener("close", () => {
    state.pendingOpportunityStakeholderId = "";
  });
  el.opportunityStakeholderForm?.addEventListener("submit", (event) =>
    submitOpportunityStakeholder(event).catch(toastError("关键人保存失败")),
  );
  el.closeOpportunityStakeholderButton?.addEventListener("click", closeOpportunityStakeholderDialog);
  el.cancelOpportunityStakeholderButton?.addEventListener("click", closeOpportunityStakeholderDialog);
  el.relationshipActionDialog?.addEventListener("click", (event) => {
    if (event.target === el.relationshipActionDialog) closeRelationshipActionDialog();
  });
  el.relationshipActionDialog?.addEventListener("close", () => {
    state.pendingRelationshipActionNoticeId = "";
    state.pendingRelationshipActionStakeholderId = "";
  });
  el.relationshipActionStakeholder?.addEventListener(
    "change",
    applyRelationshipActionStakeholderDefaults,
  );
  el.relationshipActionForm?.addEventListener("submit", (event) =>
    submitRelationshipAction(event).catch(toastError("关系行动创建失败")),
  );
  el.closeRelationshipActionButton?.addEventListener("click", closeRelationshipActionDialog);
  el.cancelRelationshipActionButton?.addEventListener("click", closeRelationshipActionDialog);
  el.opportunityOutcomeDialog?.addEventListener("click", (event) => {
    if (event.target === el.opportunityOutcomeDialog) closeOpportunityOutcomeDialog();
  });
  el.opportunityOutcomeDialog?.addEventListener("close", () => {
    state.pendingOpportunityOutcomeNoticeId = "";
    state.pendingOpportunityOutcomeAction = "";
    state.editingOpportunityOutcome = false;
  });
  el.opportunityOutcomeForm?.addEventListener("submit", (event) =>
    submitOpportunityOutcome(event).catch(toastError("投标复盘保存失败")),
  );
  el.closeOpportunityOutcomeButton?.addEventListener("click", closeOpportunityOutcomeDialog);
  el.cancelOpportunityOutcomeButton?.addEventListener("click", closeOpportunityOutcomeDialog);
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
  el.modelStrategySelect?.addEventListener("change", renderSmartStart);
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
  el.refreshOpportunitiesButton?.addEventListener("click", () =>
    refreshOpportunities().catch(toastError("机会情报刷新失败")),
  );
  el.sendOpportunityBriefingButton?.addEventListener("click", () =>
    sendOpportunityBriefing().catch(toastError("机会经营晨报发送失败")),
  );
  el.sendOpportunityChangesButton?.addEventListener("click", () =>
    sendOpportunityChanges().catch(toastError("公告变更推送失败")),
  );
  el.syncFeishuTasksButton?.addEventListener("click", () =>
    syncFeishuTasks().catch(toastError("飞书任务同步失败")),
  );
  el.opportunityLevelFilter?.addEventListener("change", () =>
    refreshOpportunities().catch(toastError("机会情报筛选失败")),
  );
  el.opportunityTopicFilter?.addEventListener("change", () =>
    refreshOpportunities().catch(toastError("机会品类筛选失败")),
  );
  el.opportunitySortSelect?.addEventListener("change", () =>
    refreshOpportunities().catch(toastError("机会情报排序失败")),
  );
  el.loadMoreOpportunitiesButton?.addEventListener("click", () => {
    state.opportunityVisible += opportunityPageSize();
    renderOpportunities({
      items: state.opportunities,
      summary: state.opportunitySummaryData,
    });
  });
  el.refreshMemoryButton?.addEventListener("click", () =>
    refreshMemoryWeekly().catch(toastError("用户记忆刷新失败")),
  );
  el.refreshOrganizationButton?.addEventListener("click", () =>
    refreshOrganizationWorkspaces().catch(toastError("组织协作刷新失败")),
  );
  el.organizationWorkspaceSelect?.addEventListener("change", () => {
    state.organizationWorkspaceId = el.organizationWorkspaceSelect.value;
    renderOrganizationSummary();
    refreshOrganizationMemories().catch(toastError("组织记忆加载失败"));
  });
  el.organizationMemorySearch?.addEventListener(
    "input",
    debounce(() => refreshOrganizationMemories().catch(toastError("组织记忆检索失败")), 220),
  );
  el.organizationMemoryTypeFilter?.addEventListener("change", () =>
    refreshOrganizationMemories().catch(toastError("组织记忆筛选失败")),
  );
  el.organizationMemoryForm?.addEventListener("submit", (event) =>
    saveOrganizationMemory(event).catch(toastError("组织记忆保存失败")),
  );
  el.createOrganizationWorkspaceButton?.addEventListener("click", () =>
    openOrganizationGroupDialog("create").catch(toastError("飞书成员加载失败")),
  );
  el.inviteOrganizationMembersButton?.addEventListener("click", () =>
    openOrganizationGroupDialog("invite").catch(toastError("飞书成员加载失败")),
  );
  el.organizationGroupForm?.addEventListener("submit", (event) =>
    submitOrganizationGroup(event).catch(toastError("飞书群同步失败")),
  );
  el.closeOrganizationGroupButton?.addEventListener("click", closeOrganizationGroupDialog);
  el.cancelOrganizationGroupButton?.addEventListener("click", closeOrganizationGroupDialog);
  el.organizationGroupDialog?.addEventListener("click", (event) => {
    if (event.target === el.organizationGroupDialog) closeOrganizationGroupDialog();
  });
  el.organizationConvertTarget?.addEventListener("change", syncOrganizationConvertFields);
  el.organizationConvertForm?.addEventListener("submit", (event) =>
    submitOrganizationConversion(event).catch(toastError("组织记忆转换失败")),
  );
  el.closeOrganizationConvertButton?.addEventListener("click", closeOrganizationConvertDialog);
  el.cancelOrganizationConvertButton?.addEventListener("click", closeOrganizationConvertDialog);
  el.organizationConvertDialog?.addEventListener("click", (event) => {
    if (event.target === el.organizationConvertDialog) closeOrganizationConvertDialog();
  });
  el.saveMemoryButton?.addEventListener("click", () =>
    saveMemoryWeekly().catch(toastError("用户记忆保存失败")),
  );
  el.sendMemoryFeishuButton?.addEventListener("click", () =>
    sendMemoryWeeklyToFeishu().catch(toastError("周报发送失败")),
  );
  el.memoryGeneratedAdvice?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-advice-id][data-advice-status]");
    if (!button) return;
    button.disabled = true;
    updateAdviceFeedback(button.dataset.adviceId, button.dataset.adviceStatus).catch((error) => {
      button.disabled = false;
      toastError("建议状态更新失败")(error);
    });
  });
  el.refreshFeishuButton?.addEventListener("click", () =>
    refreshFeishu().catch(toastError("飞书状态刷新失败")),
  );
  el.testFeishuButton?.addEventListener("click", () =>
    testFeishuConnection().catch(toastError("飞书连接测试失败")),
  );
  el.importFeishuLeadsButton?.addEventListener("click", () =>
    importFeishuPartnerLeads().catch(toastError("伙伴线索导入失败")),
  );
  el.configureFeishuReceiverButton?.addEventListener("click", () =>
    openFeishuReceiverEditor().catch(toastError("飞书会话加载失败")),
  );
  el.saveFeishuReceiverButton?.addEventListener("click", () =>
    saveFeishuReceiverSelection().catch(toastError("接收会话保存失败")),
  );
  el.cancelFeishuReceiverButton?.addEventListener("click", () => {
    if (el.feishuReceiverEditor) el.feishuReceiverEditor.hidden = true;
  });
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
  const requestedView = new URLSearchParams(window.location.search).get("view") || "";
  if (document.getElementById(requestedView)?.classList.contains("view")) showView(requestedView);
}

init().catch((error) => showToast(`页面初始化失败：${error.message}`));
