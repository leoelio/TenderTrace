const state = {
  currentRunId: null,
  running: false,
  progressCard: null,
  health: null,
  finalsHome: null,
  runs: [],
  outbox: [],
  subscriptions: [],
  sources: [],
  sourceAlerts: null,
  evaluation: null,
  memory: null,
  organizationWorkspaces: [],
  organizationMemories: [],
  bidMemory: null,
  bidMemorySelectedNodeId: "",
  pendingBidMemoryArchiveNoticeId: "",
  opportunityRadar: null,
  battleMap: null,
  battleScope: "global",
  battleTimelineIndex: -1,
  battlePlayTimer: null,
  battleEventSource: null,
  battleRevision: "",
  trainingCatalog: [],
  trainingSelectedScenarioId: "",
  trainingSession: null,
  trainingTimer: null,
  liveChallenge: null,
  liveChallengeHistory: [],
  liveChallengePollTimer: null,
  demoReliability: null,
  demoActiveRehearsal: null,
  demoLayoutAuditRunning: false,
  visualAuditRunning: false,
  visualSystem: null,
  radarScope: "all",
  radarSelectedLocationId: "",
  radarMotionDisabled: false,
  motionDisabled: false,
  presentationMode: false,
  organizationWorkspaceId: "",
  feishuDeliveryWorkspaceId: "",
  organizationGroupMode: "create",
  organizationConvertMemoryId: "",
  partnerEntities: [],
  partnerEntityId: "",
  partnerProfile: null,
  feishu: null,
  opportunities: [],
  opportunitySummaryData: {},
  opportunityRequirementPayloads: {},
  opportunityBidWorkplans: {},
  decisionSandboxPayloads: {},
  selectedDecisionScenarios: {},
  opportunityVisible: 20,
  pendingOpportunityId: "",
  pendingOpportunityTeamId: "",
  pendingOpportunityStakeholderId: "",
  pendingRelationshipActionNoticeId: "",
  pendingRelationshipActionStakeholderId: "",
  pendingOpportunityOutcomeNoticeId: "",
  pendingOpportunityOutcomeAction: "",
  editingOpportunityOutcome: false,
  openDigitalTwinNoticeId: "",
  digitalTwinRefreshTimer: null,
  digitalTwinRefreshRunning: false,
  opportunityDetailRequestSequence: 0,
  evidenceMicroscopeNoticeId: "",
  evidenceMicroscopePayload: null,
  outboxFilters: { query: "", status: "all", sort: "created_desc", expanded: false },
  runFilters: { query: "", status: "all", sort: "started_desc", expanded: false },
  actionModeTouched: false,
  intentConfirmation: { query: "", confirmed: false },
  goldAnnotationCaseId: "",
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
  finalsHomeRefreshButton: document.querySelector("#finalsHomeRefreshButton"),
  finalsHomeIntentForm: document.querySelector("#finalsHomeIntentForm"),
  finalsHomeIntentInput: document.querySelector("#finalsHomeIntentInput"),
  finalsHomeDataAsOf: document.querySelector("#finalsHomeDataAsOf"),
  finalsHomeLocalState: document.querySelector("#finalsHomeLocalState"),
  finalsHomeFeishuState: document.querySelector("#finalsHomeFeishuState"),
  finalsHomeReplayState: document.querySelector("#finalsHomeReplayState"),
  finalsHomeOpportunityCount: document.querySelector("#finalsHomeOpportunityCount"),
  finalsHomeRecentCount: document.querySelector("#finalsHomeRecentCount"),
  finalsHomeRegionCount: document.querySelector("#finalsHomeRegionCount"),
  finalsHomeSourceCount: document.querySelector("#finalsHomeSourceCount"),
  finalsHomeRadarMeta: document.querySelector("#finalsHomeRadarMeta"),
  finalsHomeCaseState: document.querySelector("#finalsHomeCaseState"),
  finalsHomeCaseTitle: document.querySelector("#finalsHomeCaseTitle"),
  finalsHomeCaseMeta: document.querySelector("#finalsHomeCaseMeta"),
  finalsHomeScoreGrid: document.querySelector("#finalsHomeScoreGrid"),
  finalsHomeCaseEvidence: document.querySelector("#finalsHomeCaseEvidence"),
  finalsHomeActions: document.querySelector("#finalsHomeActions"),
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
  motionToggleButton: document.querySelector("#motionToggleButton"),
  presentationModeButton: document.querySelector("#presentationModeButton"),
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
  workbenchContext: document.querySelector("#workbenchContext"),
  intentPreview: document.querySelector("#intentPreview"),
  searchDepthSelect: document.querySelector("#searchDepthSelect"),
  modelStrategySelect: document.querySelector("#modelStrategySelect"),
  feishuDeliveryInput: document.querySelector("#feishuDeliveryInput"),
  feishuDeliveryWorkspaceField: document.querySelector("#feishuDeliveryWorkspaceField"),
  feishuDeliveryWorkspace: document.querySelector("#feishuDeliveryWorkspace"),
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
  evidenceMicroscopeDialog: document.querySelector("#evidenceMicroscopeDialog"),
  evidenceMicroscopeTitle: document.querySelector("#evidenceMicroscopeTitle"),
  evidenceMicroscopeMeta: document.querySelector("#evidenceMicroscopeMeta"),
  evidenceMicroscopeContent: document.querySelector("#evidenceMicroscopeContent"),
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
  goldAnnotationDialog: document.querySelector("#goldAnnotationDialog"),
  goldAnnotationForm: document.querySelector("#goldAnnotationForm"),
  goldAnnotationCase: document.querySelector("#goldAnnotationCase"),
  goldAnnotationReviewer: document.querySelector("#goldAnnotationReviewer"),
  goldAnnotationSourceSite: document.querySelector("#goldAnnotationSourceSite"),
  goldAnnotationTitleInput: document.querySelector("#goldAnnotationTitleInput"),
  goldAnnotationNoticeId: document.querySelector("#goldAnnotationNoticeId"),
  goldAnnotationSourceUrl: document.querySelector("#goldAnnotationSourceUrl"),
  goldAnnotationPublishTime: document.querySelector("#goldAnnotationPublishTime"),
  goldAnnotationNote: document.querySelector("#goldAnnotationNote"),
  closeGoldAnnotationButton: document.querySelector("#closeGoldAnnotationButton"),
  cancelGoldAnnotationButton: document.querySelector("#cancelGoldAnnotationButton"),
  businessMeasurementMetrics: document.querySelector("#businessMeasurementMetrics"),
  businessMeasurementList: document.querySelector("#businessMeasurementList"),
  businessMeasurementForm: document.querySelector("#businessMeasurementForm"),
  businessMeasurementStatus: document.querySelector("#businessMeasurementStatus"),
  businessMeasurementProtocol: document.querySelector("#businessMeasurementProtocol"),
  businessDirectionCoverage: document.querySelector("#businessDirectionCoverage"),
  businessMetricDetails: document.querySelector("#businessMetricDetails"),
  businessExperimentList: document.querySelector("#businessExperimentList"),
  businessFormulaList: document.querySelector("#businessFormulaList"),
  businessSampleCount: document.querySelector("#businessSampleCount"),
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
  partnerWorkspaceSelect: document.querySelector("#partnerWorkspaceSelect"),
  partnerSearchInput: document.querySelector("#partnerSearchInput"),
  partnerSearchButton: document.querySelector("#partnerSearchButton"),
  partnerAggregateButton: document.querySelector("#partnerAggregateButton"),
  partnerEvaluateButton: document.querySelector("#partnerEvaluateButton"),
  partnerSnapshotButton: document.querySelector("#partnerSnapshotButton"),
  partnerEntityCount: document.querySelector("#partnerEntityCount"),
  partnerEntityForm: document.querySelector("#partnerEntityForm"),
  partnerEntityName: document.querySelector("#partnerEntityName"),
  partnerEntityRegion: document.querySelector("#partnerEntityRegion"),
  partnerEntityList: document.querySelector("#partnerEntityList"),
  partnerProfile: document.querySelector("#partnerProfile"),
  partnerQuestionForm: document.querySelector("#partnerQuestionForm"),
  partnerQuestionInput: document.querySelector("#partnerQuestionInput"),
  partnerQuestionAnswer: document.querySelector("#partnerQuestionAnswer"),
  partnerReviewForm: document.querySelector("#partnerReviewForm"),
  partnerReviewRecommendation: document.querySelector("#partnerReviewRecommendation"),
  partnerReviewValidUntil: document.querySelector("#partnerReviewValidUntil"),
  partnerReviewReason: document.querySelector("#partnerReviewReason"),
  partnerReviewConditions: document.querySelector("#partnerReviewConditions"),
  partnerReviewStatus: document.querySelector("#partnerReviewStatus"),
  organizationWorkspaceSelect: document.querySelector("#organizationWorkspaceSelect"),
  organizationMemorySearch: document.querySelector("#organizationMemorySearch"),
  organizationMemoryTypeFilter: document.querySelector("#organizationMemoryTypeFilter"),
  organizationSummary: document.querySelector("#organizationSummary"),
  organizationReportDelivery: document.querySelector("#organizationReportDelivery"),
  organizationMemoryMeta: document.querySelector("#organizationMemoryMeta"),
  organizationMemoryList: document.querySelector("#organizationMemoryList"),
  organizationMemoryForm: document.querySelector("#organizationMemoryForm"),
  organizationMemoryType: document.querySelector("#organizationMemoryType"),
  organizationMemoryTitleInput: document.querySelector("#organizationMemoryTitleInput"),
  organizationMemoryContent: document.querySelector("#organizationMemoryContent"),
  organizationMemoryNoticeId: document.querySelector("#organizationMemoryNoticeId"),
  organizationMemoryEvidenceUrl: document.querySelector("#organizationMemoryEvidenceUrl"),
  bidMemoryTargetNoticeId: document.querySelector("#bidMemoryTargetNoticeId"),
  bidMemoryDashboard: document.querySelector("#bidMemoryDashboard"),
  loadBidMemoryButton: document.querySelector("#loadBidMemoryButton"),
  bidMemoryArchiveDialog: document.querySelector("#bidMemoryArchiveDialog"),
  bidMemoryArchiveForm: document.querySelector("#bidMemoryArchiveForm"),
  bidMemoryArchiveProject: document.querySelector("#bidMemoryArchiveProject"),
  bidMemoryArchiveTags: document.querySelector("#bidMemoryArchiveTags"),
  bidMemoryArchiveMaterialTitle: document.querySelector("#bidMemoryArchiveMaterialTitle"),
  bidMemoryArchiveMaterialContent: document.querySelector("#bidMemoryArchiveMaterialContent"),
  bidMemoryArchiveValidUntil: document.querySelector("#bidMemoryArchiveValidUntil"),
  bidMemoryArchivePermission: document.querySelector("#bidMemoryArchivePermission"),
  bidMemoryArchiveSensitivity: document.querySelector("#bidMemoryArchiveSensitivity"),
  bidMemoryArchiveStatus: document.querySelector("#bidMemoryArchiveStatus"),
  submitBidMemoryArchiveButton: document.querySelector("#submitBidMemoryArchiveButton"),
  closeBidMemoryArchiveButton: document.querySelector("#closeBidMemoryArchiveButton"),
  cancelBidMemoryArchiveButton: document.querySelector("#cancelBidMemoryArchiveButton"),
  radarDataAsOf: document.querySelector("#radarDataAsOf"),
  radarWindowSelect: document.querySelector("#radarWindowSelect"),
  radarCategorySelect: document.querySelector("#radarCategorySelect"),
  radarMotionButton: document.querySelector("#radarMotionButton"),
  radarPresentationButton: document.querySelector("#radarPresentationButton"),
  refreshRadarButton: document.querySelector("#refreshRadarButton"),
  radarMetrics: document.querySelector("#radarMetrics"),
  radarMapTitle: document.querySelector("#radarMapTitle"),
  radarMapMeta: document.querySelector("#radarMapMeta"),
  radarMap: document.querySelector("#radarMap"),
  radarInspector: document.querySelector("#radarInspector"),
  radarCategoryHeat: document.querySelector("#radarCategoryHeat"),
  radarLatest: document.querySelector("#radarLatest"),
  radarSourceMeta: document.querySelector("#radarSourceMeta"),
  radarSourceSummary: document.querySelector("#radarSourceSummary"),
  radarSourceMap: document.querySelector("#radarSourceMap"),
  radarMethodNote: document.querySelector("#radarMethodNote"),
  battleLiveState: document.querySelector("#battleLiveState"),
  battleDataAsOf: document.querySelector("#battleDataAsOf"),
  battleWindowSelect: document.querySelector("#battleWindowSelect"),
  battleCategorySelect: document.querySelector("#battleCategorySelect"),
  battleModeSelect: document.querySelector("#battleModeSelect"),
  battleMotionButton: document.querySelector("#battleMotionButton"),
  battlePresentationButton: document.querySelector("#battlePresentationButton"),
  battleSyncButton: document.querySelector("#battleSyncButton"),
  battleExternalButton: document.querySelector("#battleExternalButton"),
  battleReplayButton: document.querySelector("#battleReplayButton"),
  battleMetrics: document.querySelector("#battleMetrics"),
  battleTimelineLabel: document.querySelector("#battleTimelineLabel"),
  battleTimelineRange: document.querySelector("#battleTimelineRange"),
  battleTimelineTicks: document.querySelector("#battleTimelineTicks"),
  battleTimelineCompare: document.querySelector("#battleTimelineCompare"),
  battlePlayButton: document.querySelector("#battlePlayButton"),
  battleMap: document.querySelector("#battleMap"),
  battleMapMeta: document.querySelector("#battleMapMeta"),
  battleImpactList: document.querySelector("#battleImpactList"),
  battleEventList: document.querySelector("#battleEventList"),
  battleListMeta: document.querySelector("#battleListMeta"),
  battleMethodNote: document.querySelector("#battleMethodNote"),
  battleEvidenceDialog: document.querySelector("#battleEvidenceDialog"),
  battleEvidenceTitle: document.querySelector("#battleEvidenceTitle"),
  battleEvidenceMeta: document.querySelector("#battleEvidenceMeta"),
  battleEvidenceContent: document.querySelector("#battleEvidenceContent"),
  battleEvidenceCloseButton: document.querySelector("#battleEvidenceCloseButton"),
  trainingHeaderState: document.querySelector("#trainingHeaderState"),
  trainingHeaderMeta: document.querySelector("#trainingHeaderMeta"),
  trainingSeedButton: document.querySelector("#trainingSeedButton"),
  trainingScenarioList: document.querySelector("#trainingScenarioList"),
  trainingSetupForm: document.querySelector("#trainingSetupForm"),
  trainingScenarioId: document.querySelector("#trainingScenarioId"),
  trainingMode: document.querySelector("#trainingMode"),
  trainingRole: document.querySelector("#trainingRole"),
  trainingDifficulty: document.querySelector("#trainingDifficulty"),
  trainingParticipant: document.querySelector("#trainingParticipant"),
  trainingCreateButton: document.querySelector("#trainingCreateButton"),
  trainingPhaseRail: document.querySelector("#trainingPhaseRail"),
  trainingStage: document.querySelector("#trainingStage"),
  trainingReport: document.querySelector("#trainingReport"),
  trainingEvidenceList: document.querySelector("#trainingEvidenceList"),
  trainingTeamReadiness: document.querySelector("#trainingTeamReadiness"),
  trainingHistoryButton: document.querySelector("#trainingHistoryButton"),
  trainingHistory: document.querySelector("#trainingHistory"),
  challengeForm: document.querySelector("#challengeForm"),
  challengeCategory: document.querySelector("#challengeCategory"),
  challengeRegion: document.querySelector("#challengeRegion"),
  challengeTimeWindow: document.querySelector("#challengeTimeWindow"),
  challengeKeyword: document.querySelector("#challengeKeyword"),
  challengeRunButton: document.querySelector("#challengeRunButton"),
  challengeSupplementButton: document.querySelector("#challengeSupplementButton"),
  challengeCancelButton: document.querySelector("#challengeCancelButton"),
  challengeCopyLinkButton: document.querySelector("#challengeCopyLinkButton"),
  challengeRefreshHistoryButton: document.querySelector("#challengeRefreshHistoryButton"),
  challengeNetworkDot: document.querySelector("#challengeNetworkDot"),
  challengeNetworkState: document.querySelector("#challengeNetworkState"),
  challengeStage: document.querySelector("#challengeStage"),
  challengeSourceList: document.querySelector("#challengeSourceList"),
  challengeHistory: document.querySelector("#challengeHistory"),
  demoConsoleOverall: document.querySelector("#demoConsoleOverall"),
  demoRefreshButton: document.querySelector("#demoRefreshButton"),
  demoPrepareButton: document.querySelector("#demoPrepareButton"),
  demoRunThreeButton: document.querySelector("#demoRunThreeButton"),
  demoConsoleMetrics: document.querySelector("#demoConsoleMetrics"),
  demoEnvironmentTime: document.querySelector("#demoEnvironmentTime"),
  demoEnvironmentChecks: document.querySelector("#demoEnvironmentChecks"),
  demoLayoutAuditButton: document.querySelector("#demoLayoutAuditButton"),
  demoLayoutAudits: document.querySelector("#demoLayoutAudits"),
  visualAuditButton: document.querySelector("#visualAuditButton"),
  visualAuditResults: document.querySelector("#visualAuditResults"),
  demoCaseGrid: document.querySelector("#demoCaseGrid"),
  demoStage: document.querySelector("#demoStage"),
  demoRehearsalLog: document.querySelector("#demoRehearsalLog"),
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

function semanticStateMeta(status) {
  const value = String(status || "unknown").toLowerCase();
  const verified = new Set(["verified", "ready", "healthy", "pass", "completed", "configured", "fresh", "normal", "stable", "finished", "sent", "active", "accepted", "supportive"]);
  const review = new Set(["pending", "warning", "warn", "attention", "review", "degraded", "incomplete", "needs_configuration", "partial", "queued", "login_required", "login_expired", "request_more", "stale"]);
  const gap = new Set(["failed", "unhealthy", "risk", "insufficient", "blocked", "expired", "conflict", "rejected", "unavailable", "resistant"]);
  const human = new Set(["human", "confirmed", "resolved", "manually_confirmed", "overridden", "escalated", "archived"]);
  if (verified.has(value)) return { tone: "verified", symbol: "✓" };
  if (review.has(value)) return { tone: "review", symbol: "!" };
  if (gap.has(value)) return { tone: "gap", symbol: "×" };
  if (human.has(value)) return { tone: "human", symbol: "人" };
  return { tone: "system", symbol: "i" };
}

function semanticStateTag(status, label, extraClass = "") {
  const stateMeta = semanticStateMeta(status);
  return `<span class="tt-state tt-state-${stateMeta.tone}${extraClass ? ` ${extraClass}` : ""}" data-semantic-state="${stateMeta.tone}"><b aria-hidden="true">${stateMeta.symbol}</b><span>${escapeHtml(label || statusLabel(status))}</span></span>`;
}

function renderSemanticLegend() {
  return `<div class="tt-status-legend" role="group" aria-label="统一状态语言">
    ${semanticStateTag("verified", "有据满足")}
    ${semanticStateTag("review", "待确认")}
    ${semanticStateTag("gap", "缺口或失效")}
    ${semanticStateTag("system", "系统信息")}
    ${semanticStateTag("human", "人工裁决")}
  </div>`;
}

function renderVisualIdentityStrip(item, twin = {}) {
  const snapshot = twin.snapshot || {};
  return `<div class="tt-identity-strip" aria-label="当前项目统一标识">
    <span><b>项目</b>${escapeHtml(item.project_no || item.notice_id || "待确认")}</span>
    <span><b>公告</b>${escapeHtml(item.notice_id || "待确认")}</span>
    <span><b>版本</b>${escapeHtml(String(snapshot.state_hash || item.revision_id || "当前基线").slice(0, 16))}</span>
  </div>`;
}

function digitalTwinConclusion(scores, actions) {
  const scoreItems = [scores.opportunity_value, scores.enterprise_fit, scores.bid_readiness].filter(Boolean);
  const attention = scoreItems.filter((item) => ["attention", "risk", "insufficient"].includes(item.status)).length;
  if (attention) return `${attention} 项核心判断需要复核，优先处理 ${actions[0]?.title || "证据缺口"}`;
  return `项目档案已就绪，${actions.length} 项行动可以继续推进`;
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

function loadBooleanPreference(key, fallback = false) {
  try {
    const saved = window.localStorage.getItem(key);
    return saved === null ? fallback : saved === "true";
  } catch {
    return fallback;
  }
}

function applyMotionPreference(disabled, persist = true) {
  state.motionDisabled = Boolean(disabled);
  state.radarMotionDisabled = state.motionDisabled;
  document.body.classList.toggle("motion-disabled", state.motionDisabled);
  document.body.classList.toggle("radar-motion-off", state.motionDisabled);
  document.body.classList.toggle("battle-motion-off", state.motionDisabled);
  for (const button of [el.motionToggleButton, el.radarMotionButton, el.battleMotionButton]) {
    if (!button) continue;
    button.setAttribute("aria-pressed", String(state.motionDisabled));
    const label = button.querySelector("span");
    if (label) label.textContent = state.motionDisabled ? "动效关" : "动效开";
    else button.textContent = state.motionDisabled ? "动效关" : "动效开";
    button.title = state.motionDisabled ? "开启动效" : "关闭业务动效";
    button.setAttribute("aria-label", button.title);
  }
  if (persist) {
    try { window.localStorage.setItem("tendertrace.motionDisabled", String(state.motionDisabled)); } catch {}
  }
}

function applyPresentationMode(active, persist = true) {
  state.presentationMode = Boolean(active);
  document.body.classList.toggle("presentation-mode", state.presentationMode);
  document.body.classList.toggle("radar-presentation", state.presentationMode);
  document.body.classList.toggle("battle-presentation", state.presentationMode);
  for (const button of [el.presentationModeButton, el.radarPresentationButton, el.battlePresentationButton]) {
    if (!button) continue;
    button.setAttribute("aria-pressed", String(state.presentationMode));
    const label = button.querySelector("span");
    if (label) label.textContent = state.presentationMode ? "退出大屏" : "大屏";
    else button.textContent = state.presentationMode ? "退出大屏" : "大屏";
    button.title = state.presentationMode ? "退出大屏模式" : "进入大屏模式";
    button.setAttribute("aria-label", button.title);
  }
  if (persist) {
    try { window.localStorage.setItem("tendertrace.presentationMode", String(state.presentationMode)); } catch {}
  }
}

function loadDisplayPreferences() {
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false;
  applyMotionPreference(loadBooleanPreference("tendertrace.motionDisabled", reducedMotion), false);
  applyPresentationMode(loadBooleanPreference("tendertrace.presentationMode", false), false);
}

function announceBusinessEvent(target, eventType = "arrival") {
  if (!target || state.motionDisabled || window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;
  const className = `tt-event-${eventType}`;
  target.classList.remove(className);
  window.requestAnimationFrame(() => {
    target.classList.add(className);
    const clear = () => target.classList.remove(className);
    target.addEventListener("animationend", clear, { once: true });
    window.setTimeout(clear, 620);
  });
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
  document.querySelectorAll(".nav-more").forEach((details) => { details.open = false; });
  if (viewId === "finalsHomeView") refreshFinalsHome().catch(toastError("总决赛首页加载失败"));
  if (viewId === "historyView") refreshRuns().catch(toastError("历史运行加载失败"));
  if (viewId === "challengeView") {
    refreshLiveChallengeHistory({ loadLatest: !state.liveChallenge }).catch(toastError("挑战记录加载失败"));
  }
  if (viewId === "demoConsoleView") {
    refreshDemoReliability().catch(toastError("演示可靠性状态加载失败"));
    refreshVisualSystem().catch(toastError("视觉验收状态加载失败"));
  }
  if (viewId === "radarView") refreshOpportunityRadar().catch(toastError("机会雷达加载失败"));
  if (viewId === "battleMapView") {
    refreshBattleMap().catch(toastError("实时战情图加载失败"));
    ensureBattleMapStream();
  }
  if (viewId === "trainingView") {
    refreshTrainingCenter().catch(toastError("训练中心加载失败"));
  }
  if (viewId === "opportunityView") refreshOpportunities().catch(toastError("机会情报加载失败"));
  if (viewId === "subscriptionsView") refreshSubscriptions().catch(toastError("订阅加载失败"));
  if (viewId === "sourcesView") refreshSourcesPanel().catch(toastError("数据源加载失败"));
  if (viewId === "evaluationView") refreshEvaluation().catch(toastError("评测加载失败"));
  if (viewId === "memoryView") {
    trackActivity("weekly_report_view", { target: "memoryView", label: "用户记忆" });
    refreshMemoryWeekly().catch(toastError("用户记忆加载失败"));
  }
  if (viewId === "partnerView") {
    refreshPartnerWorkspaceOptions()
      .then(() => refreshPartnerEntities())
      .catch(toastError("合作方尽调加载失败"));
  }
  if (viewId === "organizationView") {
    refreshOrganizationWorkspaces().catch(toastError("组织协作加载失败"));
  }
  if (viewId === "settingsView") refreshSettings().catch(toastError("设置加载失败"));
}

function settledValue(result) {
  return result?.status === "fulfilled" ? result.value : null;
}

async function refreshFinalsHome() {
  if (!document.getElementById("finalsHomeView")) return null;
  if (el.finalsHomeRefreshButton) el.finalsHomeRefreshButton.disabled = true;
  try {
    const results = await Promise.allSettled([
      api("/api/opportunity-radar?scope=domestic&window_days=365"),
      api("/api/demo-reliability?compact=true"),
      api("/api/integrations/feishu/overview"),
      api("/api/training/team-readiness"),
    ]);
    state.finalsHome = {
      radar: settledValue(results[0]),
      demo: settledValue(results[1]),
      feishu: settledValue(results[2]),
      training: settledValue(results[3]),
      partialFailureCount: results.filter((item) => item.status === "rejected").length,
    };
    renderFinalsHome(state.finalsHome);
    return state.finalsHome;
  } finally {
    if (el.finalsHomeRefreshButton) el.finalsHomeRefreshButton.disabled = false;
  }
}

function renderFinalsHome(payload) {
  const radar = payload?.radar || {};
  const summary = radar.summary || {};
  const demo = payload?.demo || {};
  const environment = demo.environment || {};
  const feishu = payload?.feishu || {};
  const mainCase = (demo.cases || []).find((item) => item.role === "main") || demo.cases?.[0] || {};
  const display = mainCase.display || {};
  const twin = mainCase.snapshot?.result?.digital_twin || {};
  const project = twin.project || {};
  const scores = twin.scores || {};
  const sourceCounts = environment.source_health_counts || {};
  const localReady = environment.critical_ready === true;
  const feishuReady = feishu.status === "ready" && feishu.features?.conversation_commands?.ready;
  const replayReady = Boolean(mainCase.replay_verified && mainCase.snapshot_verified);
  const metric = (node, value, label) => {
    if (node) node.innerHTML = `${escapeHtml(value ?? "-")}<small>${escapeHtml(label)}</small>`;
  };
  metric(el.finalsHomeOpportunityCount, summary.opportunity_count, "有效机会");
  metric(el.finalsHomeRecentCount, summary.recent_7d_count, "近 7 日新增");
  metric(el.finalsHomeRegionCount, summary.location_count, "覆盖地区");
  metric(el.finalsHomeSourceCount, summary.source_count, "本地有结果来源");
  if (el.finalsHomeDataAsOf) el.finalsHomeDataAsOf.textContent = radar.data_as_of ? `数据至 ${compactDateTimeText(radar.data_as_of)}` : "数据时间不可用";
  if (el.finalsHomeLocalState) el.finalsHomeLocalState.textContent = localReady ? "本地服务与证据库就绪" : "部分环境待检查";
  if (el.finalsHomeFeishuState) el.finalsHomeFeishuState.textContent = feishuReady ? "长连接与协作资源就绪" : "协作链路需检查";
  if (el.finalsHomeReplayState) el.finalsHomeReplayState.textContent = replayReady ? "主案例快照与回放已核验" : "主案例回放待核验";
  if (el.finalsHomeRadarMeta) {
    el.finalsHomeRadarMeta.textContent = `本地索引优先 · 健康 ${sourceCounts.healthy ?? 0} · 降级 ${sourceCounts.degraded ?? 0} · 异常 ${sourceCounts.unhealthy ?? 0}；0 条结果不等于来源故障。`;
  }
  if (el.finalsHomeCaseState) {
    el.finalsHomeCaseState.textContent = mainCase.verification_status === "verified" ? "已核验真实案例" : "待核验";
    el.finalsHomeCaseState.className = `finals-case-state ${mainCase.verification_status === "verified" ? "is-ready" : "is-review"}`;
  }
  if (el.finalsHomeCaseTitle) el.finalsHomeCaseTitle.textContent = project.title || display.title || "暂无主案例";
  if (el.finalsHomeCaseMeta) {
    el.finalsHomeCaseMeta.textContent = project.notice_id
      ? `${project.region || "地区待确认"} · ${project.purchaser || "采购方待确认"} · 截止 ${project.bid_deadline || "待确认"}`
      : "请先在演示控制台准备已核验主案例。";
  }
  if (el.finalsHomeScoreGrid) {
    const scoreItems = [
      ["机会价值", scores.opportunity_value],
      ["企业匹配度", scores.enterprise_fit],
      ["投标准备度", scores.bid_readiness],
    ];
    el.finalsHomeScoreGrid.innerHTML = scoreItems.map(([label, item]) => `<article class="is-${escapeHtml(item?.status || "unknown")}"><span>${label}</span><strong>${escapeHtml(item?.score ?? "-")}</strong><small>${escapeHtml(item?.status_label || "数据待补")}</small></article>`).join("");
  }
  if (el.finalsHomeCaseEvidence) {
    el.finalsHomeCaseEvidence.innerHTML = (display.items || []).map((item) => `<span><i></i><b>${escapeHtml(item.title)}</b>${escapeHtml(item.meta)}</span>`).join("") || "<span>暂无已核验案例证据</span>";
  }
  if (el.finalsHomeActions) {
    const actions = [...(twin.next_actions || [])];
    const blockers = scores.bid_readiness?.blockers || [];
    blockers.forEach((blocker) => actions.push({ priority: "high", title: `补齐${blocker}`, reason: "当前准备度门禁未通过" }));
    if (Number(sourceCounts.degraded || 0) + Number(sourceCounts.unhealthy || 0) > 0) {
      actions.push({ priority: "normal", title: "保留来源降级说明", reason: "现场使用本地证据或已核验回放" });
    }
    el.finalsHomeActions.innerHTML = actions.slice(0, 3).map((item, index) => `<article><span>0${index + 1}</span><div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.reason || "进入对应模块完成处理")}</p></div><i class="is-${escapeHtml(item.priority || "normal")}"></i></article>`).join("") || '<p class="empty-state">当前没有阻断性行动</p>';
  }
  document.querySelectorAll("[data-finals-primary-case]").forEach((button) => {
    button.dataset.noticeId = project.notice_id || mainCase.source_id || "";
    button.disabled = !button.dataset.noticeId;
  });
}

function routeFinalsIntent(event) {
  event?.preventDefault();
  const query = el.finalsHomeIntentInput?.value.trim() || "";
  if (!query) {
    el.finalsHomeIntentInput?.focus();
    return;
  }
  if (/训练|演练|答辩|追问/.test(query)) {
    showView("trainingView");
    return;
  }
  if (/企业|合作方|供应商|风险|尽调/.test(query)) {
    showView("partnerView");
    return;
  }
  if (/战情|态势|地图|地区|外部事件/.test(query)) {
    showView("battleMapView");
    return;
  }
  showView("workbenchView");
  if (el.queryInput) {
    el.queryInput.value = query;
    el.queryInput.dispatchEvent(new Event("input", { bubbles: true }));
    el.queryInput.focus();
  }
  refreshIntentPreview().catch(toastError("首页意图解析失败"));
}

async function openFinalsPrimaryCase(noticeId) {
  if (!noticeId) return;
  state.pendingOpportunityId = noticeId;
  showView("opportunityView");
  await refreshOpportunities();
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
  renderWorkbenchContext();
}

function renderSubscriptions(items) {
  renderSubscriptionTable(el.subscriptionPageBody, items);
  renderWorkbenchContext();
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
  const freshnessPolicy = policy.stale_monitoring_active
    ? `新鲜度 ${escapeHtml(policy.stale_hours || 0)} 小时`
    : "自动采集未开启，新鲜度 SLO 未启用";
  const incidentText = latestIncident
    ? `${sourceIncidentStatusLabel(latestIncident.status)} · ${escapeHtml((latestIncident.source_sites || []).join("、") || "来源事件")} · 截止 ${escapeHtml(compactDateTimeText(latestIncident.due_at))}`
    : "";
  el.sourceAlertSummary.className = `source-alert-summary ${issues.length ? "is-attention" : "is-healthy"}`;
  el.sourceAlertSummary.innerHTML = `
    <div>
      <span>${issues.length ? "来源 SLO 需要处理" : "来源 SLO 正常"}</span>
      <strong>${escapeHtml(payload?.source_count || 0)} 个来源 · ${escapeHtml(issues.length)} 个异常</strong>
      <small>可靠度阈值 ${escapeHtml(percent(policy.minimum_reliability || 0))} · ${freshnessPolicy}${incidentSlaHours ? ` · 处置 SLA ${escapeHtml(incidentSlaHours)} 小时` : ""}</small>
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
      const failureSummary = sourceFailureSummary(health);
      const recovery = item.site === "qianlima" && access.badge === "warn"
        ? `
          <div class="source-recovery">
            <strong>登录恢复</strong>
            <span>在本机终端重新保存登录态后，可直接校验当前会员会话。</span>
            <div>
              <code>python -m tendertrace login-qianlima</code>
              <button class="ghost-button" type="button" data-verify-qianlima>验证登录态</button>
            </div>
          </div>
        `
        : "";
      return `
        <div class="source-row source-health-card" data-visual-component="source-health">
          <div class="source-row-head">
            <strong>${site} · ${engine}</strong>
            <span>
              ${semanticStateTag(health.health_status, statusLabel(health.health_status), `badge badge-${healthStatus}`)}
              ${semanticStateTag(access.badge, access.label, `badge badge-${escapeHtml(access.badge)}`)}
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
          ${failureSummary}
          ${recovery}
        </div>
      `;
    })
    .join("");
  target.querySelectorAll("[data-verify-qianlima]").forEach((button) => {
    button.addEventListener("click", () => verifyQianlimaLogin(button));
  });
}

function sourceFailureSummary(health) {
  if (!health?.last_error) return "";
  const lastFailure = String(health.last_failure_at || "");
  const lastSuccess = String(health.last_success_at || "");
  const recovered = Boolean(lastSuccess && (!lastFailure || lastSuccess >= lastFailure));
  const label = recovered ? "已恢复异常" : "当前异常";
  const statusClass = recovered ? "source-recovered-line" : "source-error-line";
  const timestamp = lastFailure ? ` · ${escapeHtml(compactDateTimeText(lastFailure))}` : "";
  return `<span class="${statusClass}">${label}：${escapeHtml(health.last_error)}${timestamp}</span>`;
}

async function verifyQianlimaLogin(button) {
  button.disabled = true;
  try {
    const result = await api("/api/sources/qianlima/verify", { method: "POST" });
    const probe = result.live_probe || {};
    showToast(probe.detail || `千里马登录态：${statusLabel(probe.status)}`);
    await refreshSourcesPanel();
  } finally {
    button.disabled = false;
  }
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
        <button class="ghost-button" type="button" data-popover-view="evaluationView">评测与价值</button>
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
      summaryTile(report.score_label || "总分", percent(report.overall_score)),
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
    ["严格 Recall@10", strictMetricValue(report, "strict_recall_at_10")],
    ["严格 Precision@10", strictMetricValue(report, "strict_precision_at_10")],
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
  renderBusinessMeasurements(report.business || {});
  if (el.evaluationCases) {
    const cases = report.gold?.cases || [];
    el.evaluationCases.className = cases.length ? "case-list" : "case-list empty-state";
    el.evaluationCases.innerHTML = cases.length
      ? cases
          .map(
            (item) => `
              <div class="case-row">
                <div class="case-row-heading">
                  <strong>${escapeHtml(item.id || "-")} · ${escapeHtml(statusLabel(item.status))}</strong>
                  <button class="ghost-button compact-button" type="button" data-annotate-gold-case="${escapeHtml(item.id || "")}">人工标注</button>
                </div>
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

function renderBusinessMeasurements(summary) {
  const measured = Number(summary.eligible_sample_count || 0) > 0;
  const metrics = summary.metrics || {};
  const status = summary.status || "not_measured";
  if (el.businessMeasurementStatus) {
    el.businessMeasurementStatus.className = `business-value-status status-${escapeHtml(status)}`;
    el.businessMeasurementStatus.textContent = summary.status_label || "暂无完整配对实验";
  }
  if (el.businessMeasurementMetrics) {
    el.businessMeasurementMetrics.className = "business-value-metrics";
    el.businessMeasurementMetrics.innerHTML = [
      businessValueTile("有效配对样本", summary.eligible_sample_count ?? 0, `全部记录 ${summary.record_count || 0} · 门槛 ${summary.minimum_sample || 5}`),
      businessValueTile("真实参与人", summary.participant_count ?? 0, (summary.participants || []).join("、") || "待记录"),
      businessValueTile("文件与类型", summary.file_count ?? 0, (summary.document_types || []).join("、") || "待记录"),
      businessValueTile("总耗时中位数", measured ? `${metrics.total_time?.baseline_median ?? 0} → ${metrics.total_time?.assisted_median ?? 0} 分` : "待实测", measured ? `范围 ${businessRange(metrics.total_time?.delta_range, "分")}` : "不估算"),
      businessValueTile("样本内总耗时降低", measured ? businessValuePercent(summary.time_saving_rate) : "待实测", measured ? `合计节省 ${summary.saved_minutes ?? 0} 分钟` : "无完整证据不计算"),
      businessValueTile("质量失败 / 异常", `${summary.quality_failed_count || 0} / ${summary.outlier_count || 0}`, "始终显示，不从原始记录移除"),
    ].join("");
  }
  if (el.businessMeasurementProtocol) {
    const protocol = summary.protocol || {};
    el.businessMeasurementProtocol.innerHTML = [
      ["样本", protocol.recommended_sample_range || "5-10份公开文件"],
      ["配对", protocol.pairing || "同一文件人工与系统辅助各做一次"],
      ["顺序", protocol.sequence || "采用交叉顺序"],
      ["时间", protocol.time_fields || "等待、有效操作与总耗时分开"],
      ["质量", protocol.quality_fields || "由人工金标核验"],
    ].map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  }
  if (el.businessDirectionCoverage) {
    const coverage = Array.isArray(summary.direction_coverage) ? summary.direction_coverage : [];
    el.businessDirectionCoverage.innerHTML = coverage.map((item) => `
      <article class="business-direction-item status-${escapeHtml(item.status || "pending")}">
        <span>${escapeHtml(item.direction || "-")}</span>
        <div><strong>${escapeHtml(item.name || "提升方向")}</strong><small>${escapeHtml(item.task_type_label || "待定义")} · ${escapeHtml(item.sample_count || 0)} 个有效样本</small></div>
        <em>${item.status === "measured" ? "已实测" : item.status === "active" ? "实验室" : "待实测"}</em>
      </article>
    `).join("") || '<p class="business-value-empty">暂无价值链映射</p>';
  }
  if (el.businessMetricDetails) {
    const metricDefinitions = [
      ["total_time", "总耗时", "从接到任务到完成的完整时间"],
      ["active_time", "人工有效时间", "人员实际阅读、判断和操作时间"],
      ["machine_wait", "机器等待时间", "系统处理与等待时间，单独展示"],
      ["omissions", "关键要求遗漏", "对照人工金标缺失的强制要求"],
      ["false_satisfied", "错误满足判断", "把未满足要求误判为满足"],
      ["rework", "返工次数", "完成后因遗漏或错误再次修改"],
    ];
    el.businessMetricDetails.className = measured ? "business-metric-details" : "business-metric-details empty-state";
    el.businessMetricDetails.innerHTML = measured
      ? metricDefinitions.map(([key, label, description]) => businessMetricCard(label, description, metrics[key] || {})).join("")
      : escapeHtml(summary.status_label || "暂无完整配对实验");
  }
  if (el.businessExperimentList) {
    const experiments = Array.isArray(summary.experiments) ? summary.experiments : [];
    el.businessExperimentList.className = experiments.length ? "business-experiment-list" : "business-experiment-list empty-state";
    el.businessExperimentList.innerHTML = experiments.length ? experiments.map((item) => `
      <article>
        <header><strong>${escapeHtml(item.experiment_id || "未命名实验")} · v${escapeHtml(item.experiment_version || 1)}</strong><span>${escapeHtml(item.eligible_sample_count || 0)}/${escapeHtml(item.sample_count || 0)} 有效</span></header>
        <p>${escapeHtml(item.participant_count || 0)} 人 · ${escapeHtml((item.document_types || []).join("、") || "文件类型待填")}</p>
        <small>${escapeHtml((item.sequence_orders || []).join(" / ") || "交叉顺序待填")}</small>
        <small>${escapeHtml((item.conditions || []).join("；") || "实验条件待填")}</small>
      </article>
    `).join("") : "暂无实验批次";
  }
  if (el.businessFormulaList) {
    const formulas = Array.isArray(summary.formulas) ? summary.formulas : [];
    el.businessFormulaList.className = formulas.length ? "business-formula-list" : "business-formula-list empty-state";
    el.businessFormulaList.innerHTML = formulas.map((item) => `
      <article>
        <div><strong>${escapeHtml(item.label || "指标")}</strong><span>${item.result === null || item.result === undefined ? "待实测" : businessValuePercent(item.result)}</span></div>
        <code>${escapeHtml(item.formula || "-")}</code>
        <small>分子 ${escapeHtml(item.numerator ?? 0)} ${escapeHtml(item.unit || "")} / 分母 ${escapeHtml(item.denominator ?? 0)} ${escapeHtml(item.unit || "")} / n=${escapeHtml(item.sample_count || 0)}</small>
      </article>
    `).join("") || "暂无可复算指标";
  }
  if (el.businessMeasurementList) {
    const items = Array.isArray(summary.items) ? summary.items : [];
    el.businessMeasurementList.className = items.length ? "business-sample-table" : "business-sample-table empty-state";
    el.businessMeasurementList.innerHTML = items.length
      ? `<div class="business-sample-head"><span>样本 / 条件</span><span>配对时间</span><span>金标质量</span><span>证据</span></div>${items.map((item) => `
          <article class="business-sample-row quality-${escapeHtml(item.quality_status || "not_reviewed")} ${item.is_outlier ? "is-outlier" : ""}">
            <div><strong>${escapeHtml(item.sample_ref || "未命名样本")}</strong><span>${escapeHtml(item.task_type_label || item.task_type || "任务")} · ${escapeHtml(item.participant || "参与人待填")}</span><small>${escapeHtml(item.document_type || "文件类型待填")} · ${escapeHtml(item.sequence_order_label || "顺序待填")}</small></div>
            <div><strong>${escapeHtml(item.baseline_minutes || 0)} → ${escapeHtml(item.assisted_minutes || 0)} 分</strong><span>人工有效 ${escapeHtml(item.baseline_active_minutes || 0)} → ${escapeHtml(item.assisted_active_minutes || 0)} 分</span><small>变化 ${escapeHtml(item.time_saved_minutes ?? 0)} 分 · 等待 ${escapeHtml(item.assisted_machine_wait_seconds || 0)} 秒</small></div>
            <div><strong>${escapeHtml(item.quality_status_label || "待复核")}${item.is_outlier ? " · 异常值" : ""}</strong><span>遗漏 ${escapeHtml(item.baseline_omissions || 0)} → ${escapeHtml(item.assisted_omissions || 0)} · 错判 ${escapeHtml(item.baseline_false_satisfied || 0)} → ${escapeHtml(item.assisted_false_satisfied || 0)}</span><small>${escapeHtml(item.outlier_reason || item.note || "无补充说明")}</small></div>
            <div class="business-sample-links">${businessEvidenceLink(item.source_url, "公开文件")}${businessEvidenceLink(item.raw_record_url, "原始记录")}${businessEvidenceLink(item.gold_standard_url, "人工金标")}<small>${escapeHtml(item.reviewer || "复核人待填")} · ${item.evidence_complete ? "证据完整" : "证据待补"}</small></div>
          </article>
        `).join("")}`
      : escapeHtml(summary.note || "暂无记录");
  }
  if (el.businessSampleCount) el.businessSampleCount.textContent = `${summary.record_count || 0} 条 · 失败 ${summary.quality_failed_count || 0} · 异常 ${summary.outlier_count || 0}`;
}

function businessValueTile(label, value, detail) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
}

function businessValuePercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "待实测";
  return `${number >= 0 ? "" : "-"}${Math.abs(number * 100).toFixed(1)}%`;
}

function businessRange(range, unit) {
  if (!range || range.min === undefined || range.max === undefined) return "待实测";
  return `${range.min} 至 ${range.max} ${unit}`;
}

function businessMetricCard(label, description, metric) {
  const hasData = Number(metric.sample_count || 0) > 0;
  return `<article>
    <header><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(description)}</small></div><span>${hasData ? businessValuePercent(metric.reduction_rate) : "待实测"}</span></header>
    <div class="business-metric-pair"><span>人工中位数 <b>${escapeHtml(metric.baseline_median ?? "-")} ${escapeHtml(metric.unit || "")}</b></span><i>→</i><span>辅助中位数 <b>${escapeHtml(metric.assisted_median ?? "-")} ${escapeHtml(metric.unit || "")}</b></span></div>
    <footer>单样本变化范围：${escapeHtml(businessRange(metric.delta_range, metric.unit || ""))} · n=${escapeHtml(metric.sample_count || 0)}</footer>
  </article>`;
}

function businessEvidenceLink(url, label) {
  const value = String(url || "").trim();
  return value ? `<a href="${escapeHtml(value)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>` : `<span>${escapeHtml(label)}待补</span>`;
}

async function saveBusinessMeasurement(form) {
  const values = new FormData(form);
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const result = await api("/api/evaluations/business-measurements", {
      method: "POST",
      body: JSON.stringify({
        experiment_id: values.get("experiment_id") || "tendertrace-value-lab-v1",
        experiment_version: Number(values.get("experiment_version") || 1),
        task_type: values.get("task_type") || "",
        sample_ref: values.get("sample_ref") || "",
        participant: values.get("participant") || "",
        document_type: values.get("document_type") || "",
        file_count: Number(values.get("file_count") || 1),
        sequence_order: values.get("sequence_order") || "manual_first",
        conditions: values.get("conditions") || "",
        source_url: values.get("source_url") || "",
        baseline_minutes: Number(values.get("baseline_minutes") || 0),
        assisted_minutes: Number(values.get("assisted_minutes") || 0),
        baseline_active_minutes: values.get("baseline_active_minutes") === "" ? Number(values.get("baseline_minutes") || 0) : Number(values.get("baseline_active_minutes") || 0),
        assisted_active_minutes: values.get("assisted_active_minutes") === "" ? Number(values.get("assisted_minutes") || 0) : Number(values.get("assisted_active_minutes") || 0),
        baseline_machine_wait_seconds: Number(values.get("baseline_machine_wait_seconds") || 0),
        assisted_machine_wait_seconds: Number(values.get("assisted_machine_wait_seconds") || 0),
        baseline_omissions: Number(values.get("baseline_omissions") || 0),
        assisted_omissions: Number(values.get("assisted_omissions") || 0),
        baseline_false_satisfied: Number(values.get("baseline_false_satisfied") || 0),
        assisted_false_satisfied: Number(values.get("assisted_false_satisfied") || 0),
        baseline_rework_count: Number(values.get("baseline_rework_count") || 0),
        assisted_rework_count: Number(values.get("assisted_rework_count") || 0),
        quality_status: values.get("quality_status") || "not_reviewed",
        reviewer: values.get("reviewer") || "",
        recorded_by: values.get("recorded_by") || "",
        raw_record_url: values.get("raw_record_url") || "",
        gold_standard_url: values.get("gold_standard_url") || "",
        is_outlier: values.get("is_outlier") === "on",
        outlier_reason: values.get("outlier_reason") || "",
        note: values.get("note") || "",
      }),
    });
    form.reset();
    if (form.elements.recorded_by) form.elements.recorded_by.value = "admin";
    if (form.elements.experiment_id) form.elements.experiment_id.value = "tendertrace-value-lab-v1";
    if (form.elements.experiment_version) form.elements.experiment_version.value = "1";
    if (form.elements.file_count) form.elements.file_count.value = "1";
    if (state.evaluation) {
      state.evaluation.business = result.summary || {};
      renderBusinessMeasurements(state.evaluation.business);
    }
    showToast("实测任务已记录；只有质量通过样本会计入节省时间");
  } finally {
    if (submit) submit.disabled = false;
  }
}

function renderOpportunities(payload) {
  const items = payload?.items || [];
  const summary = payload?.summary || {};
  state.opportunities = items;
  state.opportunitySummaryData = summary;
  renderWorkbenchContext();
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

async function openOpportunityDetail(noticeId, digitalTwinOverride = null, restoreScrollTop = null) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || !el.opportunityDetailDialog || !el.opportunityDetailContent) return;
  const requestSequence = ++state.opportunityDetailRequestSequence;
  el.opportunityDetailTitle.textContent = `${item.project_no || item.notice_id || "项目"} · ${item.workflow?.stage_label || "数字档案"}`;
  if (!el.opportunityDetailDialog.open) el.opportunityDetailDialog.showModal();
  let digitalTwin = digitalTwinOverride || {};
  if (!digitalTwinOverride) {
    el.opportunityDetailContent.innerHTML = '<div class="digital-twin-loading"><strong>正在同步数字项目档案</strong><span>汇总公告、证据、要求、能力、会审与协作状态…</span></div>';
    try {
      digitalTwin = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/digital-twin`);
    } catch (error) {
      digitalTwin = { error: error.message || String(error) };
    }
  }
  if (requestSequence !== state.opportunityDetailRequestSequence || !el.opportunityDetailDialog.open) return;
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
  el.opportunityDetailContent.innerHTML = `
    ${renderDigitalTwinCockpit(digitalTwin, item)}
    ${renderSemanticLegend()}
    ${renderVisualIdentityStrip(item, digitalTwin)}
    <section class="decision-sandbox-shell" data-decision-sandbox="${escapeHtml(item.notice_id)}">
      <div class="decision-sandbox-loading"><strong>正在装载投标决策沙盘</strong><span>建立只读基准与临时推演空间…</span></div>
    </section>
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
    <section class="opportunity-journey" data-opportunity-journey="${escapeHtml(item.notice_id)}" aria-label="机会推进路径">
      ${renderOpportunityJourney(item)}
    </section>
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
    <details class="source-relation-shell" data-source-relation-section>
      <summary>
        <div><span>来源可信关系</span><strong>查看同一项目的原公告、转载、更正、结果与附件</strong></div>
        <small>按需展开 · 不占用主流程</small>
      </summary>
      <div class="source-relation-board" data-source-relations="${escapeHtml(item.notice_id)}">
        <div class="source-relation-loading"><i></i><span>正在核对跨来源关系与冲突字段…</span></div>
      </div>
    </details>
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
    <section id="opportunityChangeSection" class="opportunity-detail-section opportunity-change-section">
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
      <div class="change-impact-workbench" data-change-impact="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在生成公告冲击波与行动清单</div>
      </div>
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
    <section id="opportunityRequirementsSection" class="opportunity-detail-section opportunity-requirements-section">
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
    <section id="opportunityBidWorkplanSection" class="opportunity-detail-section bid-workplan-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>智能拆标与履约作战图</h3>
          <small>确认要求后生成交付物、RACI、倒排计划、缺口泳道和报价计划；完成结果实时回流准备度。</small>
        </div>
        <span>人机协同</span>
      </div>
      <div class="bid-workplan-board" data-bid-workplan="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在加载履约作战图</div>
      </div>
    </section>
    <section id="opportunityCapabilitySection" class="opportunity-detail-section capability-matching-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>企业能力证据矩阵</h3>
          <small>AI 仅可基于已核验、可定位的企业证据提出建议；最终结论由负责人确认。</small>
        </div>
        <button class="ghost-button" type="button" data-analyze-capability-matches="${escapeHtml(item.notice_id)}">生成匹配建议</button>
      </div>
      <div class="capability-matching-ledger" data-capability-matches="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在加载能力证据矩阵</div>
      </div>
    </section>
    <section id="opportunityReviewSection" class="opportunity-detail-section review-board-section">
      <div class="opportunity-detail-section-title">
        <div>
          <h3>可质询多角色会审</h3>
          <small>合规、技术、商务、风险和证据角色基于同一版本独立审查；一致事实合并，分歧交给人员裁决。</small>
        </div>
        <div class="review-board-actions">
          <button class="ghost-button" type="button" data-run-review-agents="${escapeHtml(item.notice_id)}">启动专业对手盘</button>
          <button class="ghost-button" type="button" data-send-review-board-feishu="${escapeHtml(item.notice_id)}">同步群内会审</button>
          <button class="link-button" type="button" data-sync-review-board="${escapeHtml(item.notice_id)}">生成会审项</button>
        </div>
      </div>
      <div class="requirement-review-board" data-requirement-review-board="${escapeHtml(item.notice_id)}">
        <div class="opportunity-revision-loading">正在加载会审队列</div>
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
          <div class="outcome-memory-actions">
            <button class="ghost-button" type="button" data-archive-bid-memory="${escapeHtml(item.notice_id)}">沉淀到企业投标记忆体</button>
            <button class="primary-lite-button" type="button" data-edit-opportunity-outcome="${escapeHtml(item.notice_id)}">修订复盘</button>
          </div>
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
        <div class="opportunity-bid-memory-preview" data-opportunity-bid-memory="${escapeHtml(item.notice_id)}"><span>正在检索组织内的历史经验与可复用材料…</span></div>
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
      ${(workflow.decision && workflow.decision !== "pending") || workflow.decision_reason ? `<button class="evidence-entry-button" type="button" data-open-evidence-microscope="${escapeHtml(item.notice_id)}" data-evidence-claim-type="decision" data-evidence-claim-key="bid_decision">查看决策证据链</button>` : ""}
      ${actionState.decision_required ? detailLine("决策 SLA", decisionSlaLabel(actionState)) : ""}
      <div class="qualification-decision-actions">
        ${opportunityActionButtons(item)}
      </div>
    </section>
    <section id="opportunityCollaborationSection" class="opportunity-detail-section war-room-section">
      <div class="opportunity-detail-section-title">
        <div><h3>一键投标战情室</h3><small>把已确认的项目、要求、负责人和截止时间编排成真实团队协作空间</small></div>
        <span>Web ↔ 飞书双向协同</span>
      </div>
      <div class="war-room-plan" data-war-room-plan="${escapeHtml(item.notice_id)}">
        <span>正在进行身份、权限、资源与数据预检…</span>
      </div>
    </section>
    <section class="opportunity-detail-section collaboration-notes-section">
      <div class="opportunity-detail-section-title">
        <div><h3>协作意见</h3><small>网页与飞书群内意见进入同一条机会审计链</small></div>
      </div>
      <div class="collaboration-notes" data-collaboration-notes="${escapeHtml(item.notice_id)}"><span>正在加载协作意见…</span></div>
    </section>
    <div class="opportunity-detail-footer">
      <button class="primary-lite-button" type="button" data-send-opportunity-feishu="${escapeHtml(item.notice_id)}">${collaborationButtonLabel(workflow)}</button>
      ${item.source_url ? `<a class="ghost-button" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">查看原文</a>` : ""}
    </div>
  `;
  scheduleDigitalTwinRefresh(noticeId);
  announceBusinessEvent(el.opportunityDetailContent.querySelector("[data-visual-component=\"digital-twin\"]"), "arrival");
  if (restoreScrollTop !== null) el.opportunityDetailContent.scrollTop = restoreScrollTop;
  loadDecisionSandbox(noticeId).catch((error) => {
    const container = currentDecisionSandboxContainer(noticeId);
    if (container) container.innerHTML = `<div class="decision-sandbox-error">决策沙盘加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityRevisionHistory(noticeId).catch((error) => {
    const container = currentOpportunityRevisionContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">版本记录加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadSourceRelationGraph(noticeId).catch((error) => {
    const container = currentSourceRelationContainer(noticeId);
    if (container) container.innerHTML = `<div class="source-relation-empty">来源关系加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityChangeImpact(noticeId).catch((error) => {
    const container = currentOpportunityChangeImpactContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">公告冲击波加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityRequirements(noticeId).catch((error) => {
    const container = currentOpportunityRequirementContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">要求账本加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityBidWorkplan(noticeId).catch((error) => {
    const container = currentBidWorkplanContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">履约作战图加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityCapabilityMatches(noticeId).catch((error) => {
    const container = currentOpportunityCapabilityMatchContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-requirement-empty">能力证据矩阵加载失败：${escapeHtml(error.message || "请稍后重试")}</div>`;
  });
  loadOpportunityReviewBoard(noticeId).catch((error) => {
    const container = currentOpportunityReviewBoardContainer(noticeId);
    if (container) container.innerHTML = `<div class="opportunity-revision-empty">会审队列加载失败：${escapeHtml(error.message || error)}</div>`;
  });
  loadOpportunityWarRoomPlan(noticeId).catch((error) => {
    const container = currentOpportunityWarRoomPlanContainer(noticeId);
    if (container) container.innerHTML = `<span>战情室编排方案加载失败：${escapeHtml(error.message || error)}</span>`;
  });
  loadOpportunityCollaborationNotes(noticeId).catch((error) => {
    const container = currentOpportunityCollaborationNotesContainer(noticeId);
    if (container) container.innerHTML = `<span>协作意见加载失败：${escapeHtml(error.message || error)}</span>`;
  });
  loadOpportunityBidMemoryPreview(noticeId).catch((error) => {
    const container = currentOpportunityBidMemoryContainer(noticeId);
    if (container) container.innerHTML = `<span>企业投标记忆检索失败：${escapeHtml(error.message || error)}</span>`;
  });
}

function currentSourceRelationContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-source-relations]");
  return container?.dataset.sourceRelations === noticeId ? container : null;
}

async function loadSourceRelationGraph(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/source-relations`);
  const container = currentSourceRelationContainer(noticeId);
  if (container) container.innerHTML = renderSourceRelationGraph(payload);
  return payload;
}

function renderSourceRelationGraph(payload) {
  const summary = payload.summary || {};
  const current = payload.current || {};
  const relations = Array.isArray(payload.relations) ? payload.relations : [];
  const blocked = Array.isArray(payload.blocked_candidates) ? payload.blocked_candidates : [];
  const conflicts = Array.isArray(payload.conflicts) ? payload.conflicts : [];
  const timeline = Array.isArray(payload.confirmed_timeline) ? payload.confirmed_timeline : [];
  const confirmed = relations.filter((item) => item.status === "confirmed");
  const candidates = relations.filter((item) => item.status === "candidate");
  return `
    <div class="source-relation-overview">
      <div><span>已确认关联</span><strong>${escapeHtml(summary.confirmed_count || 0)}</strong><small>进入数字档案时间线</small></div>
      <div><span>待人工确认</span><strong>${escapeHtml(summary.candidate_count || 0)}</strong><small>规则只提出候选</small></div>
      <div class="${Number(summary.conflict_count) ? "has-attention" : ""}"><span>字段冲突</span><strong>${escapeHtml(summary.conflict_count || 0)}</strong><small>不自动选择事实</small></div>
      <div class="is-safe"><span>阻止误合并</span><strong>${escapeHtml(summary.blocked_false_merge_count || 0)}</strong><small>同名不等于同项目</small></div>
    </div>
    <div class="source-relation-graph" role="img" aria-label="跨来源可信关系图">
      <article class="source-relation-node is-current kind-${escapeHtml(current.source_kind || "official")}">
        <small>当前数字档案</small>
        <strong>${escapeHtml(current.title || "当前公告")}</strong>
        <span>${escapeHtml(current.notice_type_label || "公告")} · ${escapeHtml(current.authority || current.source_site || "来源待确认")}</span>
        ${current.source_url ? `<a href="${escapeHtml(current.source_url)}" target="_blank" rel="noreferrer">打开当前原文</a>` : ""}
      </article>
      <div class="source-relation-path"><i></i><b>${relations.length ? "匹配依据可解释" : "等待关联来源"}</b><i></i></div>
      <div class="source-relation-related">
        ${relations.length ? relations.map((item) => renderSourceRelationCandidate(payload.notice_id, item)).join("") : `
          <div class="source-relation-empty"><strong>当前没有达到阈值的关联公告</strong><span>这不是故障；系统仍保留当前原文、版本和附件，后续采集只重算相关候选。</span></div>
        `}
      </div>
    </div>
    ${conflicts.length ? `
      <section class="source-relation-conflicts">
        <header><div><strong>事实复核队列</strong><span>两个来源值不一致时，保留双方原文，不自动覆盖</span></div><b>${conflicts.length} 项</b></header>
        ${conflicts.map((item) => `
          <article>
            <strong>${escapeHtml(item.field_label || item.field)}</strong>
            <div><span>${escapeHtml(item.left?.value || "空值")}</span>${item.left?.source_url ? `<a href="${escapeHtml(item.left.source_url)}" target="_blank" rel="noreferrer">来源 A</a>` : ""}</div>
            <i>≠</i>
            <div><span>${escapeHtml(item.right?.value || "空值")}</span>${item.right?.source_url ? `<a href="${escapeHtml(item.right.source_url)}" target="_blank" rel="noreferrer">来源 B</a>` : ""}</div>
            <small>${escapeHtml(item.resolution || "等待人工复核")}</small>
          </article>
        `).join("")}
      </section>
    ` : ""}
    ${blocked.length ? `
      <details class="source-relation-blocked">
        <summary>系统已阻止 ${escapeHtml(blocked.length)} 个高相似误合并候选</summary>
        ${blocked.map((item) => `<p><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml((item.conflicts || []).map((value) => value.field_label).join("、") || "关键字段冲突")}</span><small>标题相似 ${escapeHtml(item.similarity_basis?.[0]?.confidence || 0)}%，但不是同一项目</small></p>`).join("")}
      </details>
    ` : ""}
    <section class="source-relation-timeline">
      <header><strong>确认后回流数字孪生</strong><span>${confirmed.length ? `${confirmed.length} 条关联已纳入` : "人工确认后才纳入"}</span></header>
      <div>${timeline.map((item) => `<p class="type-${escapeHtml(item.type || "other")}"><time>${escapeHtml(item.at || "时间待确认")}</time><strong>${escapeHtml(item.type_label || "公告")}</strong><span>${escapeHtml(item.source_site || "未知来源")} · ${escapeHtml(item.title || "")}</span></p>`).join("")}</div>
      <small>同一公告只出现一次；人工拆分并锁定后，后续增量匹配不会重新合并。</small>
    </section>
    <footer class="source-relation-method">本地增量规则 ${escapeHtml(payload.rule_version || "-")} · 确定规则与标题相似度分开显示 · 本次未发起网络抓取 · ${candidates.length} 条候选待确认</footer>
  `;
}

function renderSourceRelationCandidate(noticeId, item) {
  const positive = [
    ...(Array.isArray(item.deterministic_basis) ? item.deterministic_basis : []),
    ...(Array.isArray(item.similarity_basis) ? item.similarity_basis : []),
  ].filter((basis) => Number(basis.weight) > 0);
  const conflicts = Array.isArray(item.conflicts) ? item.conflicts : [];
  const statusClass = item.status === "confirmed" ? "is-confirmed" : item.status === "rejected" ? "is-rejected" : "is-candidate";
  return `
    <article class="source-relation-candidate ${statusClass} kind-${escapeHtml(item.source_kind || "repost")}">
      <div class="source-relation-edge"><span>${escapeHtml(item.score || 0)}%</span><i></i><small>${escapeHtml(item.status_label || "待确认")}</small></div>
      <div class="source-relation-node">
        <div class="source-relation-node-head"><em>${escapeHtml(item.source_kind_label || "其他来源")}</em><b>${escapeHtml(item.notice_type_label || "公告")}</b></div>
        <strong>${escapeHtml(item.title || "关联公告")}</strong>
        <span>${escapeHtml(item.authority || item.source_site || "来源待分类")} · ${escapeHtml(item.publish_time || "时间待确认")}</span>
        <div class="source-relation-basis">${positive.slice(0, 5).map((basis) => `<small title="${escapeHtml(`${basis.left || ""} ↔ ${basis.right || ""}`)}">${escapeHtml(basis.label)} +${escapeHtml(basis.weight)}</small>`).join("")}</div>
        ${conflicts.length ? `<p class="source-relation-warning">冲突待复核：${escapeHtml(conflicts.map((value) => value.field_label).join("、"))}</p>` : ""}
        <div class="source-relation-node-links">${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">打开该来源原文</a>` : ""}<span>${escapeHtml(item.confidence_source === "rules_and_similarity" ? "规则候选" : item.confidence_source === "human_locked" ? "人工锁定" : "人工确认")}</span></div>
        <form class="source-relation-decision" data-source-relation-decision="${escapeHtml(item.related_notice_id)}" data-notice-id="${escapeHtml(noticeId)}">
          <input name="actor" value="项目审核人" maxlength="80" aria-label="操作人" required />
          <input name="reason" placeholder="填写合并、拆分或锁定理由" maxlength="500" aria-label="操作理由" required />
          <div>
            <button type="submit" name="action" value="merge">确认合并</button>
            <button type="submit" name="action" value="split" class="ghost-button">拆分并锁定</button>
            <button type="submit" name="action" value="lock" class="ghost-button">锁定合并</button>
          </div>
        </form>
      </div>
    </article>
  `;
}

async function decideSourceRelation(form, submitter) {
  const noticeId = form.dataset.noticeId || "";
  const relatedNoticeId = form.dataset.sourceRelationDecision || "";
  const data = new FormData(form);
  const action = submitter?.value || data.get("action") || "";
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/source-relations/${encodeURIComponent(relatedNoticeId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, actor: data.get("actor"), reason: data.get("reason") }),
  });
  const container = currentSourceRelationContainer(noticeId);
  if (container) container.innerHTML = renderSourceRelationGraph(payload);
  showToast(action === "split" ? "已拆分并锁定，增量匹配不会重新合并" : action === "lock" ? "已确认并锁定关系" : "已确认关系并回流数字档案");
  refreshDigitalTwinCockpit(noticeId).catch(() => {});
}

function currentDecisionSandboxContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-decision-sandbox]");
  return container?.dataset.decisionSandbox === noticeId ? container : null;
}

async function loadDecisionSandbox(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/decision-sandbox`);
  state.decisionSandboxPayloads[noticeId] = payload;
  const scenarios = Array.isArray(payload.scenarios) ? payload.scenarios : [];
  if (!state.selectedDecisionScenarios[noticeId] && scenarios.length) {
    state.selectedDecisionScenarios[noticeId] = scenarios[0].id;
  }
  const container = currentDecisionSandboxContainer(noticeId);
  if (container) container.innerHTML = renderDecisionSandbox(payload);
  return payload;
}

function renderDecisionSandbox(payload) {
  const noticeId = payload.notice_id || "";
  const baseline = payload.baseline || {};
  const scenarios = Array.isArray(payload.scenarios) ? payload.scenarios : [];
  const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
  const selectedId = state.selectedDecisionScenarios[noticeId] || scenarios[0]?.id || "";
  const selected = scenarios.find((item) => item.id === selectedId) || scenarios[0] || null;
  const scoreKeys = [
    ["opportunity_value", "机会价值"],
    ["enterprise_fit", "企业匹配"],
    ["bid_readiness", "投标准备"],
  ];
  const selectedScores = selected?.output?.scores || baseline.scores || {};
  const changes = Array.isArray(selected?.output?.score_changes) ? selected.output.score_changes : [];
  const affected = Array.isArray(selected?.output?.affected_requirements) ? selected.output.affected_requirements : [];
  const risks = Array.isArray(selected?.output?.risks) ? selected.output.risks : [];
  const actions = Array.isArray(selected?.output?.suggested_actions) ? selected.output.suggested_actions : [];
  const taskLoad = selected?.output?.task_load || {};
  const sample = selected?.output?.uncertainty || baseline.sample || {};
  const options = scenarios.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("");
  return `
    <div class="decision-sandbox-head">
      <div>
        <span class="decision-sandbox-eyebrow">投标决策沙盘</span>
        <h3>基准与模拟双舱</h3>
        <p>调整条件、观察影响、比较方案；沙盘内容不写回正式项目。</p>
      </div>
      <span class="decision-sandbox-safety"><i></i>沙盘隔离 · 正式数据只读</span>
    </div>
    <div class="decision-sandbox-stage">
      <section class="decision-sandbox-controls">
        <div class="decision-sandbox-section-title"><strong>01 设置推演条件</strong><span>临时变量</span></div>
        <form data-decision-sandbox-form="${escapeHtml(noticeId)}">
          <label class="sandbox-wide"><span>方案名称</span><input name="name" value="新推演方案" maxlength="80" required /></label>
          <label><span>投标模式</span><select name="scenario_mode"><option value="self_bid">自主投标</option><option value="joint_bid">联合伙伴投标</option></select></label>
          <label><span>截止时间变化（天）</span><input name="deadline_shift_days" type="number" min="-30" max="30" value="0" /></label>
          <label><span>预算变化（%）</span><input name="budget_change_percent" type="number" min="-50" max="100" step="0.1" value="0" /></label>
          <label><span>关键技术参数</span><select name="critical_technical_status"><option value="unchanged">保持基准</option><option value="met">已满足</option><option value="gap">存在缺口</option></select></label>
          <label><span>可用人员变化</span><input name="available_people_delta" type="number" min="-20" max="20" value="0" /></label>
          <label><span>伙伴材料</span><select name="partner_material_status"><option value="unchanged">保持基准</option><option value="complete">已补齐</option><option value="missing">缺失</option></select></label>
          <label><span>交付区域</span><select name="delivery_region_status"><option value="unchanged">保持基准</option><option value="covered">已覆盖</option><option value="uncovered">未覆盖</option></select></label>
          <label class="sandbox-wide"><span>推演人</span><input name="actor" value="项目负责人" maxlength="80" required /></label>
          <button class="decision-sandbox-run" type="submit">运行并保存方案 <b>→</b></button>
        </form>
      </section>
      <section class="decision-sandbox-cockpit">
        <div class="decision-sandbox-section-title"><strong>02 查看条件变化</strong><span>${selected ? escapeHtml(selected.name) : "等待首个方案"}</span></div>
        <div class="sandbox-dual-cockpit">
          <div class="sandbox-cabin baseline"><small>正式基准</small><strong>${escapeHtml(baseline.project?.title || "当前项目")}</strong><span>状态指纹 ${escapeHtml(String(baseline.formal_state_hash || "").slice(0, 10))}</span></div>
          <i class="sandbox-transfer">→</i>
          <div class="sandbox-cabin simulation"><small>模拟方案</small><strong>${escapeHtml(selected?.name || "尚未运行")}</strong><span>${selected ? "规则版本 " + escapeHtml(selected.rules_version || "-") : "选择条件后运行"}</span></div>
        </div>
        <div class="sandbox-score-compare">
          ${scoreKeys.map(([key, label]) => {
            const before = Number(baseline.scores?.[key] || 0);
            const after = Number(selectedScores[key] || before);
            const delta = after - before;
            return `<article class="sandbox-score ${delta > 0 ? "is-up" : delta < 0 ? "is-down" : "is-flat"}"><span>${label}</span><div><b>${before}</b><i>→</i><strong>${after}</strong></div><small>${delta ? `${delta > 0 ? "+" : ""}${delta} 分` : "无变化"}</small></article>`;
          }).join("")}
        </div>
        ${changes.length ? `<details class="sandbox-rule-trace" open><summary>逐项解释：输入 → 影响 → 规则</summary>${changes.map((item) => `<p><b>${escapeHtml(item.input || item.reason || "条件变化")}</b><span>${escapeHtml(item.before)} → ${escapeHtml(item.after)}</span><small>${escapeHtml(item.rule || "")}</small></p>`).join("")}</details>` : '<div class="sandbox-empty">运行方案后，这里会逐项解释分数为什么变化。</div>'}
      </section>
    </div>
    <div class="decision-sandbox-impact-grid">
      <section><div class="decision-sandbox-section-title"><strong>受影响要求</strong><span>${affected.length} 项</span></div>${affected.length ? affected.map((item) => `<p><b>${escapeHtml(item.requirement_key || "要求")}</b><span>${escapeHtml(item.title || "")}</span><small>${escapeHtml((item.reasons || []).join("、"))}</small></p>`).join("") : '<p class="sandbox-empty">当前条件未触发要求变化</p>'}</section>
      <section><div class="decision-sandbox-section-title"><strong>资源与任务</strong><span>负荷透视</span></div><div class="sandbox-load"><p><b>${escapeHtml(taskLoad.baseline_task_count || baseline.task_load?.formal_task_count || 0)}</b><span>正式任务</span></p><i>+</i><p><b>${escapeHtml(taskLoad.additional_action_count || 0)}</b><span>新增行动</span></p><i>÷</i><p><b>${escapeHtml(taskLoad.scenario_people ?? baseline.task_load?.team_member_count ?? 0)}</b><span>可用人员</span></p></div><small>模拟人均负荷 ${escapeHtml(taskLoad.tasks_per_person || 0)} 项</small></section>
      <section><div class="decision-sandbox-section-title"><strong>风险方向</strong><span>${risks.length} 项</span></div>${risks.length ? risks.map((item) => `<p class="sandbox-risk risk-${escapeHtml(item.severity || "medium")}"><b>${escapeHtml(item.title || "风险")}</b><span>${escapeHtml(item.detail || "")}</span></p>`).join("") : '<p class="sandbox-empty">未新增规则风险</p>'}</section>
      <section><div class="decision-sandbox-section-title"><strong>建议行动</strong><span>${actions.length} 项</span></div>${actions.length ? actions.map((item) => `<p><b>${escapeHtml(item.title || "待办")}</b><span>${escapeHtml(item.owner_role || "负责人")}</span></p>`).join("") : '<p class="sandbox-empty">当前没有新增行动</p>'}</section>
    </div>
    <div class="decision-sandbox-uncertainty"><strong>边界声明</strong><span>${escapeHtml(sample.message || "只展示条件变化和风险方向，不计算中标概率。")}</span><b>不输出中标概率</b></div>
    <section class="decision-sandbox-library">
      <div class="decision-sandbox-section-title"><strong>03 保存、复算与比较</strong><span>${scenarios.length} 个历史方案</span></div>
      <div class="sandbox-scenario-list">${scenarios.length ? scenarios.map((item) => `<article class="${item.id === selected?.id ? "is-selected" : ""}"><button type="button" data-select-decision-scenario="${escapeHtml(item.id)}" data-notice-id="${escapeHtml(noticeId)}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.scenario_mode_label || "")}</span><small>${escapeHtml(item.created_by || "")} · ${escapeHtml(item.created_at || "")}</small></button><div><button type="button" data-recompute-decision-scenario="${escapeHtml(item.id)}" data-notice-id="${escapeHtml(noticeId)}">复算</button><button type="button" data-promote-decision-scenario="${escapeHtml(item.id)}" data-notice-id="${escapeHtml(noticeId)}">转为待确认建议</button></div></article>`).join("") : '<p class="sandbox-empty">还没有保存的推演方案</p>'}</div>
      ${scenarios.length >= 2 ? `<div class="sandbox-compare-bar"><select data-sandbox-left>${options}</select><span>对比</span><select data-sandbox-right>${scenarios.slice().reverse().map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("")}</select><button type="button" data-compare-decision-scenarios="${escapeHtml(noticeId)}">生成对比结论</button></div><div data-sandbox-comparison></div>` : ""}
    </section>
    ${suggestions.length ? `<section class="decision-sandbox-decisions"><div class="decision-sandbox-section-title"><strong>04 负责人确认</strong><span>确认后才进入正式计划</span></div>${suggestions.map((item) => `<article class="status-${escapeHtml(item.status)}"><div><strong>${escapeHtml(item.status === "pending" ? "待负责人确认" : item.status === "accepted" ? "已纳入正式计划" : "已拒绝")}</strong><span>${escapeHtml(item.actions?.length || 0)} 项行动 · 发起人 ${escapeHtml(item.requested_by || "")}</span></div>${item.status === "pending" ? `<form data-sandbox-suggestion-decision="${escapeHtml(item.id)}" data-notice-id="${escapeHtml(noticeId)}"><input name="actor" value="投标总监" required /><input name="note" placeholder="填写确认依据" required /><button name="decision" value="accept" type="submit">确认纳入</button><button name="decision" value="reject" type="submit" class="ghost-button">拒绝</button></form>` : `<small>${escapeHtml(item.decided_by || "")} · ${escapeHtml(item.decision_note || "")}</small>`}</article>`).join("")}</section>` : ""}
  `;
}

async function createDecisionSandboxScenario(form) {
  const noticeId = form.dataset.decisionSandboxForm;
  const data = new FormData(form);
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/decision-sandbox/scenarios`, {
    method: "POST",
    body: JSON.stringify({
      name: data.get("name"), actor: data.get("actor"),
      params: {
        scenario_mode: data.get("scenario_mode"),
        deadline_shift_days: Number(data.get("deadline_shift_days") || 0),
        budget_change_percent: Number(data.get("budget_change_percent") || 0),
        critical_technical_status: data.get("critical_technical_status"),
        available_people_delta: Number(data.get("available_people_delta") || 0),
        partner_material_status: data.get("partner_material_status"),
        delivery_region_status: data.get("delivery_region_status"),
      },
    }),
  });
  state.selectedDecisionScenarios[noticeId] = payload.id;
  await loadDecisionSandbox(noticeId);
  showToast("推演方案已保存，正式项目数据未改变");
}

async function recomputeDecisionScenario(button) {
  const noticeId = button.dataset.noticeId;
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/decision-sandbox/scenarios/${encodeURIComponent(button.dataset.recomputeDecisionScenario)}/recompute`, { method: "POST" });
  showToast(result.identical ? "复算结果一致，可重复验证" : "复算结果已变化，请检查正式基准");
}

async function promoteDecisionScenario(button) {
  const noticeId = button.dataset.noticeId;
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/decision-sandbox/scenarios/${encodeURIComponent(button.dataset.promoteDecisionScenario)}/promote`, { method: "POST", body: JSON.stringify({ actor: "项目负责人" }) });
  await loadDecisionSandbox(noticeId);
  showToast("已生成待确认建议，尚未写入正式任务");
}

async function decideDecisionSandboxSuggestion(form, submitter) {
  const noticeId = form.dataset.noticeId;
  const data = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/decision-sandbox/suggestions/${encodeURIComponent(form.dataset.sandboxSuggestionDecision)}/decision`, {
    method: "POST",
    body: JSON.stringify({ accept: submitter?.value === "accept", actor: data.get("actor"), note: data.get("note") }),
  });
  await loadDecisionSandbox(noticeId);
  showToast(submitter?.value === "accept" ? "负责人已确认，行动已进入正式计划" : "方案已拒绝，正式项目未改变");
}

async function compareDecisionSandboxScenarios(button) {
  const shell = button.closest("[data-decision-sandbox]");
  const leftId = shell.querySelector("[data-sandbox-left]")?.value || "";
  const rightId = shell.querySelector("[data-sandbox-right]")?.value || "";
  const result = await api(`/api/opportunities/${encodeURIComponent(button.dataset.compareDecisionScenarios)}/decision-sandbox/compare?left_id=${encodeURIComponent(leftId)}&right_id=${encodeURIComponent(rightId)}`);
  const target = shell.querySelector("[data-sandbox-comparison]");
  if (target) target.innerHTML = `<div class="sandbox-comparison-result"><strong>${escapeHtml(result.left?.name || "方案一")} ↔ ${escapeHtml(result.right?.name || "方案二")}</strong>${(result.interpretation || []).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</div>`;
}

function renderDigitalTwinCockpit(twin, item) {
  if (!twin || twin.error) {
    return `<section class="digital-twin-cockpit is-error" data-visual-component="digital-twin" data-digital-twin-cockpit="${escapeHtml(item.notice_id)}"><strong>项目档案尚未同步</strong><span>${escapeHtml(twin?.error || "服务暂不可用")}。当前记录仍保留，可稍后重试。</span><button class="ghost-button" type="button" data-refresh-digital-twin="${escapeHtml(item.notice_id)}">重新同步项目档案</button></section>`;
  }
  const scores = twin.scores || {};
  const sourceSync = twin.source_sync || {};
  const snapshot = twin.snapshot || {};
  const changes = Array.isArray(snapshot.changes_since_previous) ? snapshot.changes_since_previous : [];
  const timeline = Array.isArray(twin.timeline) ? twin.timeline.slice(0, 4) : [];
  const actions = Array.isArray(twin.next_actions) ? twin.next_actions : [];
  const sections = Array.isArray(twin.dossier_sections) ? twin.dossier_sections : [];
  return `
    <section class="digital-twin-cockpit" data-visual-component="digital-twin" data-digital-twin-cockpit="${escapeHtml(item.notice_id)}" data-state-hash="${escapeHtml(snapshot.state_hash || "")}">
      <div class="digital-twin-topline">
        <div>
          <span class="digital-twin-kicker">投标数字孪生 · 动态项目档案</span>
          <h2 class="tt-conclusion-title">${escapeHtml(digitalTwinConclusion(scores, actions))}</h2>
          <strong>${escapeHtml(item.project_no || "项目编号待确认")} · ${escapeHtml(item.purchaser || "采购主体待确认")}</strong>
          <small>一个入口查看公告、附件、要求、能力证据、会审、团队和飞书执行状态</small>
        </div>
        <div class="digital-twin-sync sync-${escapeHtml(sourceSync.status || "unknown")}">
          ${semanticStateTag(sourceSync.status || "unknown", sourceSync.status_label || "同步状态待确认")}
          <small>数据截至 ${escapeHtml(twin.refresh?.data_as_of || "待确认")}</small>
          <button class="ghost-button" type="button" data-open-evidence-microscope="${escapeHtml(item.notice_id)}">查看证据依据</button>
          <button class="ghost-button" type="button" data-refresh-digital-twin="${escapeHtml(item.notice_id)}">刷新当前档案</button>
        </div>
      </div>
      <div class="digital-twin-score-grid">
        ${[scores.opportunity_value, scores.enterprise_fit, scores.bid_readiness].filter(Boolean).map((score) => renderDigitalTwinScore(score, item.notice_id)).join("")}
      </div>
      <div class="digital-twin-flow" aria-label="数字项目档案操作流程">
        ${digitalTwinFlowSteps(twin).map((step, index) => `
          <button type="button" class="digital-twin-flow-step is-${escapeHtml(step.status)}" data-scroll-opportunity-target="${escapeHtml(step.target)}">
            <b>${index + 1}</b><span>${escapeHtml(step.label)}</span><small>${escapeHtml(step.detail)}</small>
          </button>
        `).join('<i class="digital-twin-flow-arrow">→</i>')}
      </div>
      <div class="digital-twin-dossier-strip">
        ${sections.map((section) => `<span><b>${escapeHtml(section.count || 0)}</b>${escapeHtml(section.label || "档案项")}</span>`).join("")}
      </div>
      <div class="digital-twin-lower-grid">
        <div class="digital-twin-change-pulse">
          <div class="digital-twin-panel-title"><strong>状态变化</strong><span>${snapshot.status === "changed" ? "已生成新快照" : "当前状态无变化"}</span></div>
          ${changes.length ? changes.map((change) => `<p><span>${escapeHtml(change.label || "状态")}</span><del>${escapeHtml(change.before ?? "-")}</del><b>→</b><ins>${escapeHtml(change.after ?? "-")}</ins></p>`).join("") : "<p><span>暂无上一版差异</span></p>"}
          <small>状态指纹 ${escapeHtml(String(snapshot.state_hash || "").slice(0, 12))} · 旧版本不会被覆盖</small>
        </div>
        <div class="digital-twin-next-actions">
          <div class="digital-twin-panel-title"><strong>此刻最该做什么</strong><span>${escapeHtml(actions.length)} 项</span></div>
          ${actions.map((action) => `<button type="button" class="priority-${escapeHtml(action.priority || "normal")}" data-scroll-opportunity-target="${escapeHtml(action.target || "opportunityCollaborationSection")}"><span>${escapeHtml(action.title || "继续推进")}</span><small>${escapeHtml(action.reason || "")}</small></button>`).join("")}
        </div>
      </div>
      <details class="digital-twin-timeline">
        <summary>最近动态时间线 <span>${escapeHtml(twin.timeline?.length || 0)} 条可追溯记录</span></summary>
        ${timeline.map((event) => `<p class="severity-${escapeHtml(event.severity || "normal")}"><time>${escapeHtml(event.at || "时间待确认")}</time><strong>${escapeHtml(event.title || "状态更新")}</strong><span>${escapeHtml(event.detail || "")}</span></p>`).join("") || "<p>暂无动态记录</p>"}
      </details>
    </section>
  `;
}

function renderDigitalTwinScore(score, noticeId) {
  const value = Math.max(0, Math.min(Number(score.score || 0), 100));
  const components = Array.isArray(score.components) ? score.components : [];
  const missing = Array.isArray(score.missing) ? score.missing : [];
  return `
    <article class="digital-twin-score score-${escapeHtml(score.status || "risk")}">
      <div class="digital-twin-score-ring" style="--score:${value}"><strong>${escapeHtml(value)}</strong><span>分</span></div>
      <div class="digital-twin-score-copy">
        <div><strong>${escapeHtml(score.label || "评分")}</strong>${semanticStateTag(score.status || "unknown", score.status_label || "待评估")}</div>
        <p>${escapeHtml(score.explanation || "")}</p>
        ${missing.length ? `<small class="digital-twin-score-missing">待补：${escapeHtml(missing.join("、"))}</small>` : ""}
      </div>
      <details>
        <summary>为什么是 ${escapeHtml(value)} 分</summary>
        ${components.map((component) => `<p><span>${escapeHtml(component.label || "维度")} · 权重 ${escapeHtml(component.weight || 0)}%</span><b>${escapeHtml(component.score || 0)} 分</b><small>${escapeHtml(component.evidence || "暂无依据")}</small></p>`).join("")}
        <small>规则：${escapeHtml(score.rule_version || "-")} · ${escapeHtml(score.evaluated_at || "")}</small>
      </details>
      <button class="evidence-entry-button" type="button" data-open-evidence-microscope="${escapeHtml(noticeId || "")}" data-evidence-claim-type="score" data-evidence-claim-key="${escapeHtml(score.key || "")}">查看评分依据</button>
    </article>
  `;
}

function digitalTwinFlowSteps(twin) {
  const counts = twin.counts || {};
  const workflow = twin.workflow || {};
  const scores = twin.scores || {};
  return [
    { label: "发现项目", detail: twin.source_sync?.status_label || "来源待确认", status: ["fresh", "normal"].includes(twin.source_sync?.status) ? "ready" : "attention", target: "opportunityChangeSection" },
    { label: "建立档案", detail: `${counts.revisions || 0} 次修订`, status: "ready", target: "opportunityChangeSection" },
    { label: "拆解要求", detail: `${counts.requirements || 0} 条`, status: counts.requirements ? "ready" : "attention", target: "opportunityRequirementsSection" },
    { label: "匹配能力", detail: `${counts.capability_matches || 0} 条`, status: scores.enterprise_fit?.status === "insufficient" ? "attention" : "ready", target: "opportunityCapabilitySection" },
    { label: "会审决策", detail: `${counts.pending_reviews || 0} 项待裁决`, status: counts.pending_reviews ? "attention" : "ready", target: "opportunityReviewSection" },
    { label: "协同执行", detail: workflow.stage_label || "线索识别", status: workflow.owner_name || workflow.owner_open_id ? "ready" : "attention", target: "opportunityCollaborationSection" },
  ];
}

async function refreshDigitalTwinCockpit(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-digital-twin-cockpit]");
  if (!container || container.dataset.digitalTwinCockpit !== noticeId) return;
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  if (!item || state.digitalTwinRefreshRunning) return;
  state.digitalTwinRefreshRunning = true;
  try {
    const twin = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/digital-twin`);
    if (!el.opportunityDetailDialog?.open || state.openDigitalTwinNoticeId !== noticeId) return;
    const previousHash = container.dataset.stateHash || "";
    const nextHash = twin.snapshot?.state_hash || "";
    if (previousHash && nextHash && previousHash !== nextHash) {
      const scrollTop = el.opportunityDetailContent?.scrollTop || 0;
      const current = await api(`/api/opportunities/${encodeURIComponent(noticeId)}`);
      if (!el.opportunityDetailDialog?.open || state.openDigitalTwinNoticeId !== noticeId) return;
      const index = state.opportunities.findIndex((value) => value.notice_id === noticeId);
      if (index >= 0) state.opportunities[index] = current;
      await openOpportunityDetail(noticeId, twin, scrollTop);
      return;
    }
    if (container.isConnected) {
      container.outerHTML = renderDigitalTwinCockpit(twin, item);
      announceBusinessEvent(el.opportunityDetailContent?.querySelector("[data-digital-twin-cockpit]"), previousHash !== nextHash ? "state" : "arrival");
    }
  } finally {
    state.digitalTwinRefreshRunning = false;
  }
}

function scheduleDigitalTwinRefresh(noticeId) {
  if (state.digitalTwinRefreshTimer) window.clearInterval(state.digitalTwinRefreshTimer);
  state.openDigitalTwinNoticeId = noticeId;
  state.digitalTwinRefreshTimer = window.setInterval(() => {
    if (!el.opportunityDetailDialog?.open || state.openDigitalTwinNoticeId !== noticeId) return;
    refreshDigitalTwinCockpit(noticeId).catch(() => {});
  }, 30000);
}

function stopDigitalTwinRefresh() {
  if (state.digitalTwinRefreshTimer) window.clearInterval(state.digitalTwinRefreshTimer);
  state.digitalTwinRefreshTimer = null;
  state.openDigitalTwinNoticeId = "";
}

async function openEvidenceMicroscope(noticeId, claimType = "", claimKey = "") {
  if (!noticeId || !el.evidenceMicroscopeDialog || !el.evidenceMicroscopeContent) return;
  state.evidenceMicroscopeNoticeId = noticeId;
  state.evidenceMicroscopePayload = null;
  const opportunity = state.opportunities.find((item) => item.notice_id === noticeId) || {};
  el.evidenceMicroscopeTitle.textContent = `${opportunity.project_no || opportunity.notice_id || "项目"} · 证据核验`;
  el.evidenceMicroscopeMeta.textContent = "正在汇总来源、版本、定位、冲突与人工确认记录…";
  el.evidenceMicroscopeContent.innerHTML = '<div class="evidence-microscope-loading"><strong>正在建立可审计证据链</strong><span>判断 → 证据 → 原文 → 人工确认</span></div>';
  if (!el.evidenceMicroscopeDialog.open) el.evidenceMicroscopeDialog.showModal();
  const query = new URLSearchParams();
  if (claimType) query.set("claim_type", claimType);
  if (claimKey) query.set("claim_key", claimKey);
  const suffix = query.toString() ? `?${query}` : "";
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/evidence-microscope${suffix}`);
  if (!el.evidenceMicroscopeDialog.open || state.evidenceMicroscopeNoticeId !== noticeId) return;
  state.evidenceMicroscopePayload = payload;
  const evidenceAttention = Number(payload.summary?.pending_count || 0) + Number(payload.summary?.conflict_count || 0) + Number(payload.summary?.expired_count || 0);
  el.evidenceMicroscopeTitle.textContent = evidenceAttention
    ? `${evidenceAttention} 项证据状态需要复核`
    : `${payload.summary?.verified_count || 0} 项关键判断均可追溯`;
  el.evidenceMicroscopeMeta.textContent = `项目 ${opportunity.project_no || opportunity.notice_id || "待确认"} · 公告 ${opportunity.notice_id || noticeId} · ${payload.source_site || "来源待确认"} · ${payload.summary?.source_count || 0} 份证据`;
  el.evidenceMicroscopeContent.innerHTML = renderEvidenceMicroscope(payload, payload.selected_claim_id);
  announceBusinessEvent(el.evidenceMicroscopeContent.querySelector(".evidence-chain-visual"), "arrival");
}

function closeEvidenceMicroscope() {
  el.evidenceMicroscopeDialog?.close();
  state.evidenceMicroscopeNoticeId = "";
  state.evidenceMicroscopePayload = null;
}

function renderEvidenceMicroscope(payload, selectedClaimId = "") {
  const claims = Array.isArray(payload.claims) ? payload.claims : [];
  const selected = claims.find((item) => item.id === selectedClaimId) || claims[0];
  const summary = payload.summary || {};
  const disagreements = Array.isArray(payload.disagreements) ? payload.disagreements : [];
  const events = Array.isArray(payload.audit_events) ? payload.audit_events : [];
  if (!selected) return '<div class="evidence-microscope-empty tt-empty-state"><strong>尚未形成可回查判断</strong><span>先录入要求、企业材料或人工决策，再建立证据链。</span></div>';
  const sources = Array.isArray(selected.evidence) ? selected.evidence : [];
  const tenderSources = sources.filter((item) => item.source_type !== "enterprise_material");
  const enterpriseSources = sources.filter((item) => item.source_type === "enterprise_material");
  return `
    <section class="evidence-assurance-strip ${summary.audit_complete ? "is-complete" : "is-warning"}">
      <div>${semanticStateTag(summary.audit_complete ? "verified" : "review", summary.audit_complete ? "关键判断均可追溯" : "存在无有效证据的确定性判断")}<small>系统不会把待确认内容伪装成确定结论</small></div>
      <span>已验证 <b>${escapeHtml(summary.verified_count || 0)}</b></span>
      <span>待确认 <b>${escapeHtml(summary.pending_count || 0)}</b></span>
      <span>已过期 <b>${escapeHtml(summary.expired_count || 0)}</b></span>
      <span>冲突 <b>${escapeHtml(summary.conflict_count || 0)}</b></span>
      <span>不可访问 <b>${escapeHtml(summary.unavailable_count || 0)}</b></span>
    </section>
    <div class="evidence-microscope-layout">
      <aside class="evidence-claim-rail" aria-label="关键判断列表">
        <div class="evidence-claim-rail-heading"><strong>关键判断</strong><span>${escapeHtml(claims.length)} 项</span></div>
        ${claims.map((claim) => `<button type="button" class="evidence-claim-tab status-${escapeHtml(claim.status || "pending")} ${claim.id === selected.id ? "is-active" : ""}" data-select-evidence-claim="${escapeHtml(claim.id)}"><span>${escapeHtml(claim.claim_type_label || claim.claim_type)}</span><strong>${escapeHtml(claim.title || "未命名判断")}</strong><small>${escapeHtml(claim.status_label || claim.status)} · ${escapeHtml(claim.evidence?.length || 0)} 条依据</small></button>`).join("")}
      </aside>
      <div class="evidence-workspace">
        <section class="evidence-chain-visual" aria-label="可视化证据链">
          <div class="evidence-chain-node is-claim"><span>${escapeHtml(selected.claim_type_label || "判断")}</span><strong>${escapeHtml(selected.title)}</strong><p>${escapeHtml(selected.conclusion)}</p>${semanticStateTag(selected.status, selected.status_label || selected.status, `claim-status status-${escapeHtml(selected.status)}`)}</div>
          <i class="evidence-chain-arrow">依据</i>
          <div class="evidence-chain-sources">${sources.map((source) => `<div class="evidence-chain-node is-source status-${escapeHtml(source.verified_status)}"><span>${escapeHtml(source.stance_label || "依据")}</span><strong>${escapeHtml(source.file_name || source.source_site || "来源材料")}</strong><small>${escapeHtml(evidenceLocation(source))}</small><em>${escapeHtml(source.verified_status_label || source.verified_status)}</em></div>`).join("") || '<div class="evidence-chain-node is-source status-pending"><strong>证据待补</strong><small>当前判断不能视为确定结论</small></div>'}</div>
        </section>
        ${renderEvidenceComparison(selected.comparison || {})}
        <section class="evidence-split-view">
          <div class="evidence-pane is-tender"><div class="evidence-pane-heading"><strong>招标原文与公开来源</strong><span>${escapeHtml(tenderSources.length)} 份</span></div>${tenderSources.map((source) => renderEvidenceSourceCard(source, payload.notice_id)).join("") || '<div class="evidence-pane-empty">暂无招标侧证据</div>'}</div>
          <div class="evidence-pane is-enterprise"><div class="evidence-pane-heading"><strong>企业材料与对照证据</strong><span>${escapeHtml(enterpriseSources.length)} 份</span></div>${enterpriseSources.map((source) => renderEvidenceSourceCard(source, payload.notice_id)).join("") || '<div class="evidence-pane-empty">暂无企业侧证据，判断将保持待确认</div>'}</div>
        </section>
        ${renderAgentDisagreements(disagreements)}
        <details class="evidence-audit-timeline" ${events.length ? "" : "hidden"}><summary>人工确认与版本失效记录 <span>${escapeHtml(events.length)} 条</span></summary>${events.map((event) => `<p><time>${escapeHtml(compactDateTimeText(event.created_at || ""))}</time><strong>${escapeHtml(event.actor || "系统")}</strong><span>${escapeHtml(evidenceAuditActionLabel(event.action))}</span><small>${escapeHtml(event.reason || "")}</small></p>`).join("")}</details>
      </div>
    </div>
  `;
}

function renderEvidenceSourceCard(source, noticeId) {
  return `
    <article class="evidence-source-card status-${escapeHtml(source.verified_status || "pending")}" data-evidence-source-id="${escapeHtml(source.id)}">
      <div class="evidence-source-topline">
        <div><span>${escapeHtml(evidenceSourceTypeLabel(source.source_type))}</span><strong>${escapeHtml(source.file_name || source.source_site || "来源材料")}</strong></div>
        ${semanticStateTag(source.verified_status || "pending", source.verified_status_label || source.verified_status || "待确认")}
      </div>
      <div class="evidence-source-meta">
        <span>来源：${escapeHtml(source.source_site || "待确认")}</span>
        <span>定位：${escapeHtml(evidenceLocation(source))}</span>
        <span>版本：${escapeHtml(source.revision_id ? source.revision_id.slice(0, 12) : "当前基线")}</span>
        <span>采集：${escapeHtml(compactDateTimeText(source.captured_at || source.created_at || ""))}</span>
        <span>哈希：${escapeHtml(String(source.content_hash || "").slice(0, 16))}</span>
        <span>定位置信度：${escapeHtml(source.locator_confidence || 0)}%</span>
      </div>
      <blockquote>${renderHighlightedEvidence(source.quote || "", source.highlights || [])}</blockquote>
      ${source.extraction_method === "ocr_required" ? '<p class="evidence-ocr-notice">扫描件尚不能可靠定位，已进入 OCR 降级与人工补录流程。</p>' : ""}
      <div class="evidence-source-actions">
        ${source.source_url ? `<a class="link-button" href="${escapeHtml(source.source_url)}" target="_blank" rel="noreferrer">打开来源</a>` : ""}
        ${source.confirmed_by ? `<small>由 ${escapeHtml(source.confirmed_by)} 于 ${escapeHtml(compactDateTimeText(source.confirmed_at || ""))} 确认</small>` : ""}
      </div>
      <form class="evidence-review-form" data-evidence-review-form="${escapeHtml(noticeId)}" data-evidence-id="${escapeHtml(source.id)}">
        <select name="action"><option value="confirm">确认有效</option><option value="reject">标记冲突 / 驳回</option><option value="request_more">要求补充</option><option value="mark_unavailable">来源不可访问</option></select>
        <input name="actor" required maxlength="80" placeholder="确认人" />
        <input name="reason" required maxlength="500" placeholder="核验理由（永久保留）" />
        <button class="primary-lite-button" type="submit">签字确认</button>
      </form>
    </article>
  `;
}

function renderHighlightedEvidence(text, highlights) {
  const sorted = [...highlights].sort((a, b) => Number(a.start || 0) - Number(b.start || 0));
  let cursor = 0;
  let html = "";
  sorted.forEach((item) => {
    const start = Math.max(cursor, Number(item.start || 0));
    const end = Math.max(start, Number(item.end || start));
    html += escapeHtml(text.slice(cursor, start));
    html += `<mark class="evidence-highlight-${escapeHtml(item.kind || "value")}">${escapeHtml(text.slice(start, end))}</mark>`;
    cursor = end;
  });
  return html + escapeHtml(text.slice(cursor));
}

function renderEvidenceComparison(comparison) {
  const items = Array.isArray(comparison.items) ? comparison.items : [];
  if (!items.length) return "";
  return `<section class="evidence-comparison status-${escapeHtml(comparison.status || "single_source")}"><div><strong>字符与字段级比对</strong><span>${comparison.status === "different" ? "发现差异，保留双方证据" : "关键数值一致"}</span></div>${items.map((item) => `<p class="${item.conflict ? "has-conflict" : ""}"><strong>${escapeHtml(item.field || "字段")}</strong>${(item.values || []).map((value) => `<span>${escapeHtml(value.value || "")}</span>`).join("")}</p>`).join("")}</section>`;
}

function renderAgentDisagreements(disagreements) {
  if (!disagreements.length) return "";
  return `<section class="evidence-agent-disagreements"><div class="evidence-pane-heading"><strong>为什么不同意</strong><span>${escapeHtml(disagreements.length)} 组多智能体分歧</span></div>${disagreements.map((group) => `<article><h4>${escapeHtml(group.requirement_key || "要求")}</h4><div>${(group.opinions || []).map((opinion) => `<p class="decision-${escapeHtml(opinion.decision || "escalate")}"><strong>${escapeHtml(opinion.agent_label || opinion.agent_role)}</strong><span>${escapeHtml(reviewOpinionModeLabel(opinion))}</span><small>${escapeHtml(opinion.rationale || "未提供理由")}</small><em>${escapeHtml(opinion.evidence?.length || 0)} 条审阅依据</em></p>`).join("")}</div></article>`).join("")}</section>`;
}

function evidenceLocation(source) {
  const parts = [];
  if (source.page_number) parts.push(`第 ${source.page_number} 页`);
  if (source.section_path) parts.push(source.section_path);
  if (source.paragraph_index) parts.push(`第 ${source.paragraph_index} 段`);
  if (source.selector) parts.push(source.selector);
  return parts.join(" · ") || "定位待补";
}

function evidenceSourceTypeLabel(type) {
  return { webpage: "网页快照", pdf: "PDF 原文", docx: "DOCX 原文", enterprise_material: "企业材料", rule: "规则结果" }[type] || type || "来源";
}

function evidenceAuditActionLabel(action) {
  return { confirm: "确认有效", reject: "标记冲突", request_more: "要求补充", mark_unavailable: "标记不可访问", source_invalidated: "版本变化导致失效" }[action] || action || "状态变化";
}

async function submitEvidenceReview(form) {
  const noticeId = form.dataset.evidenceReviewForm || "";
  const evidenceId = form.dataset.evidenceId || "";
  const values = new FormData(form);
  const selectedClaimId = el.evidenceMicroscopeContent?.querySelector("[data-select-evidence-claim].is-active")?.dataset.selectEvidenceClaim || "";
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/evidence-microscope/${encodeURIComponent(evidenceId)}/review`, {
    method: "POST",
    body: JSON.stringify({ action: values.get("action") || "", actor: values.get("actor") || "", reason: values.get("reason") || "" }),
  });
  state.evidenceMicroscopePayload = payload;
  el.evidenceMicroscopeContent.innerHTML = renderEvidenceMicroscope(payload, selectedClaimId);
  showToast("证据核验已写入审计链，后续自动运行不会覆盖");
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

function renderOpportunityJourney(item, reviewSummary = {}) {
  const intelligence = item.intelligence || {};
  const requirementReview = intelligence.requirement_review || {};
  const workflow = item.workflow || {};
  const changeReview = item.change_review || {};
  const qualification = item.qualification || {};
  const blockers = qualificationBlockers(qualification, "approve_bid");
  const reviewPending = Number(reviewSummary.pending_count || 0);
  const reviewTotal = Number(reviewSummary.total_count || 0);
  const requirementsCovered = Number(requirementReview.coverage_score || 0);
  const steps = [
    {
      label: "证据变更",
      target: "opportunityChangeSection",
      status: Number(changeReview.pending_count || 0) ? "attention" : "ready",
      detail: Number(changeReview.pending_count || 0)
        ? `${changeReview.pending_count} 条公告变更待复核`
        : "当前版本已核对",
    },
    {
      label: "要求账本",
      target: "opportunityRequirementsSection",
      status: requirementsCovered >= 40 ? "ready" : "attention",
      detail: `需求覆盖 ${requirementsCovered}%${requirementsCovered >= 40 ? "，可继续推进" : "，需补齐原文要求"}`,
    },
    {
      label: "专业对手盘",
      target: "opportunityReviewSection",
      status: reviewPending ? "attention" : "ready",
      detail: reviewPending
        ? `${reviewPending} 项等待人工裁决`
        : reviewTotal ? "会审项已全部裁决" : "暂无待裁决项",
    },
    {
      label: "协同执行",
      target: "opportunityCollaborationSection",
      status: workflow.owner_open_id && !blockers.length ? "ready" : "attention",
      detail: workflow.owner_open_id
        ? (blockers.length ? `Go 前待补：${blockers.slice(0, 2).join("、")}` : "负责人和准入门禁已就绪")
        : "先认领负责人，再启动项目群战情室",
    },
  ];
  const next = steps.find((step) => step.status === "attention") || steps[steps.length - 1];
  return `
    <div class="opportunity-journey-heading">
      <div><strong>机会推进路径</strong><span>下一步：${escapeHtml(next.label)}</span></div>
      <small>${escapeHtml(next.detail)}</small>
    </div>
    <div class="opportunity-journey-steps">
      ${steps.map((step, index) => `<button class="opportunity-journey-step is-${escapeHtml(step.status)}" type="button" data-scroll-opportunity-target="${escapeHtml(step.target)}"><b>${index + 1}</b><span>${escapeHtml(step.label)}</span><small>${escapeHtml(step.detail)}</small></button>`).join("")}
    </div>
  `;
}

function refreshOpportunityJourney(noticeId, reviewSummary = {}) {
  const item = state.opportunities.find((value) => value.notice_id === noticeId);
  const container = el.opportunityDetailContent?.querySelector("[data-opportunity-journey]");
  if (item && container?.dataset.opportunityJourney === noticeId) {
    container.innerHTML = renderOpportunityJourney(item, reviewSummary);
  }
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
  const allEscalations = Array.isArray(actionQueue.escalations) ? actionQueue.escalations : [];
  const escalations = allEscalations.slice(0, 5);
  const priorities = state.opportunities
    .map(opportunityNextWork)
    .filter(Boolean)
    .slice(0, 3);
  el.opportunityDecisionBoard.className = "opportunity-decision-board";
  el.opportunityDecisionBoard.innerHTML = `
    <section>
      <span class="decision-board-kicker">今日推进</span>
      <strong>${priorities.length ? `${priorities.length} 条优先处理` : "暂无优先待办"}</strong>
      <div class="decision-priority-list">
        ${priorities.length ? priorities.map((item) => `
          <button type="button" class="decision-priority-item" data-view-opportunity="${escapeHtml(item.noticeId)}">
            <strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong>
            <small>${escapeHtml(item.action)}</small>
          </button>
        `).join("") : '<small>机会进入队列后会按截止、变更、门禁与协同状态自动排序。</small>'}
      </div>
    </section>
    <section>
      <span class="decision-board-kicker">推进门禁</span>
      <strong>${escapeHtml(actionQueue.qualification_ready || 0)} 条可提交决策</strong>
      <div class="decision-board-lines">
        ${decisionBoardLine("准入待补", actionQueue.qualification_blocked || 0)}
        ${decisionBoardLine("团队待补", actionQueue.team_incomplete || 0)}
        ${decisionBoardLine("关键关系待补", actionQueue.stakeholder_incomplete || 0)}
        ${decisionBoardLine("关系行动待办", actionQueue.relationship_action_open || 0)}
      </div>
      <div class="decision-board-pipeline">
        ${decisionPipelineValue("Go", decisions.go || 0, "go")}
        ${decisionPipelineValue("Hold", decisions.hold || 0, "hold")}
        ${decisionPipelineValue("No-Go", decisions.no_go || 0, "no-go")}
      </div>
      <small>主任务：进行 ${escapeHtml(actionQueue.task_open || 0)} · 完成 ${escapeHtml(actionQueue.task_completed || 0)} · 逾期 ${escapeHtml(actionQueue.task_overdue || 0)}</small>
    </section>
    <section>
      <span class="decision-board-kicker">协同与风险</span>
      <div class="decision-board-heading">
        <strong>${allEscalations.length ? `${allEscalations.length} 条需要管理介入` : "当前无协同逾期"}</strong>
        ${allEscalations.length ? '<button class="text-link" type="button" data-send-opportunity-escalations>发送飞书摘要</button>' : ""}
      </div>
      <div class="decision-board-lines decision-board-risk-lines">
        ${decisionBoardLine("公告变更待复核", actionQueue.change_review_pending || 0, actionQueue.change_review_overdue ? "danger" : "")}
        ${decisionBoardLine("变更复核逾期", actionQueue.change_review_overdue || 0, actionQueue.change_review_overdue ? "danger" : "")}
        ${decisionBoardLine("待管理决策", actionQueue.decision_pending || 0)}
        ${decisionBoardLine(`决策超时（${actionQueue.decision_sla_hours || 0} 小时）`, actionQueue.decision_overdue || 0, actionQueue.decision_overdue ? "danger" : "")}
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

function opportunityNextWork(item) {
  const title = String(item?.title || "").trim();
  const noticeId = String(item?.notice_id || "").trim();
  if (!title || !noticeId) return null;
  const actionState = item.action_state || {};
  const changeReview = item.change_review || {};
  const workflow = item.workflow || {};
  const qualification = item.qualification || {};
  const gates = Array.isArray(qualification.gates) ? qualification.gates : [];
  const blockedGate = gates.find((gate) => gate?.status === "blocked");
  let action = "查看下一步推进任务";
  if (changeReview.overdue) action = "处理逾期公告变更复核";
  else if (Number(changeReview.pending_count || 0)) action = "复核公告变更影响";
  else if (actionState.decision_sla_status === "overdue") action = "完成超时投标决策";
  else if (actionState.owner_required) action = "认领机会负责人";
  else if (blockedGate?.label) action = `补齐${blockedGate.label}门禁`;
  else if (actionState.due_soon) action = "确认临近截止的投标安排";
  else if (workflow.decision === "pending" && qualification.status === "ready") action = "提交 Go / Hold / No-Go 决策";
  else return null;
  return { noticeId, title, action };
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

async function loadOpportunityChangeImpact(noticeId, affectedOnly = false) {
  const query = affectedOnly ? "?affected_only=true" : "";
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/change-impact${query}`);
  const container = currentOpportunityChangeImpactContainer(noticeId);
  if (!container) return;
  container.dataset.affectedOnly = affectedOnly ? "true" : "false";
  container.innerHTML = renderOpportunityChangeImpact(payload);
  announceBusinessEvent(container.querySelector("[data-visual-component=\"change-impact\"]") || container, "impact");
}

function currentOpportunityChangeImpactContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-change-impact]");
  return container?.dataset.changeImpact === noticeId ? container : null;
}

function renderOpportunityChangeImpact(payload) {
  const round = payload?.current_round;
  if (!round) {
    return `
      <div class="change-wave-empty tt-empty-state">
        <strong>当前版本稳定，没有对象需要复核</strong>
        <span>检测到下一次公告修订后，系统会生成影响路径与负责人行动。</span>
      </div>
    `;
  }
  const counts = round.counts || {};
  const events = Array.isArray(round.events) ? round.events : [];
  const items = Array.isArray(round.items) ? round.items : [];
  const actions = Array.isArray(round.actions) ? round.actions : [];
  const rounds = Array.isArray(payload.rounds) ? payload.rounds : [];
  const affectedOnly = Boolean(payload.affected_only);
  const affectedItems = Array.from(new Map(
    items
      .filter((item) => item.impact_status !== "unaffected")
      .map((item) => [`${item.target_type}:${item.target_id}`, item]),
  ).values());
  const lanes = [
    { type: "requirement", label: "投标要求" },
    { type: "capability_match", label: "企业证据" },
    { type: "readiness", label: "准备度" },
    { type: "workflow_task", label: "任务" },
    { type: "calendar", label: "日历" },
    { type: "decision", label: "决策" },
  ];
  return `
    <section class="change-wave-shell severity-${escapeHtml(round.severity || "normal")}" data-visual-component="change-impact">
      <header class="change-wave-hero">
        <div class="change-wave-pulse" aria-hidden="true"><i></i><i></i><i></i><b>${escapeHtml(round.round_number || 1)}</b></div>
        <div>
          <span class="change-wave-kicker">CHANGE IMPACT · 公告冲击波</span>
          <h4>${escapeHtml(counts.affected || 0)} 项对象受变更影响，${escapeHtml(actions.filter((item) => item.status !== "confirmed").length)} 项行动待确认</h4>
          <p>项目 ${escapeHtml(round.notice_id || "待确认")} · 修订 ${escapeHtml(String(round.revision_id || "").slice(0, 12))} · ${escapeHtml(round.generated_at || "-")} · ${escapeHtml(round.status === "confirmed" ? "本轮已闭环" : "本轮处理中")}</p>
        </div>
        <div class="change-wave-score">
          <strong>${escapeHtml(counts.affected || 0)}</strong>
          <span>受影响对象</span>
          <small>${escapeHtml(actions.filter((item) => item.status !== "confirmed").length)} 项待确认</small>
        </div>
      </header>
      <div class="change-wave-filters">
        ${semanticStateTag("gap", `必须复核 ${counts.mandatory_review || 0}`, "is-critical")}
        ${semanticStateTag("review", `建议复核 ${counts.suggested_review || 0}`, "is-warning")}
        ${semanticStateTag("human", `已确认 ${counts.confirmed || 0}`, "is-confirmed")}
        ${semanticStateTag("verified", `不受影响 ${counts.unaffected || 0}`)}
        <button class="ghost-button" type="button" data-toggle-change-impact="${escapeHtml(round.notice_id)}" data-affected-only="${affectedOnly ? "false" : "true"}">${affectedOnly ? "显示全部" : "仅看受影响"}</button>
      </div>
      <div class="change-wave-diff-grid">
        ${events.map(changeImpactDiffCard).join("")}
      </div>
      <section class="change-wave-path">
        <div class="change-wave-section-title"><strong>影响路径</strong><span>变更 → 要求 → 证据 → 准备度 → 任务 → 日历 → 决策</span></div>
        <div class="change-wave-origin">
          ${events.map((event) => `<span>${escapeHtml(event.change_type_label || event.change_type)}</span>`).join("")}
        </div>
        <div class="change-wave-lanes">
          ${lanes.map((lane) => {
            const laneItems = affectedItems.filter((item) => item.target_type === lane.type);
            return `<div class="change-wave-lane ${laneItems.length ? "is-hit" : ""}"><span>${lane.label}</span><div>${laneItems.length ? laneItems.map((item) => `<b class="impact-${escapeHtml(item.impact_status)}" title="${escapeHtml(item.reason || "")}">${escapeHtml(item.target_title || "待复核")}</b>`).join("") : "<em>本轮未命中</em>"}</div></div>`;
          }).join("")}
        </div>
      </section>
      <section class="change-wave-actions">
        <div class="change-wave-section-title"><strong>核心行动队列</strong><span>确认后才允许同步飞书消息、任务与日历</span></div>
        <div class="change-action-board">
          ${changeActionColumn("必须复核", actions.filter((item) => item.priority === "critical" && item.status !== "confirmed"), "critical")}
          ${changeActionColumn("建议处理", actions.filter((item) => item.priority !== "critical" && item.status !== "confirmed"), "warning")}
          ${changeActionColumn("已确认", actions.filter((item) => item.status === "confirmed"), "confirmed")}
        </div>
        <div class="change-wave-syncbar">
          <span>飞书回执：消息 / 任务 / 日历均保留独立状态、幂等键、失败次数和最近错误</span>
          <button class="primary-lite-button" type="button" data-dispatch-change-impact="${escapeHtml(round.notice_id)}" data-round-id="${escapeHtml(round.id)}" ${actions.some((item) => item.status === "confirmed") ? "" : "disabled"}>同步已确认行动</button>
        </div>
      </section>
      <section class="change-wave-unaffected">
        <div class="change-wave-section-title"><strong>未受影响证明</strong><span>未命中的对象保持原业务状态，不做全量重算</span></div>
        <div>${items.filter((item) => item.impact_status === "unaffected").slice(0, 8).map((item) => `<span><b>${escapeHtml(item.target_title)}</b><small>${escapeHtml(item.reason)}</small></span>`).join("") || "<em>当前筛选未显示未受影响对象</em>"}</div>
      </section>
      <section class="change-wave-timeline">
        <div class="change-wave-section-title"><strong>版本复核时间线</strong><span>每次修订形成独立轮次</span></div>
        <div>${rounds.map((item) => `<span class="${item.id === round.id ? "is-current" : ""}"><b>R${escapeHtml(item.round_number)}</b><strong>${escapeHtml(item.status === "confirmed" ? "已闭环" : "处理中")}</strong><small>${escapeHtml(item.generated_at || "-")}</small></span>`).join("")}</div>
      </section>
    </section>
  `;
}

function changeImpactDiffCard(event) {
  return `
    <article class="change-wave-diff">
      <div><span>${escapeHtml(event.change_type_label || event.change_type)}</span><small>${escapeHtml(event.detection_method === "rule_candidate" ? "规则候选 · 待人工确认" : "结构化规则 · 已确认")}</small></div>
      <p><b>原值</b><span>${escapeHtml(noticeChangeValue(event.old_value))}</span></p>
      <i aria-hidden="true">→</i>
      <p><b>新值</b><span>${escapeHtml(noticeChangeValue(event.new_value))}</span></p>
      <a href="${escapeHtml(event.source_url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(event.source_locator || "查看来源")}</a>
    </article>
  `;
}

function changeActionColumn(label, actions, tone) {
  return `
    <div class="change-action-column tone-${tone}">
      <header><strong>${label}</strong><span>${actions.length}</span></header>
      <div>${actions.length ? actions.map((action) => `
        <article>
          <strong>${escapeHtml(action.title)}</strong>
          <span>${escapeHtml(action.owner_name || "待认领")} · ${escapeHtml(action.due_at || "待定时间")}</span>
          <small>消息 ${escapeHtml(action.message_status)} · 任务 ${escapeHtml(action.task_status)} · 日历 ${escapeHtml(action.calendar_status)}</small>
          ${action.last_error ? `<em>${escapeHtml(action.last_error)} · 可重试</em>` : ""}
          ${action.status !== "confirmed" ? `<button class="ghost-button" type="button" data-confirm-change-impact="${escapeHtml(action.notice_id)}" data-action-id="${escapeHtml(action.id)}">确认此行动</button>` : `<b class="change-action-done">${escapeHtml(action.confirmed_by || "已确认")}</b>`}
        </article>
      `).join("") : "<p>暂无项目</p>"}</div>
    </div>
  `;
}

async function confirmOpportunityChangeImpact(noticeId, actionId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/change-impact/actions/${encodeURIComponent(actionId)}/confirm`, {
    method: "POST",
    body: JSON.stringify({ actor: "web:admin", note: "已核对变更前后值、来源定位与对应行动" }),
  });
  const affectedOnly = currentOpportunityChangeImpactContainer(noticeId)?.dataset.affectedOnly === "true";
  await loadOpportunityChangeImpact(noticeId, affectedOnly);
  showToast("行动已确认，已保留确认人、说明和时间");
}

async function dispatchOpportunityChangeImpact(noticeId, roundId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/change-impact/${encodeURIComponent(roundId)}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ actor: "web:admin" }),
  });
  await loadOpportunityChangeImpact(noticeId, currentOpportunityChangeImpactContainer(noticeId)?.dataset.affectedOnly === "true");
  showToast(result.failed ? `部分同步失败，已保留 ${result.failed} 项等待重试` : "飞书消息、任务和日历已完成幂等同步");
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

async function loadOpportunityBidWorkplan(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan`);
  const container = currentBidWorkplanContainer(noticeId);
  if (!container) return;
  state.opportunityBidWorkplans[noticeId] = payload;
  container.innerHTML = renderBidWorkplan(payload);
}

function currentBidWorkplanContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-bid-workplan]");
  return container?.dataset.bidWorkplan === noticeId ? container : null;
}

function renderBidWorkplan(plan) {
  const summary = plan.summary || {};
  const groups = Array.isArray(plan.requirement_tree) ? plan.requirement_tree : [];
  const requirements = groups.flatMap((group) => group.items || []);
  const requirementById = new Map(requirements.map((item) => [item.id, item]));
  const deliverables = Array.isArray(plan.deliverables) ? plan.deliverables : [];
  const responsibilities = Array.isArray(plan.responsibilities) ? plan.responsibilities : [];
  const tasks = Array.isArray(plan.tasks) ? plan.tasks : [];
  const pricing = Array.isArray(plan.pricing) ? plan.pricing : [];
  const history = Array.isArray(plan.history) ? plan.history : [];
  const gapLabels = {
    material_missing: "材料缺失",
    capability_gap: "能力缺口",
    evidence_insufficient: "证据不足",
    conflict: "冲突待定",
    awaiting_confirmation: "待确认",
  };
  return `
    <div class="bid-workplan-toolbar">
      <div><strong>从文件要求到可执行交付</strong><small>正式任务只在人工确认要求并点击生成后创建</small></div>
      <div>
        <button class="primary-lite-button" type="button" data-build-bid-workplan="${escapeHtml(plan.notice_id)}">生成 / 刷新作战图</button>
        <button class="ghost-button" type="button" data-sync-bid-workplan="${escapeHtml(plan.notice_id)}">同步飞书任务与日历</button>
        <button class="link-button" type="button" data-refresh-bid-task-status="${escapeHtml(plan.notice_id)}">回读完成状态</button>
        <button class="link-button" type="button" data-export-bid-workplan="${escapeHtml(plan.notice_id)}">导出工作包</button>
      </div>
    </div>
    <div class="bid-workplan-kpis">
      ${bidWorkplanKpi("要求", summary.requirement_count || 0, `已确认 ${summary.confirmed_count || 0}`)}
      ${bidWorkplanKpi("交付物", summary.deliverable_count || 0, "同源要求 ID")}
      ${bidWorkplanKpi("执行准备度", `${summary.execution_readiness || 0}%`, `完成 ${summary.completed_task_count || 0}/${summary.task_count || 0}`)}
      ${bidWorkplanKpi("红线", summary.redline_count || 0, "废标 / 截止 / 签章")}
      ${bidWorkplanKpi("报价总额", formatNumber(summary.quoted_total || 0), `毛利率 ${summary.gross_margin || 0}%`)}
    </div>
    <div class="bid-workplan-grid">
      <section class="bid-workplan-panel bid-requirement-tree">
        <header><strong>要求树与来源</strong><span>${escapeHtml(requirements.length)} 项</span></header>
        ${groups.length ? groups.map((group) => `<details open><summary>${escapeHtml(group.label)} <b>${escapeHtml((group.items || []).length)}</b></summary>${(group.items || []).map((item) => `<article><div><strong>${escapeHtml(item.requirement_key)}</strong>${item.mandatory ? "<em>强制</em>" : ""}${Number(item.weight) ? `<span>${escapeHtml(item.weight)} 分</span>` : ""}</div><p>${escapeHtml(item.title)}</p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.source_locator)}</a></article>`).join("")}</details>`).join("") : '<p class="opportunity-requirement-empty">先提取或录入要求，再由负责人确认。</p>'}
      </section>
      <section class="bid-workplan-panel bid-gap-board">
        <header><strong>缺口泳道</strong><span>${escapeHtml(summary.gap_count || 0)} 项</span></header>
        <div class="bid-gap-lanes">${Object.entries(gapLabels).map(([key, label]) => {
          const items = plan.gap_lanes?.[key] || [];
          return `<div class="bid-gap-lane lane-${escapeHtml(key)}"><div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(items.length)}</span></div>${items.length ? items.slice(0, 5).map((item) => `<p><b>${escapeHtml(item.requirement_key)}</b><small>${escapeHtml(item.reason)}</small></p>`).join("") : "<p><small>当前无项目</small></p>"}</div>`;
        }).join("")}</div>
      </section>
      <section class="bid-workplan-panel bid-deliverables">
        <header><strong>交付物清单</strong><span>${escapeHtml(deliverables.length)} 项</span></header>
        ${deliverables.length ? deliverables.map((item) => `<article class="status-${escapeHtml(item.status)}"><div><strong>${escapeHtml(item.deliverable_key)}</strong><span>${escapeHtml(item.status === "completed" ? "已完成" : "待准备")}</span></div><p>${escapeHtml(item.title)}</p><small>${escapeHtml(requirementById.get(item.requirement_id)?.requirement_key || item.requirement_id)} · ${escapeHtml(item.due_at || "截止待确认")}</small></article>`).join("") : '<p class="opportunity-requirement-empty">确认要求并生成作战图后出现。</p>'}
      </section>
      <section class="bid-workplan-panel bid-raci">
        <header><strong>RACI 责任矩阵</strong><span>R执行 A批准 C会签 I知会</span></header>
        ${responsibilities.length ? renderBidRaci(responsibilities, requirementById) : '<p class="opportunity-requirement-empty">尚未生成责任矩阵。</p>'}
      </section>
      <section class="bid-workplan-panel bid-timeline">
        <header><strong>截止倒排与依赖</strong><span>${escapeHtml(tasks.length)} 个节点</span></header>
        ${tasks.length ? tasks.map((task) => `<article class="status-${escapeHtml(task.status)}"><div><span>${escapeHtml(task.due_at ? compactDateTimeText(task.due_at) : "时间待确认")}</span><strong>${escapeHtml(task.title)}</strong></div><small>${escapeHtml(task.task_key)}${task.dependency_keys?.length ? ` · 前置 ${escapeHtml(task.dependency_keys.join("、"))}` : ""}</small>${task.status !== "completed" ? `<button class="link-button" type="button" data-complete-bid-task="${escapeHtml(task.id)}" data-opportunity-id="${escapeHtml(plan.notice_id)}">标记完成</button>` : "<em>已完成</em>"}</article>`).join("") : '<p class="opportunity-requirement-empty">尚未生成倒排计划。</p>'}
      </section>
      <section class="bid-workplan-panel bid-pricing">
        <header><strong>报价计划</strong><span>${escapeHtml(pricing.length)} 项</span></header>
        ${pricing.length ? pricing.map((item) => `<article><div><strong>${escapeHtml(item.item_key)}</strong><span>${escapeHtml(item.status === "approved" ? "已批准" : item.status === "review" ? "待复核" : "草稿")}</span></div><p>${escapeHtml(item.title)}</p><small>${escapeHtml(item.quantity)} ${escapeHtml(item.unit)} × ${formatNumber(item.unit_price)} · 成本 ${formatNumber(item.cost)}</small></article>`).join("") : '<p class="opportunity-requirement-empty">技术或商务要求生成后自动建立报价项。</p>'}
        <form data-bid-pricing-form="${escapeHtml(plan.notice_id)}"><input name="item_key" required placeholder="报价编号" /><input name="title" required placeholder="报价项目" /><input name="quantity" type="number" min="0" step="0.01" value="1" /><input name="unit_price" type="number" min="0" step="0.01" placeholder="单价" /><input name="cost" type="number" min="0" step="0.01" placeholder="成本" /><select name="status"><option value="draft">草稿</option><option value="review">待复核</option><option value="approved">已批准</option></select><button class="primary-lite-button" type="submit">保存报价</button></form>
      </section>
    </div>
    <details class="bid-history"><summary>人工修订记录 · ${escapeHtml(history.length)} 条</summary>${history.slice(0, 12).map((item) => `<p><strong>${escapeHtml(item.action)}</strong><span>${escapeHtml(item.actor)} · ${escapeHtml(compactDateTimeText(item.created_at))}</span></p>`).join("")}</details>
  `;
}

function bidWorkplanKpi(label, value, detail) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></div>`;
}

function renderBidRaci(items, requirementById) {
  const grouped = new Map();
  for (const item of items) {
    if (!grouped.has(item.requirement_id)) grouped.set(item.requirement_id, []);
    grouped.get(item.requirement_id).push(item);
  }
  return `<div class="bid-raci-table">${Array.from(grouped.entries()).map(([requirementId, rows]) => `<div><strong>${escapeHtml(requirementById.get(requirementId)?.requirement_key || requirementId)}</strong>${["R", "A", "C", "I"].map((type) => { const value = rows.find((item) => item.responsibility_type === type); return `<span><b>${type}</b>${escapeHtml(value?.person_label || "待指派")}</span>`; }).join("")}</div>`).join("")}</div>`;
}

async function confirmBidRequirement(noticeId, requirementId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements/${encodeURIComponent(requirementId)}/confirm`, { method: "POST", body: JSON.stringify({ actor: "web:admin" }) });
  await Promise.all([loadOpportunityRequirements(noticeId), loadOpportunityBidWorkplan(noticeId)]);
  showToast("要求已由人工确认，可生成正式交付任务");
}

async function splitBidRequirement(noticeId, requirementId) {
  const raw = window.prompt("请输入拆分后的要求标题，每行一条（至少两条）", "交付物一\n交付物二");
  if (!raw) return;
  const titles = raw.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
  if (titles.length < 2) throw new Error("至少输入两条拆分要求");
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements/${encodeURIComponent(requirementId)}/split`, { method: "POST", body: JSON.stringify({ actor: "web:admin", parts: titles.map((title) => ({ title })) }) });
  await Promise.all([loadOpportunityRequirements(noticeId), loadOpportunityBidWorkplan(noticeId)]);
  showToast("复杂要求已拆分，原要求和来源保留在修订记录中");
}

async function mergeSelectedRequirements(noticeId) {
  const ids = Array.from(currentOpportunityRequirementContainer(noticeId)?.querySelectorAll("[data-requirement-select]:checked") || []).map((input) => input.dataset.requirementSelect);
  if (ids.length < 2) throw new Error("请至少选择两条要求");
  const requirementKey = window.prompt("合并后的要求编号", "MERGED-01");
  const title = window.prompt("合并后的要求标题", "合并要求");
  if (!requirementKey || !title) return;
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/requirements/merge`, { method: "POST", body: JSON.stringify({ requirement_ids: ids, requirement_key: requirementKey, title, actor: "web:admin" }) });
  await Promise.all([loadOpportunityRequirements(noticeId), loadOpportunityBidWorkplan(noticeId)]);
  showToast("要求已合并，原始来源和历史仍可追溯");
}

async function buildBidWorkplan(noticeId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan/build`, { method: "POST", body: JSON.stringify({ actor: "web:admin" }) });
  await loadOpportunityBidWorkplan(noticeId);
  showToast("交付物、责任矩阵和倒排计划已生成");
}

async function completeBidTask(noticeId, taskId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan/tasks/${encodeURIComponent(taskId)}/complete`, { method: "POST", body: JSON.stringify({ actor: "web:admin" }) });
  await loadOpportunityBidWorkplan(noticeId);
  await refreshDigitalTwinCockpit(noticeId);
  showToast("任务完成状态已回流投标准备度");
}

async function syncBidWorkplan(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan/sync-feishu`, { method: "POST" });
  await loadOpportunityBidWorkplan(noticeId);
  showToast(`飞书同步完成：任务 ${result.created_count || 0}，日历 ${result.calendar_created_count || 0}，失败 ${result.failed_count || 0}`);
}

async function refreshBidTaskStatus(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan/sync-task-status`, { method: "POST" });
  await loadOpportunityBidWorkplan(noticeId);
  await refreshDigitalTwinCockpit(noticeId);
  showToast(`已回读 ${result.scanned_count || 0} 个飞书任务，新增完成 ${result.completed_count || 0} 项`);
}

async function saveBidPricing(form) {
  const noticeId = form.dataset.bidPricingForm || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-workplan/pricing`, { method: "POST", body: JSON.stringify({ item_key: values.get("item_key") || "", title: values.get("title") || "", quantity: Number(values.get("quantity") || 0), unit_price: Number(values.get("unit_price") || 0), cost: Number(values.get("cost") || 0), status: values.get("status") || "draft" }) });
  await loadOpportunityBidWorkplan(noticeId);
  showToast("报价项已保存并纳入汇总");
}

async function loadOpportunityWarRoomPlan(noticeId) {
  const workspaceQuery = state.organizationWorkspaceId
    ? `?workspace_id=${encodeURIComponent(state.organizationWorkspaceId)}`
    : "";
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room${workspaceQuery}`);
  const container = currentOpportunityWarRoomPlanContainer(noticeId);
  if (!container) return;
  container.innerHTML = renderOpportunityWarRoomPlan(payload);
  announceBusinessEvent(container, "receipt");
}

function currentOpportunityWarRoomPlanContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-war-room-plan]");
  return container?.dataset.warRoomPlan === noticeId ? container : null;
}

async function loadOpportunityReviewBoard(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board`);
  const container = currentOpportunityReviewBoardContainer(noticeId);
  const opportunity = state.opportunities.find((item) => item.notice_id === noticeId) || {};
  const members = Array.isArray(opportunity.team?.members) ? opportunity.team.members : [];
  if (container) container.innerHTML = renderOpportunityReviewBoard(payload, members);
  refreshOpportunityJourney(noticeId, payload.summary || {});
}

function currentOpportunityReviewBoardContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-requirement-review-board]");
  return container?.dataset.requirementReviewBoard === noticeId ? container : null;
}

function renderOpportunityReviewBoard(payload, members = []) {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const summary = payload.summary || {};
  const opinions = Array.isArray(payload.opinions) ? payload.opinions : [];
  const humanOpinions = Array.isArray(payload.human_opinions) ? payload.human_opinions : [];
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  const actionSummary = payload.action_summary || {};
  const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
  const agentRuns = Array.isArray(payload.agent_runs) ? payload.agent_runs : [];
  const agentRuntime = payload.agent_runtime || {};
  const opinionsByReview = new Map();
  const humanOpinionsByRequirement = new Map();
  const actionsByOpinion = new Map(actions.map((action) => [action.opinion_id, action]));
  opinions.forEach((opinion) => {
    const current = opinionsByReview.get(opinion.review_id) || [];
    current.push(opinion);
    opinionsByReview.set(opinion.review_id, current);
  });
  humanOpinions.forEach((opinion) => {
    const current = humanOpinionsByRequirement.get(opinion.requirement_id) || [];
    current.push(opinion);
    humanOpinionsByRequirement.set(opinion.requirement_id, current);
  });
  return `
    <div class="requirement-review-summary">
      <span>待会审 <strong>${escapeHtml(summary.pending_count || 0)}</strong> 项</span>
      <span>已裁决 <strong>${escapeHtml(summary.resolved_count || 0)}</strong> 项</span>
      ${Number(actionSummary.open_count) ? `<span>待行动 <strong>${escapeHtml(actionSummary.open_count)}</strong> 项</span>` : ""}
      ${Number(actionSummary.unassigned_count) ? `<span class="is-warning">未指定负责人 <strong>${escapeHtml(actionSummary.unassigned_count)}</strong></span>` : ""}
      ${Number(actionSummary.undated_count) ? `<span class="is-warning">未设期限 <strong>${escapeHtml(actionSummary.undated_count)}</strong></span>` : ""}
      <span>会审运行 <strong>${escapeHtml(agentRuntime.run_count || 0)}</strong> 次</span>
      ${Number(agentRuntime.disagreement_count) ? `<span class="is-warning">专业分歧 <strong>${escapeHtml(agentRuntime.disagreement_count)}</strong> 组</span>` : ""}
      ${Number(agentRuntime.failed_role_count) ? `<span class="is-warning">角色待恢复 <strong>${escapeHtml(agentRuntime.failed_role_count)}</strong> 个</span>` : ""}
    </div>
    <div class="requirement-review-list">
      ${items.length ? items.map((item) => requirementReviewCase(item, humanOpinionsByRequirement.get(item.requirement_id) || [], actionsByOpinion, members)).join("") : '<div class="opportunity-requirement-empty">尚无会审项。生成后不会自动改变要求账本结论。</div>'}
    </div>
    ${suggestions.length ? `<section class="review-agent-panel review-opponent-panel" aria-label="可质询多角色会审">
      <div><strong>专业对手盘</strong><small>不按票数制造真相；只合并一致且有证据的事实，分歧必须由人员裁决。</small></div>
      <div class="review-agent-suggestion-list">${suggestions.map((suggestion) => reviewAgentSuggestion(suggestion, opinionsByReview.get(suggestion.review_id) || [])).join("")}</div>
    </section>` : ""}
    ${agentRuns.length ? `<details class="review-agent-runs"><summary>运行记录与恢复点 <span>${escapeHtml(agentRuns.length)} 次</span></summary>${agentRuns.slice(0, 12).map(reviewAgentRunRow).join("")}</details>` : ""}
  `;
}

function reviewAgentSuggestion(suggestion, opinions) {
  const consensusLabel = {
    unanimous: "一致",
    single: "单一意见",
    split: "存在分歧",
  }[suggestion.consensus] || "待判断";
  const hasGuardedEvidence = opinions.some((opinion) => opinion.model_status === "guarded");
  const conflictLabels = { conclusion_conflict: "结论冲突", evidence_conflict: "证据冲突", low_confidence: "低置信度" };
  const conflicts = Array.isArray(suggestion.conflict_types) ? suggestion.conflict_types : [];
  const consensusFacts = Array.isArray(suggestion.consensus_facts) ? suggestion.consensus_facts : [];
  return `
    <article class="review-agent-suggestion ${suggestion.disagreement ? "has-disagreement" : ""} ${hasGuardedEvidence ? "is-evidence-guarded" : ""}">
      <div><strong>${escapeHtml(suggestion.requirement_key || "未命名要求")}</strong><span>${escapeHtml(suggestion.suggestion_label || suggestion.suggestion || "待判断")} · ${escapeHtml(consensusLabel)}</span></div>
      <small>${hasGuardedEvidence ? "证据安全门禁已触发，未调用模型，等待人工核验" : `${escapeHtml(suggestion.opinion_count || 0)} 位 Agent 已给出意见`}</small>
      ${conflicts.length ? `<div class="review-conflict-tags">${conflicts.map((item) => `<span>${escapeHtml(conflictLabels[item] || item)}</span>`).join("")}</div>` : ""}
      ${consensusFacts.length ? `<div class="review-consensus-facts"><strong>一致事实</strong>${consensusFacts.map((fact) => `<p>${escapeHtml(fact.statement || "")}</p>`).join("")}</div>` : ""}
      <div class="review-agent-opinion-list">${opinions.map(reviewAgentOpinionCard).join("")}</div>
    </article>
  `;
}

function reviewAgentOpinionCard(opinion) {
  const evidenceIds = Array.isArray(opinion.evidence_ids) ? opinion.evidence_ids : [];
  const risks = Array.isArray(opinion.risks) ? opinion.risks : [];
  const pending = Array.isArray(opinion.pending_items) ? opinion.pending_items : [];
  const actions = Array.isArray(opinion.recommended_actions) ? opinion.recommended_actions : [];
  return `<article class="review-agent-opinion-card decision-${escapeHtml(opinion.decision || "escalate")}">
    <header><strong>${escapeHtml(opinion.agent_label || opinion.agent_role || "Agent")}</strong><span>${escapeHtml(reviewOpinionModeLabel(opinion))}</span></header>
    <p>${escapeHtml(opinion.rationale || "未提供依据")}</p>
    <div class="review-agent-evidence-ids">${evidenceIds.map((item) => `<code title="${escapeHtml(item)}">${escapeHtml(item)}</code>`).join("") || "<small>证据编号待补</small>"}</div>
    ${risks.length ? `<small><b>风险</b> ${escapeHtml(risks.join("；"))}</small>` : ""}
    ${pending.length ? `<small><b>待确认</b> ${escapeHtml(pending.join("；"))}</small>` : ""}
    ${actions.length ? `<small><b>建议动作</b> ${escapeHtml(actions.join("；"))}</small>` : ""}
    <footer><span>公告版本 ${escapeHtml(opinion.notice_revision_id || "当前快照")} · 第 ${escapeHtml(opinion.attempt_number || 1)} 次</span><button class="evidence-entry-button" type="button" data-open-evidence-microscope="${escapeHtml(opinion.notice_id || "")}" data-evidence-claim-type="agent_opinion" data-evidence-claim-key="${escapeHtml(opinion.id || "")}">打开双方证据</button></footer>
  </article>`;
}

function reviewAgentRunRow(run) {
  const failed = Array.isArray(run.failed_roles) ? run.failed_roles : [];
  return `<article class="review-agent-run status-${escapeHtml(run.status || "running")}"><div><strong>${escapeHtml(run.requirement_key || "要求")}</strong><span>${escapeHtml(run.status || "running")} · ${escapeHtml(run.completed_count || 0)} 完成 / ${escapeHtml(run.failed_count || 0)} 失败</span></div><small>公告版本 ${escapeHtml(run.notice_revision_id || "当前快照")} · 提示版本 ${escapeHtml(run.prompt_version || "-")} · 证据范围 ${escapeHtml(String(run.evidence_scope_hash || "").slice(0, 12))}</small>${failed.map((item) => item.resolved ? `<small>${escapeHtml(item.agent_label || item.agent_role)} 已通过单角色重试恢复</small>` : `<button class="link-button" type="button" data-retry-review-agent="${escapeHtml(run.notice_id)}" data-review-id="${escapeHtml(run.review_id)}" data-agent-role="${escapeHtml(item.agent_role)}">重试 ${escapeHtml(item.agent_label || item.agent_role)}</button>`).join("")}</article>`;
}

function reviewOpinionModeLabel(opinion) {
  if (opinion.model_status === "guarded") return "安全门禁 · 人工核验";
  if (opinion.model_status === "rule_grounded") return `规则证据审阅 · ${opinion.decision_label || opinion.decision || "待判断"} · ${opinion.confidence || 0}%`;
  return `${opinion.decision_label || opinion.decision || "待判断"} · ${opinion.confidence || 0}%`;
}

function requirementReviewCase(item, humanOpinions, actionsByOpinion, members) {
  const resolved = item.status === "resolved";
  return `
    <article class="requirement-review-case status-${escapeHtml(item.status || "pending")}">
      <div><strong>${escapeHtml(item.requirement_key || "未命名要求")}</strong><span>${escapeHtml(item.reviewer_role_label || item.reviewer_role || "会审")}</span></div>
      <small>${escapeHtml(item.reason_label || item.reason || "待人工判断")}</small>
      ${resolved ? `<p>裁决：${escapeHtml(item.decision_label || item.decision || "已完成")} · ${escapeHtml(item.decided_by || "")}${item.decision_note ? ` · ${escapeHtml(item.decision_note)}` : ""}</p>` : `
        <form class="requirement-review-form" data-requirement-review-form="${escapeHtml(item.notice_id)}" data-review-id="${escapeHtml(item.id)}">
          <select name="decision"><option value="accepted">采纳</option><option value="returned">退回修订</option><option value="escalated">升级会审</option></select>
          <input name="actor" required maxlength="80" placeholder="裁决人" />
          <input name="note" required maxlength="500" placeholder="裁决依据（不会覆盖原要求）" />
          <button class="link-button" type="submit">记录裁决</button>
        </form>
      `}
      <div class="human-review-opinion-list">
        ${humanOpinions.length ? humanOpinions.map((opinion) => reviewOpinionActionRow(item, opinion, actionsByOpinion.get(opinion.id), members)).join("") : '<small>暂无协作意见</small>'}
      </div>
      <form class="human-review-opinion-form" data-human-review-opinion-form="${escapeHtml(item.notice_id)}" data-requirement-id="${escapeHtml(item.requirement_id)}">
        <input name="actor" required maxlength="80" placeholder="署名" />
        <input name="content" required maxlength="2000" placeholder="补充证据、风险或判断" />
        <button class="link-button" type="submit">补充意见</button>
      </form>
    </article>
  `;
}

function reviewOpinionActionRow(item, opinion, action, members) {
  const memberOptions = [
    '<option value="">暂不指定负责人</option>',
    ...members.map((member) => `<option value="${escapeHtml(member.id || "")}">${escapeHtml(member.member_name || "未命名成员")}</option>`),
  ].join("");
  const actionState = action
    ? `<div class="review-opinion-action status-${escapeHtml(action.status || "open")}"><strong>${escapeHtml(action.status_label || action.status || "待处理")}</strong><span>${escapeHtml(action.action_note || "")}</span><small>${escapeHtml(action.assignee_name || "未指定负责人")}${action.due_at ? ` · ${escapeHtml(action.due_at)}` : " · 未设期限"}${action.feishu_task_guid ? ` · 飞书${escapeHtml(action.feishu_task_status === "completed" ? "已完成" : "已同步")}` : ""}</small>${action.status === "open" ? `<div class="review-opinion-action-controls">${!action.feishu_task_guid && action.assignee_member_id && action.due_at ? `<button class="link-button" type="button" data-sync-review-opinion-action="${escapeHtml(action.notice_id)}" data-action-id="${escapeHtml(action.id)}">同步飞书任务</button>` : ""}<form class="review-opinion-complete-form" data-review-opinion-complete="${escapeHtml(action.notice_id)}" data-action-id="${escapeHtml(action.id)}"><input name="actor" required maxlength="80" placeholder="完成人" /><input name="completion_note" required maxlength="1000" placeholder="完成依据" /><button class="link-button" type="submit">完成行动</button></form></div>` : `<small>${escapeHtml(action.completed_by || "")} · ${escapeHtml(action.completion_note || "")}</small>`}</div>`
    : `<form class="review-opinion-action-form" data-review-opinion-action="${escapeHtml(item.notice_id)}" data-opinion-id="${escapeHtml(opinion.id)}"><select name="assignee_member_id">${memberOptions}</select><input name="due_at" type="datetime-local" /><input name="action_note" required maxlength="1000" placeholder="明确下一步待处理事项" /><input name="actor" required maxlength="80" placeholder="确认人" /><button class="link-button" type="submit">转为行动</button></form>`;
  return `<div class="review-opinion-row"><p><strong>${escapeHtml(opinion.actor || "协作成员")}</strong><span>${escapeHtml(opinion.channel === "feishu_group" ? "飞书群" : "网页")} · ${escapeHtml(compactDateTimeText(opinion.created_at || ""))}</span><small>${escapeHtml(opinion.content || "")}</small></p>${actionState}</div>`;
}

async function syncOpportunityReviewBoard(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/sync`, { method: "POST" });
  await loadOpportunityReviewBoard(noticeId);
  showToast(`会审队列已生成：新增 ${payload.created_count || 0} 项`);
}

async function runOpportunityReviewAgents(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/agents`, { method: "POST" });
  await loadOpportunityReviewBoard(noticeId);
  if (Number(result.guarded_case_count || 0)) {
    showToast(`证据安全门禁：${result.guarded_case_count} 项已升级人工核验，未调用模型`);
  } else if (result.mode === "multi_agent") {
    showToast(`AI 会审完成：${result.opinion_count || 0} 条独立意见`);
  } else {
    showToast("当前模型未启用，已保留规则会审队列供人工裁决");
  }
}

async function retryOpportunityReviewAgent(noticeId, reviewId, agentRole) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/${encodeURIComponent(reviewId)}/agents/${encodeURIComponent(agentRole)}/retry`, { method: "POST" });
  await loadOpportunityReviewBoard(noticeId);
  showToast(Number(result.failed_count || 0) ? "角色重试仍失败，其他意见已保留" : "角色已恢复，意见和运行记录已更新");
}

async function sendOpportunityReviewBoardToFeishu(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/send-feishu`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: state.organizationWorkspaceId || "" }),
  });
  showToast(
    result.status === "sent"
      ? `会审摘要已同步到飞书群：待裁决 ${result.pending_count || 0} 项`
      : result.reason === "review board has no cases"
        ? "尚无会审项，请先根据要求账本生成队列"
        : "当前会审状态已同步过，无需重复发送",
  );
}

async function resolveOpportunityReviewCase(form) {
  const noticeId = form.dataset.requirementReviewForm || "";
  const reviewId = form.dataset.reviewId || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/${encodeURIComponent(reviewId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      decision: values.get("decision") || "",
      actor: values.get("actor") || "",
      note: values.get("note") || "",
    }),
  });
  await loadOpportunityReviewBoard(noticeId);
  showToast("会审裁决已记录，原要求结论保持不变");
}

async function saveHumanReviewOpinion(form) {
  const noticeId = form.dataset.humanReviewOpinionForm || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/opinions`, {
    method: "POST",
    body: JSON.stringify({
      requirement_id: form.dataset.requirementId || "",
      actor: values.get("actor") || "",
      content: values.get("content") || "",
    }),
  });
  await loadOpportunityReviewBoard(noticeId);
  showToast("会审意见已记录，等待人工裁决");
}

function renderOpportunityWarRoomPlan(plan) {
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const preflight = Array.isArray(plan.preflight) ? plan.preflight : [];
  const journey = Array.isArray(plan.journey) ? plan.journey : [];
  const receipts = Array.isArray(plan.receipts) ? plan.receipts : [];
  const resources = Array.isArray(plan.resources) ? plan.resources : [];
  const requirements = plan.requirements || {};
  const session = plan.session || null;
  const sync = plan.sync || {};
  const changeActions = plan.change_actions || {};
  const launchCount = Number(session?.launch_count || 0);
  const statusLabel = {
    planned: "待启动", started: "协作中", partial: "部分就绪",
    blocked: "预检待补", failed: "需要恢复", archived: "已归档",
  }[session?.status] || (session ? "协作中" : "待启动");
  return `
    <div class="war-room-command-head" data-visual-component="war-room">
      <div>
        <span class="war-room-eyebrow">TEAM EXECUTION SPACE</span>
        <strong>${escapeHtml(plan.preflight_ready_count || 0)} / ${escapeHtml(preflight.length)} 项预检就绪 · ${escapeHtml(statusLabel)}</strong>
        <small>项目 ${escapeHtml(plan.notice_id || "待确认")} · 同一要求编号、同一截止时间；每一步都有回执。</small>
      </div>
      <div class="war-room-live status-${escapeHtml(session?.status || "planned")}">${semanticStateTag(session?.status || "pending", statusLabel)}<small>${launchCount ? `已启动 ${launchCount} 次 · 资源自动复用` : "尚未创建外部资源"}</small></div>
    </div>
    <ol class="war-room-journey" aria-label="战情室完整协作流程">
      ${journey.map((item, index) => `<li class="status-${escapeHtml(item.status || "pending")}"><b>${index + 1}</b><div><strong>${escapeHtml(item.label || "流程步骤")}</strong><small>${escapeHtml(item.detail || "")}</small></div></li>`).join("")}
    </ol>
    <div class="war-room-grid">
      <section class="war-room-preflight-panel">
        <div class="war-room-panel-title"><strong>启动预检</strong><span>${escapeHtml(plan.preflight_ready_count || 0)} / ${escapeHtml(preflight.length)} 就绪</span></div>
        <div class="war-room-preflight-grid">
          ${preflight.map((item) => `<article class="status-${escapeHtml(item.status || "attention")}"><i>${item.status === "ready" ? "✓" : "!"}</i><div><strong>${escapeHtml(item.label || "检查项")}</strong><small>${escapeHtml(item.detail || "")}</small></div></article>`).join("")}
        </div>
      </section>
      <section class="war-room-resource-panel">
        <div class="war-room-panel-title"><strong>协作资源</strong><span>${resources.length} 个真实回执</span></div>
        ${resources.length ? `<div class="war-room-resource-grid">${resources.map(warRoomResourceCard).join("")}</div>` : `<div class="war-room-resource-preview">${steps.slice(0, 4).map((step) => `<span><b>${escapeHtml(step.label || "资源")}</b><small>${escapeHtml(step.status === "ready" ? "启动后创建或复用" : step.detail || "待配置")}</small></span>`).join("")}</div>`}
        <div class="war-room-launch-card">
          <div><strong>${session ? "资源已建立，重复启动将自动复用" : "确认后启动真实团队空间"}</strong><small>强制要求待处理 ${escapeHtml(requirements.task_candidate_count || 0)} 项；启动前不会创建飞书资源。</small></div>
          <button class="war-room-primary-action" type="button" data-launch-war-room="${escapeHtml(plan.notice_id || "")}" ${(plan.launch?.ready || state.organizationWorkspaceId) ? "" : "disabled"}>${session ? "复核并补齐资源" : "确认启动战情室"}<b>→</b></button>
        </div>
      </section>
    </div>
    ${receipts.length ? `<section class="war-room-receipt-panel"><div class="war-room-panel-title"><strong>执行回执</strong><span>成功步骤不会因重试而重建</span></div><div class="war-room-receipt-list">${receipts.map((item) => `<article class="status-${escapeHtml(item.status || "pending")}">${semanticStateTag(item.status || "pending", warRoomReceiptStatus(item.status))}<div><strong>${escapeHtml(item.label || item.step_key || "执行步骤")}</strong><span>第 ${escapeHtml(item.attempt_count || 0)} 次${item.reused ? " · 已复用" : ""}</span><small>${escapeHtml(item.last_error || item.receipt?.detail || "回执已保存")}</small></div>${item.status === "failed" ? `<button type="button" data-retry-war-room-step="${escapeHtml(item.step_key || "")}" data-notice-id="${escapeHtml(plan.notice_id || "")}">仅重试此步</button>` : item.resource_url ? `<a href="${escapeHtml(item.resource_url)}" target="_blank" rel="noreferrer">打开资源</a>` : ""}</article>`).join("")}</div></section>` : ""}
    <section class="war-room-sync-panel">
      <div class="war-room-sync-state">
        <span class="war-room-panel-kicker">状态回流</span>
        <strong>${escapeHtml(sync.listener_status === "running" ? "长连接在线" : "等待连接状态")}</strong>
        <small>最近成功 ${escapeHtml(sync.last_success_at || "尚未启动")} · 最近回写 ${escapeHtml(sync.last_sync_at || "尚未同步")}</small>
        <div><span>待重试 <b>${escapeHtml(sync.retryable_failed_count || 0)}</b></span><span>待确认冲突 <b>${escapeHtml(sync.conflict_count || 0)}</b></span></div>
      </div>
      <div class="war-room-change-state">
        <span class="war-room-panel-kicker">增量变更</span>
        <strong>仅推送受影响行动</strong>
        <small>第 ${escapeHtml(changeActions.round_number || 0)} 轮 · 已确认 ${escapeHtml(changeActions.confirmed_count || 0)} 项 · 待确认 ${escapeHtml(changeActions.pending_count || 0)} 项</small>
        <div><span>失败回执 <b>${escapeHtml(changeActions.failed_count || 0)}</b></span></div>
      </div>
      <div class="war-room-control-actions">
        <button type="button" data-sync-war-room-back="${escapeHtml(plan.notice_id || "")}" ${session ? "" : "disabled"}>回读团队状态</button>
        <button type="button" data-dispatch-war-room-changes="${escapeHtml(plan.notice_id || "")}" ${session && Number(changeActions.confirmed_count) ? "" : "disabled"}>发送已确认变更</button>
        <button type="button" data-archive-war-room="${escapeHtml(plan.notice_id || "")}" ${session && session.workspace_id && session.status !== "archived" ? "" : "disabled"}>归档组织记忆</button>
        <button class="ghost-button" type="button" data-reload-war-room="${escapeHtml(plan.notice_id || "")}">刷新回执</button>
      </div>
    </section>
  `;
}

function warRoomResourceCard(item) {
  const icons = { message: "群", task: "任", calendar: "日", bitable: "表", task_set: "列", review_queue: "审" };
  return `<article><i>${escapeHtml(icons[item.resource_type] || "协")}</i><div><strong>${escapeHtml(item.label || "飞书资源")}</strong><span>${item.reused ? "已复用" : "已创建"}</span><small>${escapeHtml(String(item.resource_id || "").slice(0, 24))}</small></div>${item.resource_url ? `<a href="${escapeHtml(item.resource_url)}" target="_blank" rel="noreferrer">↗</a>` : ""}</article>`;
}

function warRoomReceiptStatus(status) {
  return { completed: "成功", failed: "失败", skipped: "已跳过", blocked: "被阻止", pending: "等待中" }[status] || status || "待处理";
}

async function launchOpportunityWarRoom(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room/launch`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: state.organizationWorkspaceId || "", actor: "项目负责人" }),
  });
  await loadOpportunityWarRoomPlan(noticeId);
  await refreshFeishu();
  showToast(result.status === "started" ? "飞书战情室已启动" : (result.message || "飞书战情室未完全启动"));
}

async function retryOpportunityWarRoomStep(button) {
  const noticeId = button.dataset.noticeId || "";
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room/steps/${encodeURIComponent(button.dataset.retryWarRoomStep || "")}/retry`, { method: "POST", body: JSON.stringify({ actor: "项目负责人" }) });
  await loadOpportunityWarRoomPlan(noticeId);
  showToast("该步骤已单独重试，其他成功资源保持不变");
}

async function syncOpportunityWarRoomBack(noticeId) {
  const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room/sync-back`, { method: "POST", body: JSON.stringify({ actor: "项目负责人" }) });
  await Promise.all([loadOpportunityWarRoomPlan(noticeId), refreshDigitalTwinCockpit(noticeId)]);
  showToast(result.conflict_count ? `已回读状态，${result.conflict_count} 项进入人工确认` : "团队执行状态已回写 TenderTrace");
}

async function dispatchOpportunityWarRoomChanges(noticeId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room/dispatch-changes`, { method: "POST", body: JSON.stringify({ actor: "项目负责人" }) });
  await loadOpportunityWarRoomPlan(noticeId);
  showToast("仅已确认的受影响行动已发送");
}

async function archiveOpportunityWarRoom(noticeId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/war-room/archive`, { method: "POST", body: JSON.stringify({ actor: "项目负责人" }) });
  await loadOpportunityWarRoomPlan(noticeId);
  showToast("战情室记录已归档到当前协作空间的组织记忆");
}

async function loadOpportunityCollaborationNotes(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/collaboration-notes`);
  const container = currentOpportunityCollaborationNotesContainer(noticeId);
  if (container) container.innerHTML = renderOpportunityCollaborationNotes(payload, noticeId);
}

function currentOpportunityCollaborationNotesContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-collaboration-notes]");
  return container?.dataset.collaborationNotes === noticeId ? container : null;
}

function renderOpportunityCollaborationNotes(payload, noticeId) {
  const items = Array.isArray(payload.items) ? payload.items : [];
  return `
    <div class="collaboration-note-list">
      ${items.length ? items.map((item) => `<article class="collaboration-note"><p>${escapeHtml(item.content || "")}</p><small>${escapeHtml(item.actor || "协作成员")} · ${escapeHtml(item.channel === "feishu_group" ? "飞书群" : "网页")} · ${escapeHtml(compactDateTimeText(item.created_at || ""))}</small></article>`).join("") : '<p class="opportunity-requirement-empty">暂无协作意见。可在此记录，也可在飞书群中发送“项目意见 机会编号：内容”。</p>'}
    </div>
    <form class="collaboration-note-form" data-collaboration-note-form="${escapeHtml(noticeId)}">
      <input name="content" required maxlength="2000" placeholder="记录项目判断、客户反馈或会审依据" />
      <input name="actor" required maxlength="120" value="admin" aria-label="记录人" />
      <button class="link-button" type="submit">记录意见</button>
    </form>
  `;
}

async function saveOpportunityCollaborationNote(form) {
  const noticeId = form.dataset.collaborationNoteForm || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/collaboration-notes`, {
    method: "POST",
    body: JSON.stringify({ content: values.get("content") || "", actor: values.get("actor") || "admin", channel: "web" }),
  });
  await loadOpportunityCollaborationNotes(noticeId);
  showToast("协作意见已写入机会审计链");
}

async function createReviewOpinionAction(form) {
  const noticeId = form.dataset.reviewOpinionAction || "";
  const opinionId = form.dataset.opinionId || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/opinions/${encodeURIComponent(opinionId)}/actions`, {
    method: "POST",
    body: JSON.stringify({
      assignee_member_id: values.get("assignee_member_id") || "",
      due_at: values.get("due_at") || "",
      action_note: values.get("action_note") || "",
      actor: values.get("actor") || "",
    }),
  });
  await loadOpportunityReviewBoard(noticeId);
  showToast("会审意见已转为待处理行动");
}

async function completeReviewOpinionAction(form) {
  const noticeId = form.dataset.reviewOpinionComplete || "";
  const actionId = form.dataset.actionId || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/actions/${encodeURIComponent(actionId)}/complete`, {
    method: "POST",
    body: JSON.stringify({
      actor: values.get("actor") || "",
      completion_note: values.get("completion_note") || "",
    }),
  });
  await loadOpportunityReviewBoard(noticeId);
  showToast("会审行动已完成并保留处理依据");
}

async function syncReviewOpinionAction(noticeId, actionId) {
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/review-board/actions/${encodeURIComponent(actionId)}/sync-feishu`, { method: "POST" });
  await loadOpportunityReviewBoard(noticeId);
  showToast("会审行动已同步至飞书要求任务");
}

async function loadOpportunityCapabilityMatches(noticeId) {
  const payload = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/capability-passport`);
  const container = currentOpportunityCapabilityMatchContainer(noticeId);
  if (!container) return;
  container.innerHTML = renderCapabilityMatches(payload, noticeId);
}

function currentOpportunityCapabilityMatchContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-capability-matches]");
  return container?.dataset.capabilityMatches === noticeId ? container : null;
}

function renderCapabilityMatches(payload, noticeId) {
  const summary = payload.summary || {};
  const matrix = Array.isArray(payload.matrix) ? payload.matrix : [];
  const passports = Array.isArray(payload.passports) ? payload.passports : [];
  const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
  const actions = Array.isArray(payload.gap_actions) ? payload.gap_actions : [];
  const cases = Array.isArray(payload.similar_cases) ? payload.similar_cases : [];
  return `
    <div class="capability-match-summary">
      <span>能力护照 <strong>${escapeHtml(summary.passport_count || 0)}</strong></span>
      <span class="is-supported">有据满足 <strong>${escapeHtml(summary.supported_count || 0)}</strong></span>
      <span class="is-warning">明确缺口 <strong>${escapeHtml(summary.gap_count || 0)}</strong></span>
      <span class="is-warning">冲突 / 待复核 <strong>${escapeHtml((summary.conflict_count || 0) + (summary.recheck_count || 0))}</strong></span>
      <span>项目版本快照 <strong>${escapeHtml(summary.confirmed_snapshot_count || 0)}</strong></span>
    </div>
    ${alerts.length ? `<div class="capability-alert-strip">${alerts.map((item) => `<span class="severity-${escapeHtml(item.severity || "中")}"><b>${escapeHtml(item.severity || "中")}</b>${escapeHtml(item.message || "能力证据待检查")}</span>`).join("")}</div>` : ""}
    <div class="capability-passport-cockpit">
      <section class="capability-requirement-tree">
        <header><span>01</span><div><strong>招标要求树</strong><small>原文与定位</small></div></header>
        ${matrix.length ? matrix.map((row) => `<article><span>${escapeHtml(row.requirement?.requirement_key || "REQ")}</span><strong>${escapeHtml(row.requirement?.title || "未命名要求")}</strong><small>${escapeHtml(row.requirement?.source_locator || "定位待补")}</small></article>`).join("") : '<p class="capability-empty">请先确认招标要求</p>'}
      </section>
      <section class="capability-matrix-column">
        <header><span>02</span><div><strong>逐项匹配矩阵</strong><small>规则先行 · 人工定案</small></div></header>
        ${matrix.length ? matrix.map((row) => capabilityMatrixRow(row, noticeId)).join("") : '<p class="capability-empty">暂无匹配结果</p>'}
      </section>
      <section class="capability-passport-column">
        <header><span>03</span><div><strong>企业能力护照</strong><small>六类证据 · 版本留痕</small></div></header>
        ${passports.map((group) => `<details ${group.items?.length ? "open" : ""}><summary>${escapeHtml(group.label || group.type)} <b>${escapeHtml(group.items?.length || 0)}</b></summary>${(group.items || []).map((item) => `<article><strong>${escapeHtml(item.title || "未命名能力")}</strong><small>${escapeHtml(item.applicable_entity || "主体待确认")} · ${escapeHtml(item.product_model || "型号未限定")}</small><small>${escapeHtml((item.regions || []).join("、") || "地区未限定")} · v${escapeHtml(item.version_number || 1)}</small><span class="status-${escapeHtml(item.verification_status || "draft")}">${escapeHtml(item.verification_status_label || item.verification_status)}</span></article>`).join("")}</details>`).join("")}
      </section>
    </div>
    <div class="capability-closure-grid">
      <section><h4>缺口行动闭环</h4>${actions.length ? actions.map((item) => `<article><div><strong>${escapeHtml(item.action_type_label || item.action_type)}</strong><small>${escapeHtml(item.requirement_key)} · ${escapeHtml(item.title)}</small></div><span class="status-${escapeHtml(item.status)}">${item.status === "completed" ? "已完成" : "执行中"}</span>${item.status !== "completed" ? `<form data-capability-gap-complete="${escapeHtml(noticeId)}" data-action-id="${escapeHtml(item.id)}"><input name="actor" required placeholder="完成人"/><input name="note" required placeholder="完成依据"/><button class="link-button" type="submit">完成</button></form>` : ""}</article>`).join("") : '<p class="capability-empty">尚未创建缺口行动</p>'}</section>
      <section><h4>相似案例样本</h4>${cases.length ? cases.map((item) => `<article><div><strong>${escapeHtml(item.project_title || "脱敏案例")}</strong><small>${escapeHtml(item.region || "地区待确认")} · ${escapeHtml(item.product_model || "型号待确认")}</small></div><b>${escapeHtml(item.similarity_score || 0)}</b><small>样本 ${escapeHtml(item.sample_count || 1)} · ${item.result === "won" ? "中标" : "未中标"}</small></article>`).join("") : '<p class="capability-empty">暂无完成结果回流的可比案例</p>'}</section>
    </div>
    ${capabilityEvidenceForm(noticeId)}
  `;
}

function capabilityMatrixRow(row, noticeId) {
  const matches = Array.isArray(row.matches) ? row.matches : [];
  return `<article class="capability-matrix-row verdict-${escapeHtml(row.best_verdict || "needs_evidence")}">
    <div class="capability-matrix-row-title"><strong>${escapeHtml(row.requirement?.requirement_key || "REQ")}</strong><span>${escapeHtml(row.best_verdict_label || "待人工确认")}</span></div>
    ${matches.length ? matches.map((item) => `${capabilityMatchRow(item)}${item.verdict !== "supported" ? capabilityGapActionForm(item, noticeId) : ""}`).join("") : '<p>未找到企业证据，请补充材料或创建缺口行动。</p>'}
  </article>`;
}

function capabilityGapActionForm(item, noticeId) {
  return `<form class="capability-gap-action-form" data-capability-gap-action="${escapeHtml(noticeId)}" data-match-id="${escapeHtml(item.id || "")}">
    <select name="action_type"><option value="supplement_material">补充材料</option><option value="internal_confirmation">内部确认</option><option value="partner_support">伙伴协同</option><option value="abandon_requirement">放弃要求</option></select>
    <input name="actor" required maxlength="80" placeholder="创建人" />
    <button class="link-button" type="submit">转为作战任务</button>
  </form>`;
}

function capabilityMatchRow(item) {
  const decisionReady = item.status === "proposed" || item.status === "recheck";
  return `
    <article class="capability-match-row verdict-${escapeHtml(item.verdict || "needs_evidence")} status-${escapeHtml(item.status || "proposed")}">
      <div class="capability-match-heading">
        <strong>${escapeHtml(item.requirement_key || "要求待确认")}</strong>
        <span>${escapeHtml(item.verdict_label || item.verdict || "待判断")}</span>
        <em>${escapeHtml(item.status_label || item.status || "待确认")}</em>
      </div>
      <div class="capability-match-pair">
        <div><small>招标要求</small><strong>${escapeHtml(item.requirement_title || "未命名要求")}</strong></div>
        <i>对照</i>
        <div><small>企业证据</small><strong>${escapeHtml(item.capability_title || "未关联企业证据")}</strong></div>
      </div>
      <p>${escapeHtml(item.rationale || "尚未形成可审计的判断依据。")}</p>
      <small>建议置信度 ${escapeHtml(item.confidence || 0)}%${item.decided_by ? ` · ${escapeHtml(item.decided_by)}：${escapeHtml(item.decision_note || "已记录")}` : ""}</small>
      <button class="evidence-entry-button" type="button" data-open-evidence-microscope="${escapeHtml(item.notice_id || "")}" data-evidence-claim-type="capability_match" data-evidence-claim-key="${escapeHtml(item.id || "")}">查看对照依据</button>
      ${decisionReady ? `<form class="capability-match-decision-form" data-capability-match-decision="${escapeHtml(item.notice_id)}" data-match-id="${escapeHtml(item.id)}">
        <select name="verdict"><option value="supported">有据满足</option><option value="gap">明确缺口</option><option value="needs_evidence">证据不足</option><option value="conflict">存在冲突</option><option value="pending">待人工确认</option></select>
        <input name="actor" required maxlength="80" placeholder="确认人" />
        <input name="note" required maxlength="500" placeholder="确认依据（保留在审计链）" />
        <button class="link-button" name="accept" value="true" type="submit">确认结论</button>
        <button class="link-button" name="accept" value="false" type="submit">不采纳</button>
      </form>` : ""}
    </article>
  `;
}

function capabilityEvidenceForm(noticeId) {
  return `
    <form class="capability-evidence-form" data-capability-evidence-form="${escapeHtml(noticeId)}">
      <div class="capability-evidence-form-heading"><strong>录入企业能力证据</strong><small>只有“已核验”的资料可进入 AI 对照范围。</small></div>
      <div class="capability-evidence-form-grid">
        <label><span>证据编号</span><input name="capability_key" required maxlength="80" placeholder="例如 CAP-SERVER-01" /></label>
        <label><span>类别</span><select name="capability_type"><option value="product_parameter">产品参数</option><option value="qualification_certificate">资质证书</option><option value="personnel_skill">人员能力</option><option value="delivery_service">交付服务</option><option value="project_case">项目案例</option><option value="partner_authorization">伙伴授权</option></select></label>
        <label class="capability-wide"><span>能力或资料名称</span><input name="title" required maxlength="300" placeholder="例如：服务器产品规格与交付说明" /></label>
        <label class="capability-wide"><span>证据摘录</span><textarea name="evidence_text" required rows="2" maxlength="2000" placeholder="保留规格、资质、案例或交付能力的原文内容"></textarea></label>
        <label><span>证据链接</span><input name="source_url" type="url" required placeholder="https://..." /></label>
        <label><span>原文定位</span><input name="source_locator" required maxlength="300" placeholder="文件名第 2 页，第 3.1 条" /></label>
        <label><span>核验状态</span><select name="verification_status"><option value="draft">待核验</option><option value="verified">已核验</option><option value="expired">已失效</option></select></label>
        <label><span>资料负责人</span><input name="owner" maxlength="80" placeholder="可选" /></label>
        <label><span>适用主体</span><input name="applicable_entity" maxlength="160" placeholder="公司全称" /></label>
        <label><span>产品型号</span><input name="product_model" maxlength="120" placeholder="例如 TT-X100" /></label>
        <label><span>适用地区</span><input name="regions" maxlength="200" placeholder="北京、上海" /></label>
        <label><span>授权范围</span><input name="authorization_scope" maxlength="300" placeholder="项目/产品/地区范围" /></label>
        <label><span>来源文件</span><input name="source_file_name" maxlength="200" placeholder="证书或规格书文件名" /></label>
        <label><span>有效起始</span><input name="valid_from" type="date" /></label>
        <label><span>有效截止</span><input name="valid_until" type="date" /></label>
        <label><span>行业</span><input name="industry" maxlength="100" placeholder="政府、教育、医疗等" /></label>
        <label><span>脱敏样本</span><select name="sample_redacted"><option value="false">否</option><option value="true">是</option></select></label>
      </div>
      <div class="capability-evidence-form-actions"><button class="primary-lite-button" type="submit">保存企业证据</button></div>
    </form>
  `;
}

async function saveCapabilityEvidence(form) {
  const values = new FormData(form);
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    await api("/api/capabilities", {
      method: "POST",
      body: JSON.stringify({
        capability_key: values.get("capability_key") || "",
        title: values.get("title") || "",
        capability_type: values.get("capability_type") || "product_parameter",
        evidence_text: values.get("evidence_text") || "",
        source_url: values.get("source_url") || "",
        source_locator: values.get("source_locator") || "",
        verification_status: values.get("verification_status") || "draft",
        owner: values.get("owner") || "",
        applicable_entity: values.get("applicable_entity") || "",
        product_model: values.get("product_model") || "",
        regions: String(values.get("regions") || "").split(/[、,，]/).map((value) => value.trim()).filter(Boolean),
        authorization_scope: values.get("authorization_scope") || "",
        source_file_name: values.get("source_file_name") || "",
        valid_from: values.get("valid_from") || "",
        valid_until: values.get("valid_until") || "",
        industry: values.get("industry") || "",
        sample_redacted: values.get("sample_redacted") === "true",
        actor: "web:admin",
      }),
    });
    form.reset();
    showToast("企业能力证据已保存；核验后可用于 AI 对照");
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function createCapabilityGapAction(form) {
  const noticeId = form.dataset.capabilityGapAction || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/capability-gap-actions`, { method: "POST", body: JSON.stringify({ match_id: form.dataset.matchId || "", action_type: values.get("action_type") || "supplement_material", actor: values.get("actor") || "" }) });
  await Promise.all([loadOpportunityCapabilityMatches(noticeId), loadOpportunityBidWorkplan(noticeId), refreshDigitalTwinCockpit(noticeId)]);
  showToast("缺口已转为正式作战任务，可继续同步飞书");
}

async function completeCapabilityGapAction(form) {
  const noticeId = form.dataset.capabilityGapComplete || "";
  const values = new FormData(form);
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/capability-gap-actions/${encodeURIComponent(form.dataset.actionId || "")}/complete`, { method: "POST", body: JSON.stringify({ actor: values.get("actor") || "", note: values.get("note") || "" }) });
  await Promise.all([loadOpportunityCapabilityMatches(noticeId), loadOpportunityBidWorkplan(noticeId), refreshDigitalTwinCockpit(noticeId)]);
  showToast("缺口行动已完成，准备度已回流");
}

async function analyzeOpportunityCapabilityMatches(noticeId) {
  const button = el.opportunityDetailContent?.querySelector(`[data-analyze-capability-matches="${CSS.escape(noticeId)}"]`);
  if (button) button.disabled = true;
  try {
    const result = await api(`/api/opportunities/${encodeURIComponent(noticeId)}/capability-matches/analyze`, { method: "POST" });
    await loadOpportunityCapabilityMatches(noticeId);
    showToast(`匹配建议已生成：${result.proposal_count || 0} 条（${result.mode === "ai_assisted" ? "AI 辅助" : "证据优先"}）`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function decideCapabilityMatch(form, submitter) {
  const noticeId = form.dataset.capabilityMatchDecision || "";
  const matchId = form.dataset.matchId || "";
  const values = new FormData(form);
  const submit = submitter || form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    await api(`/api/opportunities/${encodeURIComponent(noticeId)}/capability-matches/${encodeURIComponent(matchId)}/decision`, {
      method: "POST",
      body: JSON.stringify({
        verdict: values.get("verdict") || "needs_evidence",
        actor: values.get("actor") || "",
        note: values.get("note") || "",
        accept: submitter?.value !== "false",
      }),
    });
    await loadOpportunityCapabilityMatches(noticeId);
    showToast("能力匹配结论已写入审计链");
  } finally {
    if (submit) submit.disabled = false;
  }
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
      <button class="link-button" type="button" data-merge-selected-requirements="${escapeHtml(noticeId)}">合并所选</button>
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
        ${requirement.status !== "superseded" ? `<input class="requirement-select" type="checkbox" data-requirement-select="${escapeHtml(requirement.id || "")}" aria-label="选择 ${escapeHtml(requirement.requirement_key || "要求")}" />` : ""}
        <strong>${escapeHtml(requirement.requirement_key || "要求编号待确认")}</strong>
        <span>${escapeHtml(requirement.requirement_type_label || requirement.requirement_type || "类型待确认")}</span>
        ${requirement.mandatory ? '<em>强制项</em>' : ""}
        <button class="evidence-entry-button" type="button" data-open-evidence-microscope="${escapeHtml(requirement.notice_id || "")}" data-evidence-claim-type="requirement" data-evidence-claim-key="${escapeHtml(requirement.requirement_key || "")}">查看依据</button>
        <button class="link-button" type="button" data-edit-opportunity-requirement="${escapeHtml(requirement.id || "")}" data-opportunity-id="${escapeHtml(requirement.notice_id || "")}">编辑</button>
        ${requirement.status === "pending" || requirement.status === "review" ? `<button class="link-button" type="button" data-confirm-bid-requirement="${escapeHtml(requirement.id || "")}" data-opportunity-id="${escapeHtml(requirement.notice_id || "")}">确认</button>` : ""}
        ${requirement.status !== "superseded" ? `<button class="link-button" type="button" data-split-bid-requirement="${escapeHtml(requirement.id || "")}" data-opportunity-id="${escapeHtml(requirement.notice_id || "")}">拆分</button>` : ""}
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
        <label><span>类型</span><select name="requirement_type"><option value="qualification">资格条件</option><option value="deadline">截止时间</option><option value="scoring">评分项</option><option value="disqualification">废标条款</option><option value="attachment">附件清单</option><option value="technical">技术参数</option><option value="commercial">商务条款</option></select></label>
        <label class="requirement-wide"><span>要求概述</span><input name="title" required maxlength="300" placeholder="可执行、可判断的要求描述" /></label>
        <label class="requirement-wide"><span>原文摘录</span><textarea name="evidence_text" required rows="2" maxlength="2000" placeholder="复制对应原文，不以模型概括代替证据"></textarea></label>
        <label><span>原文定位</span><input name="source_locator" required maxlength="300" placeholder="文件名第 3 页，第 2.1 条" /></label>
        <label><span>证据链接</span><input name="source_url" type="url" required value="${escapeHtml(item.source_url || "")}" /></label>
        <label><span>置信度</span><input name="confidence" type="number" min="0" max="100" value="0" /></label>
        <label><span>评分权重</span><input name="weight" type="number" min="0" max="100" step="0.1" value="0" /></label>
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
  for (const field of ["requirement_key", "requirement_type", "title", "evidence_text", "source_url", "source_locator", "confidence", "weight", "status", "assignee_member_id", "due_at", "note"]) {
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
        weight: Number(values.get("weight") || 0),
        status: values.get("status") || "pending",
        assignee_member_id: values.get("assignee_member_id") || "",
        due_at: values.get("due_at") || "",
        note: values.get("note") || "",
        actor: "web:admin",
      }),
    });
    await loadOpportunityRequirements(noticeId);
    await loadOpportunityBidWorkplan(noticeId);
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
  await loadOpportunityBidWorkplan(noticeId);
  showToast(result.status === "needs_manual_input" ? result.message : `规则提取完成：新增或更新 ${result.created_or_updated_count || 0} 项，人工内容保留 ${result.preserved_count || 0} 项`);
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

function renderWorkbenchContext() {
  if (!el.workbenchContext) return;
  const latestReport = state.outbox?.[0];
  const activeSubscriptions = (state.subscriptions || []).filter((item) => item.status === "active");
  const opportunityTotal = Number(state.opportunitySummaryData?.total ?? state.opportunities?.length ?? 0);
  const reportName = latestReport?.name || "尚无报告";
  const reportTime = latestReport?.created_at
    ? `生成于 ${compactDateTimeText(latestReport.created_at)}`
    : "完成一次查询后会保留可下载交付物";
  const reportAction = latestReport
    ? `<a class="context-action" href="${escapeHtml(latestReport.download_url || `/api/outbox/${encodeURIComponent(reportName)}`)}" data-download-outbox-name="${escapeHtml(reportName)}">下载 Word</a>`
    : '<button class="context-action" type="button" data-workbench-view="historyView">查看历史运行</button>';
  const subscriptionDetail = activeSubscriptions.length
    ? `已启用 ${activeSubscriptions.length} 项增量追踪，仅推送新增公告`
    : "尚未启用自动追踪，可按查询结果创建订阅";
  const opportunityDetail = opportunityTotal
    ? `已沉淀 ${opportunityTotal} 条可研判机会，可进入要求账本与会审`
    : "运行后会把可行动公告沉淀为机会、要求账本与会审项";
  el.workbenchContext.innerHTML = `
    <div class="workbench-context-label">当前工作上下文</div>
    <div class="workbench-context-grid">
      <article class="workbench-context-item">
        <span>最近交付</span>
        <strong title="${escapeHtml(reportName)}">${escapeHtml(reportName)}</strong>
        <small>${escapeHtml(reportTime)}</small>
        ${reportAction}
      </article>
      <article class="workbench-context-item">
        <span>自动追踪</span>
        <strong>${activeSubscriptions.length ? `${activeSubscriptions.length} 项订阅已启用` : "尚未启用订阅"}</strong>
        <small>${escapeHtml(subscriptionDetail)}</small>
        <button class="context-action" type="button" data-workbench-view="subscriptionsView">管理订阅</button>
      </article>
      <article class="workbench-context-item">
        <span>协作推进</span>
        <strong>${opportunityTotal ? `${opportunityTotal} 条机会待研判` : "等待首个机会"}</strong>
        <small>${escapeHtml(opportunityDetail)}</small>
        <button class="context-action" type="button" data-workbench-view="opportunityView">打开机会情报</button>
      </article>
    </div>
  `;
  el.workbenchContext.querySelectorAll("[data-workbench-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.workbenchView));
  });
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

function strictMetricValue(report, metric) {
  const recall = report.recall || {};
  if (recall.strict_recall_available) return percent(recall[metric]);
  if (recall.strict_recall_observed) {
    return `观察值 ${percent(recall[metric])}，待完成`;
  }
  return "待标注";
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
  const listener = conversationCommands.listener || {};
  const latestCommand = conversationCommands.last_event;
  const listenerState = listener.running
    ? `长连接运行中${listener.heartbeat_at ? ` · 心跳 ${compactDateTimeText(listener.heartbeat_at)}` : ""}`
    : listener.status === "stale"
      ? "长连接心跳超时，需要重启监听器"
      : listener.status === "failed"
        ? "长连接异常，需要重启监听器"
        : conversationCommands.long_connection_available
          ? "长连接待启动"
          : "长连接不可用";
  const conversationDetail = latestCommand
    ? `${latestCommand.command_kind === "subscription" ? "订阅" : "即时查询"} · ${statusLabel(latestCommand.status)} · ${compactDateTimeText(latestCommand.updated_at)}`
    : `${listenerState} · HTTP 回调${conversationCommands.webhook_ready ? "已就绪" : "待配置"}`;
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
    [
      "独立智能体应用（可选）",
      features.agent_service,
      features.agent_service?.detail || "未启用；不影响现有飞书协作功能",
    ],
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
  const region = bidql.region?.city || bidql.region?.province || bidql.region?.aliases?.[0] || "未识别区域";
  const topics = bidql.topic?.core?.length ? bidql.topic.core.join(" / ") : "全部主题";
  const time = bidql.time?.resolved_window
    ? `${bidql.time.resolved_window.from} 至 ${bidql.time.resolved_window.to}`
    : bidql.time?.kind || "默认时间";
  const schedule = bidql.schedule?.kind === "immediate" ? "立即执行" : bidql.schedule?.time || bidql.schedule?.kind;
  const clarifications = clarificationQuestions(bidql);
  const confirmed = state.intentConfirmation.confirmed && state.intentConfirmation.query === bidql.query;
  el.intentPreview.className = `intent-preview${clarifications.length ? " needs-clarification" : ""}`;
  el.intentPreview.innerHTML = `
    <span>区域：${escapeHtml(region)}</span>
    <span>主题：${escapeHtml(topics)}</span>
    <span>时间：${escapeHtml(time)}</span>
    <span>计划：${escapeHtml(schedule)}</span>
    ${
      clarifications.length && !confirmed
        ? intentClarificationHtml(clarifications)
        : clarifications.length
          ? '<span class="clarify-chip is-confirmed">已按当前解析确认</span>'
        : ""
    }
  `;
}

function intentClarificationHtml(clarifications) {
  const candidateText = clarifications
    .flatMap((item) => Array.isArray(item.candidates) ? item.candidates : [])
    .map((candidate) => String(candidate).trim())
    .filter(Boolean)
    .join(" / ");
  return `
    <div class="intent-clarification" role="status">
      <span class="clarify-chip">需确认：${escapeHtml(clarifications.map((item) => item.question).join("；"))}</span>
      ${candidateText ? `<small>当前候选：${escapeHtml(candidateText)}</small>` : ""}
      <div class="intent-clarification-actions">
        <button class="link-button" type="button" data-confirm-intent>按当前范围继续</button>
        <button class="ghost-button" type="button" data-edit-intent>补充需求</button>
      </div>
    </div>
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
  if (state.intentConfirmation.confirmed && state.intentConfirmation.query === query) return true;
  state.intentConfirmation = { query, confirmed: false };
  renderIntentPreview(bidql);
  showToast("请先确认当前解析范围，或补充主题和地区");
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
  renderOrganizationReportDelivery(
    state.organizationWorkspaces.find((item) => item.id === state.organizationWorkspaceId),
  );
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

function openGoldAnnotationDialog(caseId) {
  const item = (state.evaluation?.gold?.cases || []).find((value) => value.id === caseId);
  if (!item) throw new Error("金标用例不存在或已刷新");
  state.goldAnnotationCaseId = caseId;
  el.goldAnnotationForm?.reset();
  if (el.goldAnnotationCase) {
    el.goldAnnotationCase.textContent = `${item.id} · ${item.query}`;
  }
  if (el.goldAnnotationReviewer) {
    el.goldAnnotationReviewer.value = el.userLabel?.textContent?.trim() || "admin";
  }
  el.goldAnnotationDialog?.showModal();
}

function closeGoldAnnotationDialog() {
  el.goldAnnotationDialog?.close();
  state.goldAnnotationCaseId = "";
}

async function submitGoldAnnotation(event) {
  event.preventDefault();
  const caseId = state.goldAnnotationCaseId;
  if (!caseId) throw new Error("请先选择金标用例");
  const body = {
    reviewer: el.goldAnnotationReviewer?.value.trim() || "",
    note: el.goldAnnotationNote?.value.trim() || "",
    notice: {
      source_site: el.goldAnnotationSourceSite?.value.trim() || "",
      notice_id: el.goldAnnotationNoticeId?.value.trim() || "",
      title: el.goldAnnotationTitleInput?.value.trim() || "",
      publish_time: el.goldAnnotationPublishTime?.value.trim() || "",
      source_url: el.goldAnnotationSourceUrl?.value.trim() || "",
    },
  };
  const result = await api(
    `/api/evaluations/gold/cases/${encodeURIComponent(caseId)}/notices`,
    { method: "POST", body: JSON.stringify(body) },
  );
  state.evaluation = result.evaluation;
  renderEvaluation(state.evaluation);
  closeGoldAnnotationDialog();
  showToast(result.annotation?.status === "unchanged" ? "该来源已在金标中" : "人工金标已记录，严格指标已重算");
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
  if (
    state.pendingOpportunityId
    && document.getElementById("opportunityView")?.classList.contains("active")
  ) {
    await openRequestedOpportunity();
  }
  return payload;
}

async function openRequestedOpportunity() {
  const noticeId = state.pendingOpportunityId;
  if (!noticeId) return;
  try {
    const item = await api(`/api/opportunities/${encodeURIComponent(noticeId)}`);
    const index = state.opportunities.findIndex((value) => value.notice_id === noticeId);
    if (index >= 0) state.opportunities[index] = item;
    else state.opportunities.unshift(item);
    state.pendingOpportunityId = "";
    const query = new URLSearchParams(window.location.search);
    query.delete("opportunity");
    const suffix = query.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}${window.location.hash}`);
    openOpportunityDetail(noticeId);
  } catch (error) {
    state.pendingOpportunityId = "";
    showToast(`无法打开飞书关联机会：${error.message}`);
  }
}

function opportunityPageSize() {
  return window.innerWidth <= 700 ? 6 : 20;
}

function liveChallengeStatusText(status) {
  return ({
    local_ready: "本地证据已就绪",
    local_empty: "本地暂无匹配",
    supplementing: "联网补充中",
    completed: "联网补充完成",
    completed_with_errors: "部分来源受限",
    cancelled: "已停止联网补充",
    failed: "联网补充失败",
  })[status] || status || "等待挑战";
}

function liveChallengeSourceText(status) {
  return ({
    available: "可用",
    restricted: "暂不可访问",
    not_applicable: "本次不适用",
  })[status] || "未知";
}

function updateChallengeNetworkState() {
  const online = navigator.onLine;
  if (el.challengeNetworkDot) el.challengeNetworkDot.classList.toggle("is-offline", !online);
  if (el.challengeNetworkState) el.challengeNetworkState.textContent = online ? "在线，可选联网补充" : "离线，本地证据可用";
  if (el.challengeSupplementButton && state.liveChallenge?.status !== "supplementing") {
    el.challengeSupplementButton.disabled = !online || !state.liveChallenge;
  }
}

function renderLiveChallenge(payload) {
  state.liveChallenge = payload;
  const results = payload?.results || [];
  const sources = payload?.source_summary || [];
  const restrictedCount = sources.filter((item) => item.status === "restricted").length;
  const isSupplementing = payload?.status === "supplementing";
  const dataAsOf = results.map((item) => item.indexed_at || item.recorded_at || "").filter(Boolean).sort().pop() || payload?.created_at || "";
  if (el.challengeSupplementButton) el.challengeSupplementButton.disabled = !payload || isSupplementing || !navigator.onLine;
  if (el.challengeCancelButton) el.challengeCancelButton.hidden = !isSupplementing;
  if (el.challengeRunButton) el.challengeRunButton.disabled = isSupplementing;
  if (!el.challengeStage) return;

  const statusWarning = ["completed_with_errors", "cancelled", "failed", "local_empty"].includes(payload?.status);
  const cards = results.length
    ? results.map((item, index) => `
      <article class="challenge-result-card">
        <span class="challenge-result-rank">${String(index + 1).padStart(2, "0")}</span>
        <div>
          <div class="challenge-result-meta">
            <span class="challenge-proof-badge ${item.origin === "online" ? "is-network" : ""}">${item.origin === "online" ? "联网新增 · 待核验" : "本地已验证"}</span>
            <span>${escapeHtml(item.source_site || "未知来源")}</span>
            <span>${escapeHtml(item.publish_time || "日期未披露")}</span>
          </div>
          <h3>${escapeHtml(item.title || "未命名公告")}</h3>
          <p>${escapeHtml(item.region || "地区未披露")} · ${escapeHtml(item.purchaser || "采购人未披露")} · 索引时间 ${escapeHtml(compactDateTimeText(item.indexed_at) || "本次联网")}</p>
        </div>
        <div class="challenge-result-actions">
          ${item.source_url ? `<a class="ghost-button" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">打开原文</a>` : ""}
          <button class="text-link" type="button" data-challenge-opportunity="${escapeHtml(item.notice_id)}">数字档案</button>
        </div>
      </article>`).join("")
    : `<div class="challenge-empty"><strong>本地暂无匹配结果</strong><p>查询记录已经保存。可以调整条件，或在联网状态下尝试补充公开来源。</p></div>`;

  el.challengeStage.innerHTML = `
    <header class="challenge-result-head">
      <div><span class="workspace-eyebrow">LIVE RESULT / ${escapeHtml(payload.id?.slice(0, 8) || "")}</span><h2>${escapeHtml(payload.normalized_query || "现场挑战")}</h2><p>所有结果来自本地索引或本次公开来源采集，不使用随机演示数据。</p></div>
      <span class="challenge-result-mode">${escapeHtml(liveChallengeStatusText(payload.status))}</span>
    </header>
    <div class="challenge-metrics">
      <div class="challenge-metric"><span>本地结果</span><strong>${Number(payload.local_result_count || 0)}</strong></div>
      <div class="challenge-metric"><span>本地响应</span><strong>${Number(payload.local_duration_ms || 0)} ms</strong></div>
      <div class="challenge-metric"><span>联网新增</span><strong>${Number(payload.online_result_count || 0)}</strong></div>
      <div class="challenge-metric"><span>数据时间</span><strong>${escapeHtml(compactDateTimeText(dataAsOf) || "刚刚")}</strong></div>
    </div>
    <p class="challenge-status-note ${statusWarning ? "is-warning" : ""}">${escapeHtml(payload.error_text || (isSupplementing ? "本地结果保持可用，正在并行补充公开来源。" : restrictedCount ? `${restrictedCount} 个来源暂不可访问，本地结果不受影响。` : "本地证据已经就绪；联网补充是可选动作。"))}</p>
    <div class="challenge-result-list">${cards}</div>`;
  renderLiveChallengeSources(sources);
  updateChallengeNetworkState();
}

function renderLiveChallengeSources(sources) {
  if (!el.challengeSourceList) return;
  if (!sources?.length) {
    el.challengeSourceList.className = "challenge-source-list empty-state";
    el.challengeSourceList.textContent = "暂无来源状态";
    return;
  }
  el.challengeSourceList.className = "challenge-source-list";
  el.challengeSourceList.innerHTML = sources.map((item) => `
    <article class="challenge-source-row">
      <div><strong>${escapeHtml(item.label || item.source || "来源")}</strong><span>${escapeHtml(item.detail || "")} · ${Number(item.count || 0)} 条</span></div>
      <em class="challenge-source-state ${item.status === "restricted" ? "is-restricted" : item.status === "not_applicable" ? "is-na" : ""}">${escapeHtml(liveChallengeSourceText(item.status))}</em>
    </article>`).join("");
}

function renderLiveChallengeHistory(items) {
  if (!el.challengeHistory) return;
  if (!items?.length) {
    el.challengeHistory.className = "challenge-history empty-state";
    el.challengeHistory.textContent = "暂无挑战记录";
    return;
  }
  el.challengeHistory.className = "challenge-history";
  el.challengeHistory.innerHTML = items.map((item) => `
    <article class="challenge-history-row">
      <div><strong>${escapeHtml(item.category)} · ${escapeHtml(item.region)}</strong><span>${escapeHtml(item.time_window_label)} · ${escapeHtml(liveChallengeStatusText(item.status))} · ${Number(item.result_count || 0)} 条 · ${escapeHtml(compactDateTimeText(item.created_at))}</span></div>
      <button class="text-link" type="button" data-load-live-challenge="${escapeHtml(item.id)}">打开记录</button>
    </article>`).join("");
}

async function refreshLiveChallengeHistory({ loadLatest = false } = {}) {
  const payload = await api("/api/live-challenges?limit=20");
  state.liveChallengeHistory = payload.items || [];
  renderLiveChallengeHistory(state.liveChallengeHistory);
  if (loadLatest && state.liveChallengeHistory[0]) await loadLiveChallenge(state.liveChallengeHistory[0].id);
}

async function loadLiveChallenge(sessionId) {
  const payload = await api(`/api/live-challenges/${encodeURIComponent(sessionId)}`);
  renderLiveChallenge(payload);
  if (payload.status === "supplementing") scheduleLiveChallengePoll(sessionId);
  return payload;
}

async function startLiveChallenge(event) {
  event.preventDefault();
  const body = {
    category: el.challengeCategory?.value.trim() || "",
    region: el.challengeRegion?.value.trim() || "",
    time_window: el.challengeTimeWindow?.value || "90d",
    keyword: el.challengeKeyword?.value.trim() || "",
    actor: el.userLabel?.textContent?.trim() || "judge",
    max_results: 12,
  };
  if (el.challengeRunButton) el.challengeRunButton.disabled = true;
  try {
    const payload = await api("/api/live-challenges", { method: "POST", body: JSON.stringify(body) });
    renderLiveChallenge(payload);
    await refreshLiveChallengeHistory();
    showToast(`本地挑战完成：${payload.local_result_count || 0} 条，${payload.local_duration_ms || 0} ms`);
  } finally {
    if (el.challengeRunButton && state.liveChallenge?.status !== "supplementing") el.challengeRunButton.disabled = false;
  }
}

async function supplementLiveChallenge() {
  const sessionId = state.liveChallenge?.id;
  if (!sessionId) throw new Error("请先完成一次本地挑战");
  if (!navigator.onLine) throw new Error("当前离线，本地证据仍可使用");
  const payload = await api(`/api/live-challenges/${encodeURIComponent(sessionId)}/supplement`, { method: "POST", body: "{}" });
  renderLiveChallenge(payload);
  scheduleLiveChallengePoll(sessionId);
}

function scheduleLiveChallengePoll(sessionId) {
  if (state.liveChallengePollTimer) window.clearTimeout(state.liveChallengePollTimer);
  state.liveChallengePollTimer = window.setTimeout(async () => {
    try {
      const payload = await loadLiveChallenge(sessionId);
      if (payload.status === "supplementing") scheduleLiveChallengePoll(sessionId);
      else {
        state.liveChallengePollTimer = null;
        await refreshLiveChallengeHistory();
      }
    } catch (error) {
      state.liveChallengePollTimer = null;
      toastError("联网状态读取失败")(error);
    }
  }, 900);
}

async function cancelLiveChallenge() {
  const sessionId = state.liveChallenge?.id;
  if (!sessionId) return;
  if (state.liveChallengePollTimer) window.clearTimeout(state.liveChallengePollTimer);
  state.liveChallengePollTimer = null;
  const payload = await api(`/api/live-challenges/${encodeURIComponent(sessionId)}/cancel`, { method: "POST", body: "{}" });
  renderLiveChallenge(payload);
  await refreshLiveChallengeHistory();
}

async function copyLiveChallengeLink() {
  const url = `${window.location.origin}${window.location.pathname}?view=challengeView`;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
  } else {
    const input = document.createElement("textarea");
    input.value = url;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  showToast("评委挑战入口已复制");
}

function demoRoleText(role) {
  return ({ main: "主案例", backup: "备选案例", replay: "回放案例" })[role] || role || "案例";
}

function demoModeText(mode) {
  return ({ live: "实时动作", verified_history: "已验证历史", replay: "同版本真实回放" })[mode] || mode || "未选择";
}

function demoStatusText(status) {
  return ({ ready: "就绪", attention: "需关注", blocked: "阻断", client_check: "浏览器检查", passed: "通过", failed: "失败", not_checked: "未检查" })[status] || status || "未知";
}

function renderDemoReliability(payload) {
  state.demoReliability = payload;
  const summary = payload?.summary || {};
  const environment = payload?.environment || {};
  if (el.demoConsoleOverall) {
    const ready = payload?.status === "ready";
    el.demoConsoleOverall.className = `demo-overall-state ${ready ? "is-ready" : environment.critical_ready ? "is-checking" : "is-blocked"}`;
    el.demoConsoleOverall.innerHTML = `<i></i><div><small>现场状态</small><strong>${escapeHtml(ready ? "可靠性就绪" : environment.critical_ready ? "案例待准备" : "核心检查未通过")}</strong></div>`;
  }
  if (el.demoConsoleMetrics) {
    el.demoConsoleMetrics.className = "demo-console-metrics";
    el.demoConsoleMetrics.innerHTML = [
      [summary.case_count || 0, "冻结案例", "主 / 备 / 回放"],
      [summary.verified_replay_count || 0, "已验证回放", "同版本哈希校验"],
      [summary.rehearsal_count || 0, "全流程演练", summary.consecutive_passes ? "最近三次连续通过" : "尚未连续三次通过"],
      [summary.layout_profiles_passed || 0, "投屏尺寸", "目标 2 种"],
      [environment.critical_ready ? "通过" : "阻断", "核心预检", compactDateTimeText(environment.checked_at) || "刚刚"],
    ].map(([value, label, note]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  }
  renderDemoEnvironment(environment);
  renderDemoLayoutAudits(payload?.layout_audits || []);
  renderDemoCases(payload?.cases || []);
  renderDemoRehearsalLog(payload?.rehearsals || []);
}

function renderDemoEnvironment(environment) {
  if (el.demoEnvironmentTime) el.demoEnvironmentTime.textContent = compactDateTimeText(environment?.checked_at) || "刚刚";
  if (!el.demoEnvironmentChecks) return;
  const checks = environment?.checks || [];
  if (!checks.length) {
    el.demoEnvironmentChecks.className = "demo-check-grid empty-state";
    el.demoEnvironmentChecks.textContent = "暂无预检结果";
    return;
  }
  el.demoEnvironmentChecks.className = "demo-check-grid";
  el.demoEnvironmentChecks.innerHTML = checks.map((item) => `
    <article class="demo-check-card is-${escapeHtml(item.status)}">
      <i>${item.status === "ready" ? "✓" : item.status === "blocked" ? "×" : "!"}</i>
      <div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.detail)}</span></div>
    </article>`).join("");
}

function renderDemoLayoutAudits(items) {
  if (!el.demoLayoutAudits) return;
  if (!items?.length) {
    el.demoLayoutAudits.className = "demo-layout-audits empty-state";
    el.demoLayoutAudits.textContent = "尚未检查";
    return;
  }
  el.demoLayoutAudits.className = "demo-layout-audits";
  el.demoLayoutAudits.innerHTML = items.map((item) => `
    <article class="demo-layout-card">
      <b>${escapeHtml(item.profile === "projector_1440" ? "PROJECTOR" : "FULL HD")}</b>
      <div><strong>${Number(item.viewport_width)} × ${Number(item.viewport_height)}</strong><span>${item.created_at ? `实测 ${escapeHtml(compactDateTimeText(item.created_at))}` : "等待同源浏览器实测"}${item.scroll_width ? ` · 页面宽 ${Number(item.scroll_width)}` : ""}</span></div>
      <em class="demo-layout-state is-${escapeHtml(item.status)}">${escapeHtml(demoStatusText(item.status))}</em>
    </article>`).join("");
}

function renderDemoCases(cases) {
  if (!el.demoCaseGrid) return;
  if (!cases?.length) {
    el.demoCaseGrid.className = "demo-case-grid empty-state";
    el.demoCaseGrid.textContent = "尚未准备案例；点击“从真实记录准备案例”后，系统只从已有数据库记录冻结。";
    return;
  }
  el.demoCaseGrid.className = "demo-case-grid";
  el.demoCaseGrid.innerHTML = cases.map((item) => `
    <article class="demo-case-card role-${escapeHtml(item.role)}">
      <header><span class="demo-case-role">${escapeHtml(demoRoleText(item.role))}</span><span class="demo-case-integrity ${item.snapshot_verified && item.replay_verified ? "" : "is-failed"}">${item.snapshot_verified && item.replay_verified ? "✓ 快照与回放一致" : "× 完整性失败"}</span></header>
      <h3>${escapeHtml(item.label)}</h3>
      <span class="demo-case-kind ${item.evidence_kind === "controlled_fixture" ? "is-fixture" : ""}">${item.evidence_kind === "controlled_fixture" ? "受控演练数据（明确标识）" : "公开来源真实记录"}</span>
      <div class="demo-case-meta"><span>数据时间 ${escapeHtml(compactDateTimeText(item.data_as_of) || item.data_as_of || "未知")}</span><span>版本 ${escapeHtml(String(item.source_version || "").slice(0, 14))}</span><span>校验 ${escapeHtml(String(item.snapshot_hash || "").slice(0, 14))}</span></div>
      <div class="demo-case-actions">
        <button type="button" data-demo-case-id="${escapeHtml(item.id)}" data-demo-mode="live">实时打开</button>
        <button type="button" data-demo-case-id="${escapeHtml(item.id)}" data-demo-mode="verified_history">验证历史</button>
        <button type="button" data-demo-case-id="${escapeHtml(item.id)}" data-demo-mode="replay">真实回放</button>
      </div>
    </article>`).join("");
}

function renderDemoRehearsal(result) {
  state.demoActiveRehearsal = result;
  if (!el.demoStage) return;
  const rehearsal = result?.rehearsal || {};
  const display = result?.display || {};
  const events = rehearsal.events || [];
  const metrics = display.metrics || [];
  const items = display.items || [];
  const links = (display.action_links || []).filter((item) => {
    const url = String(item.url || "");
    return url.startsWith("/") || url.startsWith("http://") || url.startsWith("https://");
  });
  el.demoStage.innerHTML = `
    <header class="demo-stage-head">
      <div><span class="workspace-eyebrow">REHEARSAL / ${escapeHtml(String(rehearsal.id || "").slice(0, 8))}</span><h2>${escapeHtml(display.title || result?.case?.label || "演示案例")}</h2><p>数据时间 ${escapeHtml(compactDateTimeText(display.data_as_of) || display.data_as_of || "未知")} · ${display.evidence_kind === "controlled_fixture" ? "受控演练数据" : "公开来源真实记录"} · 打开 ${Number(rehearsal.opened_in_ms || 0)} ms</p></div>
      <span class="demo-mode-badge mode-${escapeHtml(rehearsal.actual_mode)}">${escapeHtml(demoModeText(rehearsal.actual_mode))}</span>
    </header>
    ${rehearsal.switch_reason ? `<p class="demo-switch-reason"><strong>切换原因：</strong>${escapeHtml(rehearsal.switch_reason)}</p>` : ""}
    <div class="demo-stage-metrics">${metrics.map((item) => `<article><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`).join("")}</div>
    <div class="demo-stage-body">
      <div>
        <div class="demo-section-head"><div><strong>案例证据摘要</strong><span>回放内容来自冻结时真实数据库结果</span></div></div>
        <div class="demo-display-items">${items.length ? items.map((item, index) => `<article class="demo-display-item"><i>${String(index + 1).padStart(2, "0")}</i><div><strong>${escapeHtml(item.title || "证据项")}</strong><span>${escapeHtml(item.meta || item.status || "")}</span></div>${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">原文</a>` : ""}</article>`).join("") : '<div class="empty-state">当前快照没有摘要项</div>'}</div>
        <div class="demo-stage-actions">${links.map((item) => `<a class="ghost-button" href="${escapeHtml(item.url)}" ${String(item.url).startsWith("http") ? 'target="_blank" rel="noreferrer"' : ""}>${escapeHtml(item.label || "打开")}</a>`).join("")}</div>
      </div>
      <div>
        <div class="demo-section-head"><div><strong>逐步回执</strong><span>五个步骤分别计时</span></div></div>
        <div class="demo-event-list">${events.map((item) => `<article class="demo-event-row"><i>${item.status === "passed" ? "✓" : "×"}</i><div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.detail)}</span></div><em>${Number(item.duration_ms || 0)} ms</em></article>`).join("")}</div>
      </div>
    </div>`;
}

function renderDemoRehearsalLog(items) {
  if (!el.demoRehearsalLog) return;
  if (!items?.length) {
    el.demoRehearsalLog.className = "demo-rehearsal-log empty-state";
    el.demoRehearsalLog.textContent = "暂无演练记录";
    return;
  }
  const caseMap = new Map((state.demoReliability?.cases || []).map((item) => [item.id, item]));
  el.demoRehearsalLog.className = "demo-rehearsal-log";
  el.demoRehearsalLog.innerHTML = items.map((item) => {
    const demoCase = caseMap.get(item.case_id) || {};
    return `<article class="demo-log-row"><div><strong>${escapeHtml(demoRoleText(demoCase.role))}</strong><span>${escapeHtml(compactDateTimeText(item.started_at))}</span></div><div><strong>${escapeHtml(demoCase.label || item.case_id)}</strong><span>${escapeHtml(item.switch_reason || `${demoModeText(item.requested_mode)} → ${demoModeText(item.actual_mode)}`)}</span></div><b>${escapeHtml(demoModeText(item.actual_mode))}</b><em class="${item.status === "failed" ? "is-failed" : ""}">${escapeHtml(demoStatusText(item.status))}</em><small>${Number(item.opened_in_ms || 0)} ms</small></article>`;
  }).join("");
}

async function refreshDemoReliability() {
  const payload = await api("/api/demo-reliability");
  renderDemoReliability(payload);
  return payload;
}

async function prepareDemoReliability() {
  if (el.demoPrepareButton) el.demoPrepareButton.disabled = true;
  try {
    const payload = await api("/api/demo-reliability/prepare", {
      method: "POST",
      body: JSON.stringify({ actor: el.userLabel?.textContent?.trim() || "admin" }),
    });
    renderDemoReliability(payload.overview);
    showToast("主案例、备选案例和真实回放已从现有记录冻结");
  } finally {
    if (el.demoPrepareButton) el.demoPrepareButton.disabled = false;
  }
}

async function runDemoRehearsal(caseId, mode = "live", options = {}) {
  const profile = options.profile || "projector_1440";
  const dimensions = profile === "full_hd_1920" ? [1920, 1080] : [1440, 900];
  const payload = await api("/api/demo-reliability/rehearsals", {
    method: "POST",
    body: JSON.stringify({
      case_id: caseId,
      requested_mode: mode,
      browser_online: options.browserOnline ?? navigator.onLine,
      viewport_width: dimensions[0],
      viewport_height: dimensions[1],
      scenario: options.scenario || "manual",
      actor: el.userLabel?.textContent?.trim() || "judge",
    }),
  });
  renderDemoRehearsal(payload);
  await refreshDemoReliability();
  return payload;
}

async function runThreeDemoRehearsals() {
  const cases = state.demoReliability?.cases || [];
  if (cases.length < 3) throw new Error("请先从真实记录准备三个案例");
  if (el.demoRunThreeButton) {
    el.demoRunThreeButton.disabled = true;
    el.demoRunThreeButton.textContent = "正在执行 1 / 3";
  }
  const plan = [
    { demoCase: cases.find((item) => item.role === "main"), mode: "live", profile: "projector_1440", browserOnline: navigator.onLine, scenario: "main_live" },
    { demoCase: cases.find((item) => item.role === "backup"), mode: "verified_history", profile: "full_hd_1920", browserOnline: navigator.onLine, scenario: "backup_history" },
    { demoCase: cases.find((item) => item.role === "replay"), mode: "live", profile: "projector_1440", browserOnline: false, scenario: "offline_replay" },
  ];
  try {
    for (let index = 0; index < plan.length; index += 1) {
      if (el.demoRunThreeButton) el.demoRunThreeButton.textContent = `正在执行 ${index + 1} / 3`;
      await runDemoRehearsal(plan[index].demoCase.id, plan[index].mode, plan[index]);
    }
    showToast("连续三次全流程演练完成");
  } finally {
    if (el.demoRunThreeButton) {
      el.demoRunThreeButton.disabled = false;
      el.demoRunThreeButton.textContent = "连续三次全流程演练";
    }
  }
}

async function runDemoLayoutAuditProfile(profile, width, height) {
  const frame = document.createElement("iframe");
  frame.title = `${width}×${height} 投屏布局检查`;
  frame.style.position = "fixed";
  frame.style.left = "-20000px";
  frame.style.top = "0";
  frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  frame.style.border = "0";
  frame.style.opacity = "0";
  frame.src = `${window.location.pathname}?view=demoConsoleView&layoutAudit=1`;
  document.body.append(frame);
  try {
    await new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error(`${width}×${height} 页面加载超时`)), 15000);
      frame.addEventListener("load", () => {
        window.setTimeout(() => {
          window.clearTimeout(timer);
          resolve();
        }, 1200);
      }, { once: true });
    });
    const doc = frame.contentDocument;
    if (!doc) throw new Error("无法读取同源投屏页面");
    const scrollWidth = Math.max(doc.documentElement.scrollWidth, doc.body?.scrollWidth || 0);
    const overflows = [...doc.querySelectorAll("[data-demo-critical]")].filter((node) => {
      const rect = node.getBoundingClientRect();
      return rect.left < -1 || rect.right > width + 1;
    }).map((node) => node.getAttribute("data-demo-critical") || node.id || node.className).slice(0, 20);
    return api("/api/demo-reliability/layout-audits", {
      method: "POST",
      body: JSON.stringify({
        profile,
        viewport_width: width,
        viewport_height: height,
        scroll_width: scrollWidth,
        critical_overflows: overflows,
        user_agent: navigator.userAgent,
      }),
    });
  } finally {
    frame.remove();
  }
}

async function runDemoLayoutAudits() {
  if (state.demoLayoutAuditRunning) return;
  state.demoLayoutAuditRunning = true;
  if (el.demoLayoutAuditButton) {
    el.demoLayoutAuditButton.disabled = true;
    el.demoLayoutAuditButton.textContent = "正在检查";
  }
  try {
    const results = [];
    results.push(await runDemoLayoutAuditProfile("projector_1440", 1440, 900));
    results.push(await runDemoLayoutAuditProfile("full_hd_1920", 1920, 1080));
    await refreshDemoReliability();
    const passed = results.filter((item) => item.status === "passed").length;
    showToast(`投屏实测完成：${passed} / 2 通过`);
  } finally {
    state.demoLayoutAuditRunning = false;
    if (el.demoLayoutAuditButton) {
      el.demoLayoutAuditButton.disabled = false;
      el.demoLayoutAuditButton.textContent = "检查两种尺寸";
    }
  }
}

function renderVisualSystem(payload) {
  state.visualSystem = payload;
  if (!el.visualAuditResults) return;
  const audits = payload?.audits || [];
  if (!audits.length) {
    el.visualAuditResults.className = "visual-audit-results empty-state";
    el.visualAuditResults.textContent = "尚未验收";
    return;
  }
  el.visualAuditResults.className = "visual-audit-results";
  el.visualAuditResults.innerHTML = audits.map((item) => {
    const checks = item.checks || {};
    const passedChecks = [
      "state_words_with_symbols", "conclusion_titles_visible", "identity_consistent",
      "focus_visible", "motion_can_be_disabled", "presentation_preserves_content",
      "editors_hidden_in_presentation",
    ].filter((key) => checks[key]).length;
    return `<article class="visual-audit-card is-${escapeHtml(item.status)}">
      <div><b>${escapeHtml(item.profile === "projector_1440" ? "PROJECTOR" : "FULL HD")}</b><strong>${Number(item.viewport_width)} × ${Number(item.viewport_height)}</strong></div>
      <span>关键检查 ${passedChecks} / 7 · 状态字 ${Number(checks.min_status_font_px || 0)}px · 页面宽 ${Number(item.scroll_width || 0)}</span>
      <em>${escapeHtml(demoStatusText(item.status))}</em>
    </article>`;
  }).join("");
}

async function refreshVisualSystem() {
  const payload = await api("/api/visual-system");
  renderVisualSystem(payload);
  return payload;
}

async function waitForVisualAuditFrame(frame, noticeId) {
  const started = Date.now();
  while (Date.now() - started < 20000) {
    const doc = frame.contentDocument;
    const dialog = doc?.querySelector("#opportunityDetailDialog[open]");
    const digitalTwin = dialog?.querySelector('[data-visual-component="digital-twin"]');
    const changeImpact = dialog?.querySelector('[data-visual-component="change-impact"], .change-wave-empty');
    const warRoom = dialog?.querySelector('[data-war-room-plan] [data-visual-component="war-room"]');
    const identity = dialog?.querySelector(".tt-identity-strip");
    if (digitalTwin && changeImpact && warRoom && identity?.textContent?.includes(noticeId)) return doc;
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  throw new Error("主案例关键页面加载超时");
}

async function runVisualSystemAuditProfile(profile, width, height, noticeId) {
  const frame = document.createElement("iframe");
  frame.title = `${width}×${height} 方向15视觉验收`;
  frame.style.position = "fixed";
  frame.style.left = "-30000px";
  frame.style.top = "0";
  frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  frame.style.border = "0";
  frame.style.opacity = "0";
  frame.src = `${window.location.pathname}?view=opportunityView&opportunity=${encodeURIComponent(noticeId)}&visualAuditFrame=1`;
  document.body.append(frame);
  try {
    await new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error(`${width}×${height} 页面加载超时`)), 20000);
      frame.addEventListener("load", () => {
        window.clearTimeout(timer);
        resolve();
      }, { once: true });
    });
    const doc = await waitForVisualAuditFrame(frame, noticeId);
    doc.body.classList.add("presentation-mode", "motion-disabled");
    const evidenceButton = doc.querySelector('[data-open-evidence-microscope]');
    if (!evidenceButton) throw new Error("主案例缺少证据入口");
    evidenceButton.click();
    const evidenceStarted = Date.now();
    while (Date.now() - evidenceStarted < 15000) {
      if (doc.querySelector('#evidenceMicroscopeDialog[open] .evidence-chain-visual, #evidenceMicroscopeDialog[open] .tt-empty-state')) break;
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    const logicalComponents = [
      ["digital-twin", doc.querySelector('[data-visual-component="digital-twin"]')],
      ["change-impact", doc.querySelector('[data-visual-component="change-impact"], .change-wave-empty')],
      ["war-room", doc.querySelector('[data-war-room-plan] [data-visual-component="war-room"]')],
      ["evidence-microscope", doc.querySelector('#evidenceMicroscopeDialog[open]')],
    ];
    const visibleComponents = logicalComponents.filter(([, node]) => {
      if (!node) return false;
      const style = frame.contentWindow.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    });
    const overflows = visibleComponents.filter(([, node]) => {
      const rect = node.getBoundingClientRect();
      return rect.left < -1 || rect.right > width + 1 || node.scrollWidth > node.clientWidth + 1;
    }).map(([label]) => label);
    const stateWords = [...doc.querySelectorAll(".tt-state")];
    const statusFontSizes = stateWords.map((node) => Number.parseFloat(frame.contentWindow.getComputedStyle(node.querySelector("span") || node).fontSize) || 0);
    const minStatusFont = statusFontSizes.length ? Math.min(...statusFontSizes) : 0;
    const conclusionNodes = [
      doc.querySelector('.tt-conclusion-title'),
      doc.querySelector('.change-wave-hero h4, .change-wave-empty strong'),
      doc.querySelector('.war-room-command-head strong'),
      doc.querySelector('#evidenceMicroscopeTitle'),
    ].filter((node) => node?.textContent?.trim());
    const identityText = doc.querySelector(".tt-identity-strip")?.textContent || "";
    const evidenceMeta = doc.querySelector("#evidenceMicroscopeMeta")?.textContent || "";
    const focusTarget = doc.querySelector('#evidenceMicroscopeDialog[open] button, [data-open-evidence-microscope]');
    focusTarget?.focus();
    focusTarget?.classList.add("tt-audit-focus-visible");
    const focusStyle = focusTarget ? frame.contentWindow.getComputedStyle(focusTarget) : null;
    const focusRuleCount = [...doc.styleSheets].reduce((count, sheet) => {
      try {
        return count + [...sheet.cssRules].filter((rule) => String(rule.selectorText || "").includes(":focus-visible")).length;
      } catch {
        return count;
      }
    }, 0);
    const focusOutlinePx = Number.parseFloat(focusStyle?.outlineWidth || "0") || 0;
    const motionTarget = doc.querySelector('[data-visual-component="change-impact"], .change-wave-empty');
    motionTarget?.classList.add("tt-event-impact");
    const motionStyle = motionTarget ? frame.contentWindow.getComputedStyle(motionTarget) : null;
    const editors = [...doc.querySelectorAll(".evidence-review-form, .opportunity-requirement-form, .opportunity-facts-form, .collaboration-note-form")];
    const checks = {
      state_words_with_symbols: stateWords.length > 0 && stateWords.every((node) => node.querySelector("b")?.textContent?.trim() && node.querySelector("span")?.textContent?.trim()),
      conclusion_titles_visible: conclusionNodes.length >= 4,
      identity_consistent: identityText.includes(noticeId) && evidenceMeta.includes(noticeId),
      focus_visible: Boolean(focusRuleCount > 0 && focusTarget && focusOutlinePx >= 2),
      motion_can_be_disabled: Boolean(motionStyle && motionStyle.animationName === "none" && motionStyle.transitionDuration.split(",").every((value) => Number.parseFloat(value) === 0)),
      presentation_preserves_content: visibleComponents.length >= 4,
      editors_hidden_in_presentation: editors.length > 0 && editors.every((node) => frame.contentWindow.getComputedStyle(node).display === "none"),
      min_status_font_px: minStatusFont,
      critical_component_count: visibleComponents.length,
      conclusion_title_count: conclusionNodes.length,
      focus_target_found: Boolean(focusTarget),
      focus_rule_count: focusRuleCount,
      focus_outline_px: focusOutlinePx,
    };
    focusTarget?.classList.remove("tt-audit-focus-visible");
    motionTarget?.classList.remove("tt-event-impact");
    const scrollWidth = Math.max(doc.documentElement.scrollWidth, doc.body?.scrollWidth || 0);
    return api("/api/visual-system/audits", {
      method: "POST",
      body: JSON.stringify({
        profile,
        viewport_width: width,
        viewport_height: height,
        notice_id: noticeId,
        scroll_width: scrollWidth,
        critical_overflows: overflows,
        checks,
        user_agent: navigator.userAgent,
      }),
    });
  } finally {
    frame.remove();
  }
}

async function runVisualSystemAudits() {
  if (state.visualAuditRunning) return;
  state.visualAuditRunning = true;
  if (el.visualAuditButton) {
    el.visualAuditButton.disabled = true;
    el.visualAuditButton.textContent = "正在验收";
  }
  try {
    const reliability = state.demoReliability || await refreshDemoReliability();
    const mainCase = (reliability?.cases || []).find((item) => item.role === "main");
    if (!mainCase || mainCase.source_type !== "opportunity") throw new Error("主案例尚未绑定真实机会记录");
    const results = [];
    results.push(await runVisualSystemAuditProfile("projector_1440", 1440, 900, mainCase.source_id));
    results.push(await runVisualSystemAuditProfile("full_hd_1920", 1920, 1080, mainCase.source_id));
    await refreshVisualSystem();
    showToast(`方向15视觉验收完成：${results.filter((item) => item.status === "passed").length} / 2 通过`);
  } finally {
    state.visualAuditRunning = false;
    if (el.visualAuditButton) {
      el.visualAuditButton.disabled = false;
      el.visualAuditButton.textContent = "验收关键页面";
    }
  }
}

async function refreshOpportunityRadar({ persist = false } = {}) {
  if (!el.radarMap) return null;
  const windowDays = Number(el.radarWindowSelect?.value || 365);
  const category = el.radarCategorySelect?.value || "";
  if (el.refreshRadarButton) {
    el.refreshRadarButton.disabled = true;
    el.refreshRadarButton.textContent = persist ? "正在保存快照" : "正在读取索引";
  }
  try {
    const payload = persist
      ? await api("/api/opportunity-radar/refresh", { method: "POST", body: JSON.stringify({ scope: state.radarScope, window_days: windowDays, category, actor: "admin" }) })
      : await api(`/api/opportunity-radar?${new URLSearchParams({ scope: state.radarScope, window_days: String(windowDays), category })}`);
    state.opportunityRadar = payload;
    if (!(payload.locations || []).some((item) => item.id === state.radarSelectedLocationId)) {
      state.radarSelectedLocationId = payload.locations?.[0]?.id || "";
    }
    renderOpportunityRadar(payload);
    announceBusinessEvent(document.querySelector(".radar-command"), "arrival");
    if (persist) showToast(`本地雷达快照已保存，共 ${payload.summary?.opportunity_count || 0} 条机会`);
    return payload;
  } finally {
    if (el.refreshRadarButton) {
      el.refreshRadarButton.disabled = false;
      el.refreshRadarButton.textContent = "刷新本地快照";
    }
  }
}

function renderOpportunityRadar(payload) {
  const summary = payload.summary || {};
  const snapshot = payload.snapshot || {};
  if (el.radarDataAsOf) el.radarDataAsOf.textContent = `截至 ${compactDateTimeText(payload.data_as_of || payload.generated_at) || "当前本地索引"}`;
  if (el.radarMapTitle) el.radarMapTitle.textContent = state.radarScope === "domestic" ? "全国机会分布" : state.radarScope === "international" ? "国际机会分布" : "全球机会总览";
  if (el.radarMapMeta) el.radarMapMeta.textContent = `${summary.location_count || 0} 个有数据地区 · ${summary.opportunity_count || 0} 条机会`;
  document.querySelectorAll("[data-radar-scope]").forEach((button) => button.classList.toggle("is-active", button.dataset.radarScope === state.radarScope));
  if (el.radarMetrics) {
    el.radarMetrics.className = "radar-metrics";
    el.radarMetrics.innerHTML = [
      radarMetric("本地机会", summary.opportunity_count || 0, `${summary.location_count || 0} 个地区`),
      radarMetric("近7天新增", summary.recent_7d_count || 0, payload.window_days ? `当前窗口 ${payload.window_days} 天` : "全部索引"),
      radarMetric("数据来源", summary.source_count || 0, `正常 ${summary.healthy_source_count || 0}`),
      radarMetric("需关注", summary.attention_source_count || 0, `访问受限 ${summary.limited_source_count || 0}`),
      radarMetric("离线快照", snapshot.id ? "已保存" : "未保存", snapshot.created_at ? compactDateTimeText(snapshot.created_at) : "点击刷新本地快照"),
    ].join("");
  }
  renderRadarCategoryOptions(payload.available_categories || [], payload.category || "");
  renderRadarMap(payload);
  renderRadarInspector(payload);
  renderRadarCategoryHeat(payload.categories || [], summary.opportunity_count || 0);
  renderRadarLatest(payload.latest || []);
  renderRadarSources(payload.sources || [], summary);
  if (el.radarMethodNote) el.radarMethodNote.textContent = `统计截至 ${compactDateTimeText(payload.data_as_of || "") || "本地索引时间"}；只读取本地索引与已保存健康记录，手动刷新不触发外部采集。`;
}

function radarMetric(label, value, detail) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
}

function renderRadarCategoryOptions(items, selected) {
  if (!el.radarCategorySelect) return;
  const signature = items.map((item) => `${item.name}:${item.count}`).join("|");
  if (el.radarCategorySelect.dataset.signature === signature && el.radarCategorySelect.value === selected) return;
  el.radarCategorySelect.dataset.signature = signature;
  el.radarCategorySelect.innerHTML = `<option value="">全部品类</option>${items.map((item) => `<option value="${escapeHtml(item.name)}" ${item.name === selected ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.count)}</option>`).join("")}`;
}

function renderRadarMap(payload) {
  if (!el.radarMap) return;
  const domestic = state.radarScope === "domestic";
  const locations = Array.isArray(payload.locations) ? payload.locations : [];
  const background = domestic ? radarChinaBackground() : radarWorldBackground();
  if (!locations.length) {
    el.radarMap.innerHTML = `${background}<div class="radar-map-empty"><b>当前筛选没有本地机会</b><span>这是“0条结果”，不代表数据源发生故障。可扩大时间窗口或取消品类筛选。</span></div>`;
    return;
  }
  const maxCount = Math.max(...locations.map((item) => Number(item.opportunity_count || 0)), 1);
  el.radarMap.innerHTML = `${background}<div class="radar-rings" aria-hidden="true"><i></i><i></i><i></i></div>${locations.map((item) => {
    const x = domestic ? item.china_x : item.world_x;
    const y = domestic ? item.china_y : item.world_y;
    const size = 18 + Math.round(Math.sqrt(Number(item.opportunity_count || 0) / maxCount) * 28);
    const trust = Number(item.reliability_score || 0) >= 0.85 ? "high" : Number(item.reliability_score || 0) >= 0.6 ? "medium" : "low";
    return `<button type="button" class="radar-location trust-${trust} ${item.id === state.radarSelectedLocationId ? "is-selected" : ""}" data-radar-location="${escapeHtml(item.id)}" style="--radar-x:${Number(x)}%;--radar-y:${Number(y)}%;--radar-size:${size}px" aria-label="${escapeHtml(item.name)} ${escapeHtml(item.opportunity_count)}条机会"><i></i><b>${escapeHtml(item.opportunity_count)}</b><span>${escapeHtml(item.name)}</span></button>`;
  }).join("")}`;
}

function radarWorldBackground() {
  return `<svg class="radar-map-svg" viewBox="0 0 1000 520" aria-hidden="true"><defs><linearGradient id="radarSea" x1="0" x2="1"><stop stop-color="#071b36"/><stop offset="1" stop-color="#0b2944"/></linearGradient></defs><rect width="1000" height="520" fill="url(#radarSea)"/><g class="radar-graticule"><path d="M0 130H1000M0 260H1000M0 390H1000M200 0V520M400 0V520M600 0V520M800 0V520"/></g><g class="radar-land"><path d="M58 94l72-35 111 16 55 50-18 55-62 11-31 50-74-20-30-64z"/><path d="M218 257l55 15 39 64-14 102-38 55-25-79-36-74z"/><path d="M414 98l76-40 89 27 36 50-29 33-72-6-35 40-61-22-38-44z"/><path d="M470 210l87-19 68 48-8 102-53 111-64-22-28-98-40-51z"/><path d="M590 93l111-35 153 27 92 68-24 80-96 18-45-31-53 45-75-31-35-61z"/><path d="M781 333l91-27 73 53-22 70-102 9-55-51z"/></g><g class="radar-border-glow"><path d="M58 94l72-35 111 16M414 98l76-40 89 27M590 93l111-35 153 27M470 210l87-19 68 48M781 333l91-27"/></g></svg>`;
}

function radarChinaBackground() {
  return `<svg class="radar-map-svg" viewBox="0 0 1000 520" aria-hidden="true"><defs><linearGradient id="radarChinaSea" x1="0" x2="1"><stop stop-color="#061a34"/><stop offset="1" stop-color="#0a304b"/></linearGradient></defs><rect width="1000" height="520" fill="url(#radarChinaSea)"/><g class="radar-graticule"><path d="M0 130H1000M0 260H1000M0 390H1000M200 0V520M400 0V520M600 0V520M800 0V520"/></g><path class="radar-china-land" d="M112 138l83-52 105 15 78-35 89 42 92-9 82 53 98-19 91 52 5 77-61 44-21 81-73 37-56-39-84 19-49-43-83 32-80-44-80-6-31-62-72-23-45-62z"/><g class="radar-china-lines"><path d="M211 119l55 82 82-32 59 83 89-63 63 79 88-74 74 94M171 252l101-12 76 85 96-30 72 71 93-49 102 17M303 101l-31 139M407 108v144M559 99v169M641 152l6 42"/></g></svg>`;
}

function renderRadarInspector(payload) {
  if (!el.radarInspector) return;
  const location = (payload.locations || []).find((item) => item.id === state.radarSelectedLocationId) || payload.locations?.[0];
  if (!location) {
    el.radarInspector.className = "radar-inspector empty-state";
    el.radarInspector.textContent = "当前筛选没有地区机会";
    return;
  }
  state.radarSelectedLocationId = location.id;
  const opportunities = (payload.opportunities || []).filter((item) => item.location_id === location.id).slice(0, 7);
  el.radarInspector.className = "radar-inspector";
  el.radarInspector.innerHTML = `<header><span>${location.domestic ? "全国节点" : "全球节点"}</span><h2>${escapeHtml(location.name)}</h2><p><b>${escapeHtml(location.opportunity_count)}</b> 条本地机会 · 近7天新增 ${escapeHtml(location.recent_7d_count || 0)}</p></header>
    <div class="radar-inspector-trust"><span>来源平均可信</span><strong>${escapeHtml(location.reliability_score ? percent(location.reliability_score) : "待验证")}</strong><em>${escapeHtml(location.reliability_status || "待验证")}</em></div>
    <div class="radar-inspector-tags">${(location.hot_categories || []).map((item) => `<span>${escapeHtml(item.name)} · ${escapeHtml(item.count)}</span>`).join("")}</div>
    <div class="radar-inspector-list">${opportunities.map((item) => `<button type="button" data-radar-open-opportunity="${escapeHtml(item.notice_id)}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.source_site)} · ${escapeHtml(item.publish_time || "时间待核")}</small></button>`).join("")}</div>
    <button class="radar-query-button" type="button" data-radar-query-location="${escapeHtml(location.name)}">带入自然语言查询</button>`;
}

function renderRadarCategoryHeat(items, total) {
  if (!el.radarCategoryHeat) return;
  if (!items.length) {
    el.radarCategoryHeat.className = "radar-category-heat empty-state";
    el.radarCategoryHeat.textContent = "当前筛选没有品类统计";
    return;
  }
  const max = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  el.radarCategoryHeat.className = "radar-category-heat";
  el.radarCategoryHeat.innerHTML = items.slice(0, 8).map((item, index) => `<button type="button" data-radar-category="${escapeHtml(item.name)}"><span>${String(index + 1).padStart(2, "0")}</span><div><b>${escapeHtml(item.name)}</b><i style="--heat:${Math.max(8, Number(item.count || 0) / max * 100)}%"></i></div><strong>${escapeHtml(item.count)}</strong><small>${total ? Math.round(Number(item.count || 0) / total * 100) : 0}%</small></button>`).join("");
}

function renderRadarLatest(items) {
  if (!el.radarLatest) return;
  if (!items.length) {
    el.radarLatest.className = "radar-latest empty-state";
    el.radarLatest.textContent = "当前窗口没有新增机会";
    return;
  }
  el.radarLatest.className = "radar-latest";
  el.radarLatest.innerHTML = items.slice(0, 8).map((item) => `<button type="button" data-radar-open-opportunity="${escapeHtml(item.notice_id)}"><i></i><span><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.location_name)} · ${escapeHtml(item.category)} · ${escapeHtml(item.publish_time || "时间待核")}</small></span><em>${escapeHtml(item.source_site)}</em></button>`).join("");
}

function renderRadarSources(items, summary) {
  if (el.radarSourceMeta) el.radarSourceMeta.textContent = `${items.length} 个来源 · 正常 ${summary.healthy_source_count || 0} · 需关注 ${summary.attention_source_count || 0} · 受限 ${summary.limited_source_count || 0}`;
  if (el.radarSourceSummary) {
    el.radarSourceSummary.className = "radar-source-summary";
    el.radarSourceSummary.innerHTML = `<div class="radar-source-orbit">${radarWorldBackground()}${items.map((item) => `<span class="source-${escapeHtml(item.availability_status)}" style="--source-x:${Number(item.world_x)}%;--source-y:${Number(item.world_y)}%" title="${escapeHtml(item.authority)} · ${escapeHtml(item.availability_label)}"><i></i><b>${escapeHtml(item.site)}</b></span>`).join("")}</div><div class="radar-source-explain"><strong>可信度不是结果数量</strong><p>绿色表示近期运行稳定；黄色表示性能下降或待验证；红色表示当前异常；紫色表示登录或外部访问限制。</p><p>来源正常但本地0条时单独标为“0条结果”，不会误报成故障。</p></div>`;
  }
  if (!el.radarSourceMap) return;
  el.radarSourceMap.className = "radar-source-map";
  el.radarSourceMap.innerHTML = items.map((item) => `<article class="source-${escapeHtml(item.availability_status)} data-${escapeHtml(item.data_status)}"><header><i></i><div><strong>${escapeHtml(item.authority)}</strong><small>${escapeHtml(item.site)} · ${item.domestic ? "国内" : "国际"}</small></div><span>${escapeHtml(item.availability_label)}</span></header><div class="radar-source-numbers"><b>${item.success_rate === null || item.success_rate === undefined ? "-" : escapeHtml(percent(item.success_rate))}<small>成功率</small></b><b>${item.avg_elapsed_ms ? escapeHtml(`${item.avg_elapsed_ms}ms`) : "-"}<small>平均延迟</small></b><b>${escapeHtml(item.local_notice_count || 0)}<small>本地结果</small></b></div><p><span>最近成功</span><b>${escapeHtml(compactDateTimeText(item.last_success_at) || "暂无记录")}</b></p>${item.last_error ? `<p class="radar-source-error"><span>最近异常</span><b>${escapeHtml(item.last_error)}</b></p>` : ""}<footer><em class="data-${escapeHtml(item.data_status)}">${escapeHtml(item.data_status_label)}</em><small>${escapeHtml((item.restrictions || []).join(" · ") || `${item.route_count || 0} 条采集路由`)}</small></footer></article>`).join("");
}

function selectRadarLocation(locationId) {
  state.radarSelectedLocationId = locationId;
  if (state.opportunityRadar) {
    renderRadarMap(state.opportunityRadar);
    renderRadarInspector(state.opportunityRadar);
  }
}

function applyRadarQuery(locationName) {
  const days = Number(el.radarWindowSelect?.value || 365);
  const category = el.radarCategorySelect?.value || "招标采购";
  const timeText = days ? `最近${days}天` : "全部历史";
  if (el.queryInput) el.queryInput.value = `${timeText}${locationName}${category}机会有哪些`;
  state.intentConfirmation = { query: "", confirmed: false };
  showView("workbenchView");
  refreshIntentPreview().catch(toastError("查询预览失败"));
  el.queryInput?.focus();
  showToast(`已将${locationName}条件带入自然语言查询`);
}

function battleLayerSelection() {
  return [...document.querySelectorAll("[data-battle-layer]:checked")]
    .map((input) => input.dataset.battleLayer)
    .filter(Boolean);
}

async function refreshBattleMap({ sync = false, fetchExternal = false } = {}) {
  if (!el.battleMap) return null;
  if (sync || fetchExternal) {
    const button = fetchExternal ? el.battleExternalButton : el.battleSyncButton;
    if (button) button.disabled = true;
    try {
      const receipt = await api("/api/battle-map/sync", {
        method: "POST",
        body: JSON.stringify({ fetch_external: fetchExternal, external_limit: 60, actor: "admin" }),
      });
      const message = fetchExternal
        ? `已同步 ${receipt.external?.imported_count || 0} 条 USGS 事件，形成 ${receipt.candidate_impact_count || 0} 条待复核影响`
        : `本地事件已刷新：${receipt.business?.geo_events || 0} 条`;
      showToast(message);
    } finally {
      if (button) button.disabled = false;
    }
  }
  const params = new URLSearchParams({
    scope: state.battleScope,
    window_hours: String(Number(el.battleWindowSelect?.value || 2160)),
    category: el.battleCategorySelect?.value || "",
    layers: battleLayerSelection().join(","),
    mode: el.battleModeSelect?.value || "live",
  });
  const payload = await api(`/api/battle-map?${params}`);
  state.battleMap = payload;
  const frames = payload.timeline?.frames || [];
  state.battleTimelineIndex = Math.max(0, frames.length - 1);
  renderBattleMap(payload);
  announceBusinessEvent(el.battleMap, "arrival");
  return payload;
}

function ensureBattleMapStream() {
  if (state.battleEventSource || typeof EventSource === "undefined") {
    if (typeof EventSource === "undefined") setBattleLiveState("fallback", "按需刷新", "当前浏览器不支持 SSE");
    return;
  }
  const source = new EventSource("/api/battle-map/stream");
  state.battleEventSource = source;
  source.addEventListener("revision", (event) => {
    try {
      const receipt = JSON.parse(event.data || "{}");
      setBattleLiveState("live", "实时连接", compactDateTimeText(receipt.generated_at) || "刚刚");
      if (state.battleRevision && receipt.revision !== state.battleRevision && el.battleModeSelect?.value === "live") {
        refreshBattleMap().catch(toastError("实时事件更新失败"));
      }
      state.battleRevision = receipt.revision || state.battleRevision;
    } catch {}
  });
  source.onerror = () => setBattleLiveState("fallback", "连接重试中", "地图仍可使用本地数据与回放");
}

function setBattleLiveState(kind, title, detail) {
  if (!el.battleLiveState) return;
  el.battleLiveState.className = `battle-live-state is-${kind}`;
  const strong = el.battleLiveState.querySelector("strong");
  const span = el.battleLiveState.querySelector("span");
  if (strong) strong.textContent = title;
  if (span) span.textContent = detail;
}

function renderBattleMap(payload) {
  const summary = payload.summary || {};
  const replay = payload.replay || {};
  const modeLabel = payload.mode === "replay" ? "已验证回放" : "当前本地事件流";
  if (el.battleDataAsOf) el.battleDataAsOf.textContent = `数据截至 ${compactDateTimeText(payload.data_as_of) || "待核"}`;
  setBattleLiveState(payload.mode === "replay" ? "replay" : "live", modeLabel, replay.verified_at ? `验证于 ${compactDateTimeText(replay.verified_at)}` : compactDateTimeText(payload.last_connected_at || payload.generated_at));
  document.querySelectorAll("[data-battle-scope]").forEach((button) => button.classList.toggle("is-active", button.dataset.battleScope === state.battleScope));
  renderBattleCategoryOptions(payload.available_categories || [], payload.category || "");
  if (el.battleMetrics) {
    el.battleMetrics.className = "battle-metrics";
    el.battleMetrics.innerHTML = [
      battleMetric("商机事件", summary.opportunity_count || 0, "真实公告"),
      battleMetric("成交事件", summary.award_count || 0, `${summary.flow_count || 0} 条可证流向`),
      battleMetric("外部事件", summary.external_event_count || 0, "USGS 官方源"),
      battleMetric("候选影响", summary.candidate_impact_count || 0, `已确认 ${summary.confirmed_impact_count || 0}`),
      battleMetric("省级定位", `${Math.round(Number(summary.province_precision_rate || 0) * 100)}%`, `${summary.cluster_count || 0} 个聚合节点`),
    ].join("");
  }
  renderBattleTimeline(payload);
  renderBattleFrame(payload);
  if (el.battleMethodNote) {
    el.battleMethodNote.textContent = `${modeLabel}；地图与列表共享同一事件查询。外部事件存在不等于项目受影响，${summary.candidate_impact_count || 0} 条关系均保留规则、置信度和人工复核状态。`;
  }
}

function battleMetric(label, value, detail) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
}

function renderBattleCategoryOptions(items, selected) {
  if (!el.battleCategorySelect) return;
  const signature = JSON.stringify(items);
  if (el.battleCategorySelect.dataset.signature === signature) return;
  el.battleCategorySelect.dataset.signature = signature;
  el.battleCategorySelect.innerHTML = `<option value="">全部品类</option>${items.map((item) => `<option value="${escapeHtml(item.name)}" ${item.name === selected ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.count)}</option>`).join("")}`;
}

function renderBattleTimeline(payload) {
  const frames = payload.timeline?.frames || [];
  const max = Math.max(0, frames.length - 1);
  state.battleTimelineIndex = Math.min(max, Math.max(0, state.battleTimelineIndex));
  if (el.battleTimelineRange) {
    el.battleTimelineRange.max = String(max);
    el.battleTimelineRange.value = String(state.battleTimelineIndex);
    el.battleTimelineRange.disabled = !frames.length;
  }
  if (el.battleTimelineTicks) {
    const visible = frames.length <= 7 ? frames : frames.filter((_, index) => index === 0 || index === frames.length - 1 || index % Math.ceil(frames.length / 5) === 0);
    el.battleTimelineTicks.innerHTML = visible.map((frame) => `<span>${escapeHtml(frame.time.slice(5))}</span>`).join("");
  }
  updateBattleTimelineSummary(payload);
}

function updateBattleTimelineSummary(payload) {
  const frames = payload.timeline?.frames || [];
  const frame = frames[state.battleTimelineIndex];
  if (el.battleTimelineLabel) el.battleTimelineLabel.textContent = frame ? `${frame.time} · 截至此日` : "当前筛选没有带时间事件";
  if (el.battleTimelineCompare) {
    const previous = state.battleTimelineIndex > 0 ? frames[state.battleTimelineIndex - 1] : null;
    const delta = frame ? Number(frame.total || 0) - Number(previous?.total || 0) : 0;
    el.battleTimelineCompare.innerHTML = frame
      ? `<b>${delta >= 0 ? "+" : ""}${delta} 事件</b><span>商机 ${escapeHtml(frame.opportunity || 0)} · 成交 ${escapeHtml(frame.award || 0)} · 外部 ${escapeHtml(frame.external || 0)}</span>`
      : "<b>当前</b><span>无可比较事件</span>";
  }
}

function battleFrameCutoff(payload) {
  const frame = payload.timeline?.frames?.[state.battleTimelineIndex];
  if (!frame) return Number.POSITIVE_INFINITY;
  return new Date(`${frame.time}T23:59:59Z`).getTime();
}

function renderBattleFrame(payload) {
  const cutoff = battleFrameCutoff(payload);
  const timed = (item) => {
    const value = new Date(item.event_time || 0).getTime();
    return !Number.isFinite(value) || value <= cutoff;
  };
  const events = (payload.events || []).filter(timed);
  const external = (payload.external_events || []).filter(timed);
  const flows = (payload.flows || []).filter(timed);
  renderBattleSpatialMap(payload, events, external, flows);
  renderBattleImpacts(payload, external);
  renderBattleEventList(events, external, flows);
  updateBattleTimelineSummary(payload);
}

function battleClientClusters(items) {
  const buckets = new Map();
  for (const item of items) {
    if (item.map_x === null || item.map_x === undefined || item.map_y === null || item.map_y === undefined) continue;
    const key = `${Math.round(Number(item.map_x) / 3) * 3}:${Math.round(Number(item.map_y) / 3) * 3}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(item);
  }
  return [...buckets.entries()].map(([id, members]) => ({
    id,
    map_x: members.reduce((sum, item) => sum + Number(item.map_x), 0) / members.length,
    map_y: members.reduce((sum, item) => sum + Number(item.map_y), 0) / members.length,
    count: members.length,
    primary_layer: members.some((item) => item.layer === "external") ? "external" : members.some((item) => item.layer === "award") ? "award" : "opportunity",
    event_ids: members.map((item) => item.id),
    labels: members.slice(0, 3).map((item) => item.title),
    region_name: members[0].region_name || "",
  }));
}

function renderBattleSpatialMap(payload, events, external, flows) {
  if (!el.battleMap) return;
  const background = state.battleScope === "china" ? radarChinaBackground() : radarWorldBackground();
  const clusters = battleClientClusters([...events, ...external]);
  const visibleFlows = flows.filter((flow) => [flow.from_x, flow.from_y, flow.to_x, flow.to_y].every((value) => value !== null && value !== undefined));
  const flowPaths = visibleFlows.map((flow) => {
    const x1 = Number(flow.from_x) * 10;
    const y1 = Number(flow.from_y) * 5.2;
    const x2 = Number(flow.to_x) * 10;
    const y2 = Number(flow.to_y) * 5.2;
    const cx = (x1 + x2) / 2;
    const cy = Math.min(y1, y2) - Math.max(22, Math.abs(x2 - x1) * .14);
    return `<path d="M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}" />`;
  }).join("");
  const flowButtons = visibleFlows.map((flow) => `<button class="battle-flow-hit" type="button" data-battle-event="${escapeHtml(flow.id)}" style="--battle-x:${(Number(flow.from_x) + Number(flow.to_x)) / 2}%;--battle-y:${(Number(flow.from_y) + Number(flow.to_y)) / 2}%" aria-label="查看流向 ${escapeHtml(flow.from_label)} 到 ${escapeHtml(flow.to_label)}">↗</button>`).join("");
  const points = clusters.map((cluster) => {
    const size = Math.min(52, 22 + Math.sqrt(cluster.count) * 8);
    return `<button class="battle-point layer-${escapeHtml(cluster.primary_layer)}" type="button" data-battle-event="${escapeHtml(cluster.event_ids[0])}" style="--battle-x:${Number(cluster.map_x)}%;--battle-y:${Number(cluster.map_y)}%;--battle-size:${size}px" title="${escapeHtml(cluster.labels.join("；"))}" aria-label="${escapeHtml(cluster.region_name || "事件节点")} ${cluster.count} 条事件"><i></i><b>${escapeHtml(cluster.count)}</b><span>${escapeHtml(cluster.region_name || cluster.primary_layer)}</span></button>`;
  }).join("");
  el.battleMap.className = "battle-map";
  el.battleMap.innerHTML = `${background}<svg class="battle-flow-overlay" viewBox="0 0 1000 520" preserveAspectRatio="none" aria-hidden="true">${flowPaths}</svg>${flowButtons}${points}${clusters.length ? "" : '<div class="battle-map-empty"><strong>当前时间点没有事件</strong><span>可扩大时间窗口、切换范围或恢复图层。</span></div>'}`;
  if (el.battleMapMeta) el.battleMapMeta.textContent = `${clusters.length} 个聚合节点 · ${visibleFlows.length} 条流向 · ${payload.mode === "replay" ? "回放模式" : "实时模式"}`;
}

function renderBattleImpacts(payload, visibleExternal) {
  if (!el.battleImpactList) return;
  const visible = new Set(visibleExternal.map((item) => item.id));
  const cards = (payload.impact_cards || []).filter((card) => visible.has(card.event?.id));
  if (!cards.length) {
    el.battleImpactList.className = "battle-impact-list empty-state";
    el.battleImpactList.innerHTML = "<strong>当前没有候选影响</strong><span>外部事件与项目必须满足地区或距离规则才会建立关系。</span>";
    return;
  }
  el.battleImpactList.className = "battle-impact-list";
  el.battleImpactList.innerHTML = cards.slice(0, 12).map((card) => `<article class="impact-${escapeHtml(card.event.severity)}">
    <button class="battle-impact-event" type="button" data-battle-event="${escapeHtml(card.event.id)}"><span>${escapeHtml(card.event.source_name)} · ${escapeHtml(card.event.event_type)}</span><strong>${escapeHtml(card.event.title)}</strong><small>${escapeHtml(compactDateTimeText(card.event.event_time))} · ${escapeHtml(card.event.coordinate_precision)}定位</small></button>
    <div class="battle-impact-count"><b>${escapeHtml(card.impact_count)}</b><span>候选影响</span></div>
    ${(card.impacts || []).slice(0, 4).map((impact) => `<div class="battle-impact-target"><header><span class="basis-${escapeHtml(impact.relation_basis)}">${escapeHtml(impact.relation_basis === "rule" ? "规则关联" : impact.relation_basis)}</span><em>${escapeHtml(impact.review_status === "confirmed" ? "已确认" : impact.review_status === "rejected" ? "已排除" : impact.review_status === "monitoring" ? "持续监测" : "待复核")}</em></header><strong>${escapeHtml(impact.target_title)}</strong><p>${escapeHtml(impact.explanation)}</p><small>${escapeHtml(impact.impact_scope)} · 置信 ${escapeHtml(impact.confidence)}</small><footer><button type="button" data-review-battle-impact="${escapeHtml(impact.id)}" data-impact-status="monitoring">设为监测</button><button type="button" data-review-battle-impact="${escapeHtml(impact.id)}" data-impact-status="rejected">排除关联</button></footer></div>`).join("")}
  </article>`).join("");
}

function renderBattleEventList(events, external, flows) {
  if (!el.battleEventList) return;
  const items = [...events, ...external, ...flows].sort((left, right) => String(right.event_time).localeCompare(String(left.event_time)));
  if (el.battleListMeta) el.battleListMeta.textContent = `${items.length} 条 · 与地图同口径`;
  if (!items.length) {
    el.battleEventList.className = "battle-event-list empty-state";
    el.battleEventList.textContent = "当前时间点没有事件";
    return;
  }
  el.battleEventList.className = "battle-event-list";
  el.battleEventList.innerHTML = items.slice(0, 120).map((item) => `<button type="button" role="listitem" data-battle-event="${escapeHtml(item.id)}"><i class="layer-${escapeHtml(item.layer)}"></i><span><strong>${escapeHtml(item.title || `${item.from_label} → ${item.to_label}`)}</strong><small>${escapeHtml(item.region_name || item.from_label || "位置待核")} · ${escapeHtml(compactDateTimeText(item.event_time) || "时间待核")} · ${escapeHtml(item.coordinate_precision || item.from_precision || "精度待核")}</small></span><em>${escapeHtml(item.source_name || "本地")}</em></button>`).join("");
}

async function openBattleEvidence(eventId) {
  if (!el.battleEvidenceDialog || !eventId) return;
  const payload = await api(`/api/battle-map/events/${encodeURIComponent(eventId)}`);
  const event = payload.event || {};
  if (el.battleEvidenceTitle) el.battleEvidenceTitle.textContent = event.title || `${event.from_label || ""} → ${event.to_label || ""}` || "事件证据";
  if (el.battleEvidenceMeta) el.battleEvidenceMeta.textContent = `${payload.kind || "event"} · ${event.id || eventId}`;
  const impacts = payload.impacts || [];
  if (el.battleEvidenceContent) el.battleEvidenceContent.innerHTML = `<div class="battle-evidence-assurance"><span><b>来源</b>${escapeHtml(event.source_name || "本地索引")}</span><span><b>证据状态</b>${escapeHtml(event.evidence_status || "待核")}</span><span><b>坐标精度</b>${escapeHtml(event.coordinate_precision || `${event.from_precision || ""}/${event.to_precision || ""}`)}</span><span><b>事件时间</b>${escapeHtml(compactDateTimeText(event.event_time) || "待核")}</span></div>
    <section><h3>事实与边界</h3><p>${escapeHtml(event.summary || "该点或连线来自已保存的业务记录；地图不补造未知地点。")}</p><dl><div><dt>区域</dt><dd>${escapeHtml(event.region_name || event.from_label || "待核")}</dd></div><div><dt>采集时间</dt><dd>${escapeHtml(compactDateTimeText(event.captured_at) || "待核")}</dd></div><div><dt>许可</dt><dd>${escapeHtml(event.source_license || "原业务来源")}</dd></div>${event.snapshot_sha256 ? `<div><dt>快照 SHA-256</dt><dd>${escapeHtml(event.snapshot_sha256)}</dd></div>` : ""}</dl>${event.source_url ? `<a href="${escapeHtml(event.source_url)}" target="_blank" rel="noreferrer">打开原始证据 ↗</a>` : ""}</section>
    ${impacts.length ? `<section><h3>候选影响链</h3>${impacts.map((impact) => `<article><strong>${escapeHtml(impact.target_title)}</strong><p>${escapeHtml(impact.explanation)}</p><small>${escapeHtml(impact.relation_basis)} · ${escapeHtml(impact.rule_key)} · 置信 ${escapeHtml(impact.confidence)} · ${escapeHtml(impact.review_status)}</small><b>建议：${escapeHtml(impact.suggested_action)}</b></article>`).join("")}</section>` : ""}`;
  if (!el.battleEvidenceDialog.open) el.battleEvidenceDialog.showModal();
}

async function reviewBattleImpact(impactId, status) {
  const notes = {
    monitoring: "规则命中成立，先核验实际交付地点、合作方和运输路径，确认前仅作为监测候选。",
    rejected: "人工复核后确认当前项目与该外部事件没有可证明的业务关联。",
    confirmed: "人工已核对交付地点或供应链证据，确认该外部事件影响当前对象。",
  };
  await api(`/api/battle-map/impacts/${encodeURIComponent(impactId)}/review`, {
    method: "POST",
    body: JSON.stringify({ status, actor: "admin", note: notes[status] || "人工复核" }),
  });
  showToast(status === "rejected" ? "已排除该候选关联" : "已更新人工复核状态");
  await refreshBattleMap();
}

async function saveBattleReplay() {
  if (el.battleReplayButton) el.battleReplayButton.disabled = true;
  try {
    const frame = await api("/api/battle-map/replays", {
      method: "POST",
      body: JSON.stringify({
        scope: state.battleScope,
        window_hours: Number(el.battleWindowSelect?.value || 2160),
        category: el.battleCategorySelect?.value || "",
        actor: "admin",
        verified: true,
      }),
    });
    showToast(`已保存验证回放 ${String(frame.state_hash || "").slice(0, 10)}`);
  } finally {
    if (el.battleReplayButton) el.battleReplayButton.disabled = false;
  }
}

function toggleBattlePlayback() {
  if (state.battlePlayTimer) {
    window.clearInterval(state.battlePlayTimer);
    state.battlePlayTimer = null;
    if (el.battlePlayButton) {
      el.battlePlayButton.textContent = "▶ 播放";
      el.battlePlayButton.setAttribute("aria-pressed", "false");
    }
    return;
  }
  const frames = state.battleMap?.timeline?.frames || [];
  if (frames.length < 2) return;
  state.battleTimelineIndex = 0;
  if (el.battlePlayButton) {
    el.battlePlayButton.textContent = "Ⅱ 暂停";
    el.battlePlayButton.setAttribute("aria-pressed", "true");
  }
  renderBattleFrame(state.battleMap);
  state.battlePlayTimer = window.setInterval(() => {
    state.battleTimelineIndex += 1;
    if (state.battleTimelineIndex >= frames.length) {
      state.battleTimelineIndex = frames.length - 1;
      toggleBattlePlayback();
    }
    if (el.battleTimelineRange) el.battleTimelineRange.value = String(state.battleTimelineIndex);
    renderBattleFrame(state.battleMap);
  }, state.motionDisabled ? 1200 : 720);
}

const trainingParticipantKey = "local-user";
const trainingPhaseLabels = {
  opening: "开场",
  fundamentals: "基础事实",
  evidence: "证据追问",
  change: "风险变化",
  action: "行动计划",
  summary: "总结",
};

function safeHttpUrl(value) {
  const url = String(value || "").trim();
  return url.startsWith("https://") || url.startsWith("http://");
}

async function refreshTrainingCenter({ seed = false } = {}) {
  if (!el.trainingScenarioList) return null;
  if (seed) {
    if (el.trainingSeedButton) el.trainingSeedButton.disabled = true;
    try {
      await api("/api/training/scenarios/seed", {
        method: "POST",
        body: JSON.stringify({ actor: "training-curator" }),
      });
      showToast("已从真实项目刷新四类人工确认训练场景");
    } finally {
      if (el.trainingSeedButton) el.trainingSeedButton.disabled = false;
    }
  }
  let catalog = await api("/api/training/scenarios");
  if (!catalog.count) {
    await api("/api/training/scenarios/seed", {
      method: "POST",
      body: JSON.stringify({ actor: "training-curator" }),
    });
    catalog = await api("/api/training/scenarios");
  }
  state.trainingCatalog = catalog.items || [];
  const requested = new URLSearchParams(window.location.search).get("training_scenario") || "";
  const preferred = state.trainingSelectedScenarioId || requested;
  state.trainingSelectedScenarioId = state.trainingCatalog.some((item) => item.id === preferred)
    ? preferred
    : state.trainingCatalog[0]?.id || "";
  renderTrainingCatalog();
  selectTrainingScenario(state.trainingSelectedScenarioId, { renderList: false });
  await Promise.all([refreshTrainingHistory(), refreshTrainingTeamReadiness()]);
  return catalog;
}

function renderTrainingCatalog() {
  if (!el.trainingScenarioList) return;
  if (!state.trainingCatalog.length) {
    el.trainingScenarioList.className = "training-scenario-list empty-state";
    el.trainingScenarioList.textContent = "当前没有已批准训练场景";
    return;
  }
  el.trainingScenarioList.className = "training-scenario-list";
  el.trainingScenarioList.innerHTML = state.trainingCatalog.map((item, index) => `
    <button type="button" class="${item.id === state.trainingSelectedScenarioId ? "is-active" : ""}" data-training-scenario="${escapeHtml(item.id)}">
      <span>${String(index + 1).padStart(2, "0")} · ${escapeHtml(item.scenario_type_label)}</span>
      <strong>${escapeHtml(item.project_alias)}</strong>
      <small>${escapeHtml(item.target_roles.join(" / "))} · ${escapeHtml(item.question_count)} 问 · 约 ${escapeHtml(item.estimated_minutes)} 分钟</small>
      <em>${escapeHtml(item.approval_status === "approved" ? "人工确认" : item.approval_status)}</em>
    </button>`).join("");
}

function selectTrainingScenario(scenarioId, { renderList = true } = {}) {
  const scenario = state.trainingCatalog.find((item) => item.id === scenarioId);
  if (!scenario) return;
  state.trainingSelectedScenarioId = scenario.id;
  if (el.trainingScenarioId) el.trainingScenarioId.value = scenario.id;
  if (el.trainingRole) {
    const previous = el.trainingRole.value;
    el.trainingRole.innerHTML = (scenario.target_roles || []).map((role) => `<option value="${escapeHtml(role)}">${escapeHtml(role)}</option>`).join("");
    if ((scenario.target_roles || []).includes(previous)) el.trainingRole.value = previous;
  }
  if (el.trainingHeaderState && !state.trainingSession) el.trainingHeaderState.textContent = scenario.scenario_type_label;
  if (el.trainingHeaderMeta && !state.trainingSession) el.trainingHeaderMeta.textContent = `${scenario.project_alias} · ${scenario.question_count} 问`;
  if (renderList) renderTrainingCatalog();
  renderTrainingEvidence(scenario);
}

function renderTrainingEvidence(scenario) {
  if (!el.trainingEvidenceList) return;
  const evidence = scenario?.source_snapshot?.allowed_evidence || [];
  if (!evidence.length) {
    el.trainingEvidenceList.className = "training-evidence-list empty-state";
    el.trainingEvidenceList.textContent = "当前场景没有允许证据";
    return;
  }
  el.trainingEvidenceList.className = "training-evidence-list";
  el.trainingEvidenceList.innerHTML = evidence.map((item) => `
    <article>
      <span>${escapeHtml(String(item.type || "evidence").toUpperCase())}</span>
      <strong>${escapeHtml(item.label || item.id)}</strong>
      <code>${escapeHtml(item.id)}</code>
      <small>${escapeHtml(item.locator || "来源位置待核验")}</small>
      ${safeHttpUrl(item.source_url) ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">打开原始证据</a>` : ""}
    </article>`).join("");
}

async function createTrainingFromForm(event) {
  event.preventDefault();
  const scenario = state.trainingCatalog.find((item) => item.id === el.trainingScenarioId?.value);
  if (!scenario) throw new Error("请先选择训练场景");
  if (el.trainingCreateButton) el.trainingCreateButton.disabled = true;
  try {
    state.trainingSession = await api("/api/training/sessions", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: scenario.id,
        mode: el.trainingMode?.value || "preparation",
        role: el.trainingRole?.value || scenario.target_roles?.[0] || "项目负责人",
        difficulty: el.trainingDifficulty?.value || "standard",
        participant_key: trainingParticipantKey,
        participant_display: el.trainingParticipant?.value.trim() || "现场主讲人",
        sample_kind: "live",
      }),
    });
    renderTrainingSession(state.trainingSession);
  } finally {
    if (el.trainingCreateButton) el.trainingCreateButton.disabled = false;
  }
}

async function beginCurrentTraining() {
  if (!state.trainingSession) return;
  state.trainingSession = await api(`/api/training/sessions/${encodeURIComponent(state.trainingSession.id)}/begin`, {
    method: "POST",
    body: JSON.stringify({ participant_key: trainingParticipantKey }),
  });
  renderTrainingSession(state.trainingSession);
}

async function submitCurrentTrainingAnswer(event) {
  event?.preventDefault();
  if (!state.trainingSession) return;
  const answer = document.querySelector("#trainingAnswer")?.value.trim() || "";
  if (!answer) throw new Error("请先输入回答");
  const refs = [...document.querySelectorAll("[data-training-evidence-ref]:checked")].map((item) => item.value);
  const button = document.querySelector("#trainingSubmitAnswer");
  if (button) button.disabled = true;
  try {
    state.trainingSession = await api(`/api/training/sessions/${encodeURIComponent(state.trainingSession.id)}/answer`, {
      method: "POST",
      body: JSON.stringify({ participant_key: trainingParticipantKey, answer, evidence_refs: refs }),
    });
    renderTrainingSession(state.trainingSession);
    if (state.trainingSession.status === "completed") {
      await Promise.all([refreshTrainingHistory(), refreshTrainingTeamReadiness()]);
      showToast("训练完成，五维报告和完整回放已生成");
    }
  } finally {
    if (button) button.disabled = false;
  }
}

async function requestTrainingHint() {
  if (!state.trainingSession) return;
  const hint = await api(`/api/training/sessions/${encodeURIComponent(state.trainingSession.id)}/hint`, {
    method: "POST",
    body: JSON.stringify({ participant_key: trainingParticipantKey }),
  });
  const output = document.querySelector("#trainingHintOutput");
  if (output) output.innerHTML = `<b>第 ${escapeHtml(hint.hint_level)} 层提示</b><span>${escapeHtml(hint.hint)}</span>`;
}

function renderTrainingSession(session) {
  if (!el.trainingStage) return;
  if (el.trainingHeaderState) {
    el.trainingHeaderState.textContent = session.status === "completed" ? "训练报告已生成" : session.status === "active" ? "训练进行中" : "会话已建立";
  }
  if (el.trainingHeaderMeta) el.trainingHeaderMeta.textContent = `${session.project_alias} · ${session.role} · ${session.mode === "learning" ? "学习模式" : "准备模式"}`;
  renderTrainingPhaseRail(session);
  stopTrainingTimer();
  if (session.status === "ready") {
    el.trainingReport.hidden = true;
    el.trainingStage.className = "training-stage is-ready";
    el.trainingStage.innerHTML = `<div class="training-ready-card"><span>SESSION READY</span><h2>${escapeHtml(session.scenario_title)}</h2><p>${escapeHtml(session.project_alias)}</p><dl><div><dt>角色</dt><dd>${escapeHtml(session.role)}</dd></div><div><dt>模式</dt><dd>${session.mode === "learning" ? "学习模式" : "准备模式"}</dd></div><div><dt>评分</dt><dd>${escapeHtml(session.scoring_version)}</dd></div></dl><button id="trainingBeginButton" class="primary-button" type="button">我准备好了</button><small>点击后开始计时并保存完整回放。</small></div>`;
    document.querySelector("#trainingBeginButton")?.addEventListener("click", () => beginCurrentTraining().catch(toastError("训练启动失败")));
    return;
  }
  if (session.status === "completed") {
    el.trainingStage.className = "training-stage is-complete";
    const turns = session.turns || [];
    el.trainingStage.innerHTML = `<div class="training-complete-banner"><span>TRAINING COMPLETE</span><strong>${escapeHtml(turns.length)} 轮连续追问已完成</strong><small>首次回答、证据引用、评分依据和模型候选均已进入匿名回放。</small></div>`;
    renderTrainingReport(session.result);
    return;
  }
  el.trainingReport.hidden = true;
  const current = session.current_question || {};
  const scenario = state.trainingCatalog.find((item) => item.id === session.scenario_id);
  const evidence = scenario?.source_snapshot?.allowed_evidence || [];
  const progress = Math.min(100, Math.round((Number(session.current_question_index || 0) / Math.max(1, Number(session.question_count || 1))) * 100));
  el.trainingStage.className = "training-stage is-active";
  el.trainingStage.innerHTML = `
    <div class="training-question-head">
      <div class="training-role-avatar">${escapeHtml(session.role.slice(0, 1))}</div>
      <div><span>${escapeHtml(trainingPhaseLabels[current.phase] || current.phase)} · 第 ${escapeHtml(current.sequence || 1)} 问</span><strong>${escapeHtml(session.role)}正在接受追问</strong></div>
      <time id="trainingTimer">00:00</time>
    </div>
    <div class="training-progress"><i style="width:${progress}%"></i><span>${progress}%</span></div>
    <blockquote>${escapeHtml(current.prompt || "正在生成下一问")}</blockquote>
    <form id="trainingAnswerForm" class="training-answer-form">
      <label><span>你的回答</span><textarea id="trainingAnswer" rows="7" maxlength="5000" placeholder="先给结论，再说明事实、证据、风险边界和下一步行动。" autofocus></textarea></label>
      <fieldset><legend>本轮引用证据（可多选）</legend>${evidence.slice(0, 8).map((item) => `<label><input type="checkbox" data-training-evidence-ref value="${escapeHtml(item.id)}" /><span><b>${escapeHtml(item.id)}</b>${escapeHtml(item.label)}</span></label>`).join("")}</fieldset>
      <div id="trainingHintOutput" class="training-hint-output" ${session.mode === "learning" ? "" : "hidden"}></div>
      <div class="training-answer-actions">
        ${session.mode === "learning" ? '<button id="trainingHintButton" class="ghost-button" type="button">给我一层提示</button>' : '<small>准备模式：提交前不展示完整参考答案</small>'}
        <button id="trainingSubmitAnswer" class="primary-button" type="submit">提交回答并接受追问</button>
      </div>
    </form>`;
  document.querySelector("#trainingAnswerForm")?.addEventListener("submit", (event) => submitCurrentTrainingAnswer(event).catch(toastError("回答提交失败")));
  document.querySelector("#trainingHintButton")?.addEventListener("click", () => requestTrainingHint().catch(toastError("提示加载失败")));
  startTrainingTimer(session.started_at);
}

function renderTrainingPhaseRail(session) {
  if (!el.trainingPhaseRail) return;
  const phases = Object.keys(trainingPhaseLabels);
  const activeIndex = phases.indexOf(session.current_phase);
  el.trainingPhaseRail.querySelectorAll("[data-training-phase]").forEach((item, index) => {
    item.classList.toggle("is-complete", session.status === "completed" || index < activeIndex);
    item.classList.toggle("is-active", session.status !== "completed" && index === activeIndex);
  });
}

function renderTrainingReport(result) {
  if (!el.trainingReport || !result) return;
  const labels = result.dimension_labels || {};
  const scores = result.dimension_scores || {};
  const replayTurns = result.replay?.turns || [];
  el.trainingReport.hidden = false;
  el.trainingReport.innerHTML = `
    <header><div><span>FIVE-DIMENSION REPORT</span><h2>准备度 ${escapeHtml(result.total_score)} / 100</h2><p>${escapeHtml(trainingReadinessLabel(result.readiness_level))} · 评分版本 ${escapeHtml(result.scoring_version)}</p></div><div class="training-score-ring" style="--score:${Number(result.total_score || 0)}"><b>${escapeHtml(result.total_score)}</b><small>总分</small></div></header>
    <div class="training-dimension-grid">${Object.entries(labels).map(([key, label]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(scores[key] ?? 0)}</strong><i><b style="width:${Number(scores[key] || 0)}%"></b></i></article>`).join("")}</div>
    <div class="training-report-grid">
      <section><h3>薄弱点与补强任务</h3><div class="training-task-list">${(result.remediation_tasks || []).length ? result.remediation_tasks.map((task) => `<article><div><b>${escapeHtml(task.title)}</b><span>${escapeHtml(task.basis)}</span></div><button type="button" data-training-sync-task="${escapeHtml(task.id)}" data-result-id="${escapeHtml(result.id)}">${task.feishu_task_guid ? "已同步飞书" : "同步飞书任务"}</button></article>`).join("") : '<p class="empty-state">本轮没有低于 70 分的维度</p>'}</div></section>
      <section><h3>可复算与边界</h3><dl><div><dt>评分哈希</dt><dd>${escapeHtml(String(result.score_hash || "").slice(0, 18))}</dd></div><div><dt>模型状态</dt><dd>${escapeHtml(result.model_review_status)}</dd></div><div><dt>正式项目写入</dt><dd>${escapeHtml(result.replay?.formal_project_write_count || 0)} 次</dd></div><div><dt>匿名回放</dt><dd>${result.anonymized ? "已开启" : "未开启"}</dd></div></dl><button id="trainingRecomputeButton" class="ghost-button" type="button" data-result-id="${escapeHtml(result.id)}">重新复算结果</button><output id="trainingRecomputeOutput"></output></section>
    </div>
    <details class="training-replay"><summary>展开完整训练回放 · ${escapeHtml(replayTurns.length)} 轮</summary><div>${replayTurns.map((turn) => `<article><span>${escapeHtml(trainingPhaseLabels[turn.phase] || turn.phase)} · ${escapeHtml(turn.question_id)}</span><strong>${escapeHtml(turn.prompt)}</strong><p>${escapeHtml(turn.first_answer)}</p><small>证据 ${escapeHtml((turn.evidence_refs || []).join("、") || "未引用")} · 规则得分 ${escapeHtml(turn.score?.total ?? 0)}</small></article>`).join("")}</div></details>`;
  el.trainingReport.querySelectorAll("[data-training-sync-task]").forEach((button) => {
    button.addEventListener("click", () => syncTrainingTask(button).catch(toastError("飞书补强任务同步失败")));
  });
  document.querySelector("#trainingRecomputeButton")?.addEventListener("click", () => recomputeCurrentTrainingResult(result.id).catch(toastError("训练结果复算失败")));
}

function trainingReadinessLabel(value) {
  return { ready: "已准备", nearly_ready: "接近准备完成", needs_practice: "需要继续练习" }[value] || value;
}

async function recomputeCurrentTrainingResult(resultId) {
  const payload = await api(`/api/training/results/${encodeURIComponent(resultId)}/recompute`, { method: "POST", body: "{}" });
  const output = document.querySelector("#trainingRecomputeOutput");
  if (output) output.textContent = payload.identical ? `复算一致 · ${String(payload.recomputed_hash).slice(0, 12)}` : "复算结果不一致，需要人工检查";
}

async function syncTrainingTask(button) {
  if (!button || button.disabled) return;
  button.disabled = true;
  try {
    const payload = await api(`/api/training/results/${encodeURIComponent(button.dataset.resultId)}/tasks/${encodeURIComponent(button.dataset.trainingSyncTask)}/sync-feishu`, { method: "POST", body: "{}" });
    button.textContent = payload.status === "reused" ? "飞书任务已存在" : "飞书任务已创建";
    showToast(`飞书补强任务${payload.status === "reused" ? "已复用" : "已创建"}`);
  } finally {
    button.disabled = false;
  }
}

async function refreshTrainingHistory() {
  if (!el.trainingHistory) return;
  const payload = await api(`/api/training/sessions?participant_key=${encodeURIComponent(trainingParticipantKey)}`);
  const items = payload.items || [];
  if (!items.length) {
    el.trainingHistory.className = "training-history empty-state";
    el.trainingHistory.textContent = "暂无训练记录";
    return;
  }
  el.trainingHistory.className = "training-history";
  el.trainingHistory.innerHTML = items.map((item) => `<button type="button" data-training-session="${escapeHtml(item.id)}"><span>${escapeHtml(item.status === "completed" ? "已完成" : item.status === "active" ? "进行中" : "待开始")}</span><strong>${escapeHtml(item.role)} · ${escapeHtml(item.mode === "learning" ? "学习模式" : "准备模式")}</strong><small>${escapeHtml(compactDateTimeText(item.created_at) || item.created_at)}</small></button>`).join("");
}

async function refreshTrainingTeamReadiness() {
  if (!el.trainingTeamReadiness) return;
  const payload = await api("/api/training/team-readiness");
  if (!payload.completed_session_count) {
    el.trainingTeamReadiness.className = "training-team-readiness empty-state";
    el.trainingTeamReadiness.textContent = "暂无真人或人工验证训练结果；自动基准样本不计入团队准备度。";
    return;
  }
  el.trainingTeamReadiness.className = "training-team-readiness";
  el.trainingTeamReadiness.innerHTML = `<div class="training-team-metrics"><strong>${escapeHtml(payload.participant_count)}<small>参与者</small></strong><strong>${escapeHtml(payload.completed_session_count)}<small>完成场次</small></strong>${Object.entries(payload.dimension_averages || {}).map(([key, value]) => `<strong>${value === null ? "-" : escapeHtml(value)}<small>${escapeHtml({ fact_accuracy: "事实", evidence_citation: "证据", risk_awareness: "风险", action_completeness: "行动", expression_clarity: "表达" }[key] || key)}</small></strong>`).join("")}</div><div class="training-team-weaknesses">${(payload.common_weaknesses || []).map((item) => `<span>${escapeHtml(item.label)} · ${escapeHtml(item.count)}</span>`).join("") || "当前没有共同薄弱点"}</div><p>${escapeHtml(payload.privacy_note)} ${escapeHtml(payload.sample_limit)}</p>`;
}

async function loadTrainingSession(sessionId) {
  state.trainingSession = await api(`/api/training/sessions/${encodeURIComponent(sessionId)}?participant_key=${encodeURIComponent(trainingParticipantKey)}`);
  state.trainingSelectedScenarioId = state.trainingSession.scenario_id;
  renderTrainingCatalog();
  selectTrainingScenario(state.trainingSelectedScenarioId, { renderList: false });
  renderTrainingSession(state.trainingSession);
}

function startTrainingTimer(startedAt) {
  stopTrainingTimer();
  const started = Date.parse(startedAt || new Date().toISOString());
  const update = () => {
    const node = document.querySelector("#trainingTimer");
    if (!node) return;
    const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
    node.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  update();
  state.trainingTimer = window.setInterval(update, 1000);
}

function stopTrainingTimer() {
  if (state.trainingTimer) window.clearInterval(state.trainingTimer);
  state.trainingTimer = null;
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
  renderFeishuDeliveryWorkspaceOptions();
  renderOrganizationSummary();
  await Promise.all([refreshOrganizationMemories(), refreshBidMemory()]);
}

async function refreshBidMemory(noticeId = null) {
  if (!el.bidMemoryDashboard) return null;
  if (!state.organizationWorkspaceId) {
    state.bidMemory = null;
    el.bidMemoryDashboard.className = "bid-memory-dashboard empty-state";
    el.bidMemoryDashboard.textContent = "选择协作空间后加载企业投标记忆体";
    return null;
  }
  const targetNoticeId = noticeId === null
    ? (el.bidMemoryTargetNoticeId?.value.trim() || new URLSearchParams(window.location.search).get("memory_notice")?.trim() || "")
    : String(noticeId || "").trim();
  if (el.bidMemoryTargetNoticeId && noticeId !== null) el.bidMemoryTargetNoticeId.value = targetNoticeId;
  const params = new URLSearchParams({ actor: "admin" });
  if (targetNoticeId) params.set("notice_id", targetNoticeId);
  const payload = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/bid-memory?${params}`);
  state.bidMemory = payload;
  state.bidMemorySelectedNodeId = payload.graph?.nodes?.[0]?.id || "";
  renderBidMemory(payload);
  return payload;
}

function renderBidMemory(payload) {
  if (!el.bidMemoryDashboard) return;
  const access = payload.access || {};
  if (!access.granted) {
    el.bidMemoryDashboard.className = "bid-memory-dashboard is-denied";
    el.bidMemoryDashboard.innerHTML = `<div class="bid-memory-access-denied"><b>权限边界生效</b><span>${escapeHtml(access.message || "当前账号无权查看该组织空间")}</span></div>`;
    return;
  }
  const summary = payload.summary || {};
  const sample = payload.sample || {};
  const recommendations = Array.isArray(payload.recommendations) ? payload.recommendations : [];
  const assets = Array.isArray(payload.assets) ? payload.assets : [];
  const audit = Array.isArray(payload.audit) ? payload.audit : [];
  el.bidMemoryDashboard.className = "bid-memory-dashboard";
  el.bidMemoryDashboard.innerHTML = `
    <div class="bid-memory-metrics">
      ${bidMemoryMetric("历史项目", summary.project_count || 0, `中标 ${summary.won_count || 0} · 未中标 ${summary.lost_count || 0}`)}
      ${bidMemoryMetric("经验资产", summary.asset_count || 0, `权限隐藏 ${summary.hidden_sensitive_count || 0}`)}
      ${bidMemoryMetric("可直接复用", summary.reusable_count || 0, "均保留来源与版本")}
      ${bidMemoryMetric("需处理", Number(summary.update_needed_count || 0) + Number(summary.expired_count || 0), `需更新 ${summary.update_needed_count || 0} · 已过期 ${summary.expired_count || 0}`)}
    </div>
    <div class="bid-memory-sample ${sample.reliable ? "is-reliable" : "is-insufficient"}">
      <div><i>${sample.reliable ? "✓" : "!"}</i><span><strong>${escapeHtml(sample.label || "暂无可靠经验")}</strong><small>${escapeHtml(sample.message || "只提供可追溯参考，不生成胜率。")}</small></span></div>
      <em>样本 ${escapeHtml(sample.count || 0)} · 永不生成伪胜率</em>
    </div>
    <div class="bid-memory-stage">
      <section class="bid-memory-graph-panel">
        <div class="bid-memory-section-title"><div><strong>企业经验关系图谱</strong><span>点击节点查看来源、版本、状态和人工记录</span></div><small>${escapeHtml(payload.graph?.nodes?.length || 0)} 节点 · ${escapeHtml(payload.graph?.edges?.length || 0)} 关系</small></div>
        ${renderBidMemoryGraph(payload.graph || {})}
        <div class="bid-memory-legend">${(payload.graph?.legend || []).map((item) => `<span class="type-${escapeHtml(item.type)}"><i></i>${escapeHtml(item.label)}</span>`).join("")}</div>
      </section>
      <aside class="bid-memory-inspector" data-bid-memory-inspector>${renderBidMemoryInspector(payload, state.bidMemorySelectedNodeId)}</aside>
    </div>
    <section class="bid-memory-recommendations">
      <div class="bid-memory-section-title"><div><strong>相似项目与经验推荐</strong><span>结构化字段与文本相似度共同检索，成功和失败案例同时显示</span></div><small>${recommendations.length} 个来源项目</small></div>
      <div class="bid-memory-recommendation-grid">${recommendations.length ? recommendations.map(renderBidMemoryRecommendation).join("") : `<div class="bid-memory-empty"><b>暂无可靠经验</b><span>先完成历史项目复盘，系统才会提供有来源的相似经验。</span></div>`}</div>
    </section>
    <section class="bid-memory-assets">
      <div class="bid-memory-section-title"><div><strong>经验资产状态</strong><span>可复用、需更新、仅供参考、已过期和已失效分别管理</span></div><small>${assets.length} 项可见</small></div>
      <div class="bid-memory-asset-board">${["reusable", "update_needed", "reference", "expired"].map((status) => renderBidMemoryAssetLane(status, assets.filter((item) => item.effective_status === status))).join("")}</div>
    </section>
    <section class="bid-memory-audit">
      <div class="bid-memory-section-title"><div><strong>人工确认与修改记录</strong><span>确认、纠正、撤回和项目归档全部留痕</span></div><small>${audit.length} 条</small></div>
      <div>${audit.slice(0, 12).map((item) => `<span><i></i><b>${escapeHtml(bidMemoryAuditLabel(item.action))}</b><small>${escapeHtml(item.actor || "系统")} · ${escapeHtml(compactDateTimeText(item.created_at || ""))}</small><em>${escapeHtml(item.note || "已记录")}</em></span>`).join("") || "<p>暂无人工操作记录</p>"}</div>
    </section>`;
}

function bidMemoryMetric(label, value, detail) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
}

function renderBidMemoryGraph(graph) {
  const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const nodes = rawNodes.slice(0, 24);
  if (!nodes.length) return `<div class="bid-memory-graph-empty"><b>等待历史项目进入记忆体</b><span>完成项目复盘并归档后，关系网络会在这里形成。</span></div>`;
  const positions = {};
  const target = nodes.find((item) => item.type === "target") || nodes[0];
  positions[target.id] = { x: 500, y: 245 };
  const projects = nodes.filter((item) => item.type === "project");
  const others = nodes.filter((item) => item.id !== target.id && item.type !== "project");
  projects.forEach((item, index) => {
    const angle = (Math.PI * 2 * index / Math.max(projects.length, 1)) - Math.PI / 2;
    positions[item.id] = { x: 500 + Math.cos(angle) * 250, y: 245 + Math.sin(angle) * 135 };
  });
  others.forEach((item, index) => {
    const angle = (Math.PI * 2 * index / Math.max(others.length, 1)) - Math.PI / 2 + 0.18;
    positions[item.id] = { x: 500 + Math.cos(angle) * 430, y: 245 + Math.sin(angle) * 205 };
  });
  const visibleIds = new Set(nodes.map((item) => item.id));
  const edges = (graph.edges || []).filter((item) => visibleIds.has(item.source) && visibleIds.has(item.target));
  return `<div class="bid-memory-graph">
    <svg viewBox="0 0 1000 490" preserveAspectRatio="none" aria-hidden="true">${edges.map((edge) => {
      const source = positions[edge.source]; const targetPosition = positions[edge.target];
      return `<g><line x1="${source.x}" y1="${source.y}" x2="${targetPosition.x}" y2="${targetPosition.y}"></line><text x="${(source.x + targetPosition.x) / 2}" y="${(source.y + targetPosition.y) / 2 - 4}">${escapeHtml(edge.label || "关联")}</text></g>`;
    }).join("")}</svg>
    ${nodes.map((item) => {
      const point = positions[item.id];
      return `<button type="button" class="bid-memory-node type-${escapeHtml(item.type)} ${item.id === state.bidMemorySelectedNodeId ? "is-selected" : ""}" data-bid-memory-node="${escapeHtml(item.id)}" style="--node-x:${point.x / 10}%;--node-y:${point.y / 4.9}%"><i></i><strong>${escapeHtml(item.label || item.type)}</strong><small>${escapeHtml(item.subtitle || bidMemoryNodeLabel(item.type))}</small></button>`;
    }).join("")}
  </div>`;
}

function renderBidMemoryInspector(payload, nodeId) {
  const node = (payload.graph?.nodes || []).find((item) => item.id === nodeId) || payload.graph?.nodes?.[0];
  if (!node) return `<div class="bid-memory-inspector-empty">点击图谱节点查看完整来源</div>`;
  const asset = node.id.startsWith("asset:") ? (payload.assets || []).find((item) => `asset:${item.id}` === node.id) : null;
  const project = node.id.startsWith("project:") ? (payload.projects || []).find((item) => `project:${item.id}` === node.id) : null;
  if (asset) return `
    <span class="bid-memory-inspector-kicker">${escapeHtml(asset.asset_type_label || "经验资产")}</span>
    <h3>${escapeHtml(asset.title)}</h3>
    <p>${escapeHtml(asset.content)}</p>
    <dl><div><dt>状态</dt><dd>${escapeHtml(bidMemoryStatusLabel(asset.effective_status))}</dd></div><div><dt>版本</dt><dd>v${escapeHtml(asset.version_number || 1)}</dd></div><div><dt>有效期</dt><dd>${escapeHtml(asset.valid_until || "长期")}</dd></div><div><dt>确认人</dt><dd>${escapeHtml(asset.confirmed_by || "待人工确认")}</dd></div></dl>
    <div class="bid-memory-inspector-actions">${asset.source_url ? `<a href="${escapeHtml(asset.source_url)}" target="_blank" rel="noreferrer">打开来源</a>` : ""}<button type="button" data-bid-memory-asset-action="confirm" data-asset-id="${escapeHtml(asset.id)}">确认可复用</button><button type="button" data-bid-memory-asset-action="correct" data-asset-id="${escapeHtml(asset.id)}">纠正</button><button type="button" data-bid-memory-asset-action="withdraw" data-asset-id="${escapeHtml(asset.id)}">撤回</button></div>`;
  if (project) return `
    <span class="bid-memory-inspector-kicker">历史来源项目</span><h3>${escapeHtml(project.title)}</h3>
    <p>${escapeHtml(project.summary || "")}</p><blockquote>${escapeHtml(project.lessons || "暂无复盘")}</blockquote>
    <dl><div><dt>最终结果</dt><dd>${project.outcome_result === "won" ? "中标" : "未中标"}</dd></div><div><dt>地区</dt><dd>${escapeHtml(project.region || "-")}</dd></div><div><dt>采购主体</dt><dd>${escapeHtml(project.purchaser || "-")}</dd></div><div><dt>归档时间</dt><dd>${escapeHtml(project.finalized_at || "-")}</dd></div></dl>
    ${project.source_url ? `<a class="bid-memory-source-link" href="${escapeHtml(project.source_url)}" target="_blank" rel="noreferrer">回查来源项目 ↗</a>` : ""}`;
  return `<span class="bid-memory-inspector-kicker">${escapeHtml(bidMemoryNodeLabel(node.type))}</span><h3>${escapeHtml(node.label || "关系节点")}</h3><p>该节点来自当前组织空间的已归档项目关系。选择历史项目或经验资产可查看来源、版本、有效期和人工记录。</p>`;
}

function renderBidMemoryRecommendation(item) {
  const assets = Array.isArray(item.reusable_assets) ? item.reusable_assets : [];
  const warnings = Array.isArray(item.warnings) ? item.warnings : [];
  return `<article class="bid-memory-recommendation result-${escapeHtml(item.result || "unknown")}">
    <header><span>${item.result === "won" ? "中标经验" : "失败教训"}</span><strong>${escapeHtml(item.similarity_score || 0)}</strong><small>相似度</small></header>
    <h3>${escapeHtml(item.source_title || "历史项目")}</h3>
    <p>${(item.reasons || []).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}</p>
    <div class="bid-memory-reuse-chips">${assets.slice(0, 3).map((asset) => `<b>可复用 · ${escapeHtml(asset.title)}</b>`).join("")}${warnings.slice(0, 3).map((asset) => `<em>${asset.asset_type === "gap" ? "历史缺口" : bidMemoryStatusLabel(asset.effective_status)} · ${escapeHtml(asset.title)}</em>`).join("")}</div>
    <footer><span>人工确认 ${escapeHtml(item.human_confirmed_count || 0)} 项 · ${escapeHtml(compactDateTimeText(item.finalized_at || ""))}</span>${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">查看来源</a>` : ""}</footer>
  </article>`;
}

function renderBidMemoryAssetLane(status, items) {
  return `<div class="bid-memory-asset-lane status-${status}"><header><strong>${escapeHtml(bidMemoryStatusLabel(status))}</strong><span>${items.length}</span></header><div>${items.slice(0, 8).map((item) => `<button type="button" data-bid-memory-node="asset:${escapeHtml(item.id)}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.asset_type_label)} · v${escapeHtml(item.version_number || 1)}${item.valid_until ? ` · ${escapeHtml(item.valid_until)}` : ""}</small></button>`).join("") || "<p>暂无</p>"}</div></div>`;
}

function bidMemoryStatusLabel(status) {
  return { reusable: "可直接复用", update_needed: "需更新", reference: "仅供参考", expired: "已过期", invalid: "已失效" }[status] || status || "待确认";
}

function bidMemoryNodeLabel(type) {
  return { target: "当前机会", project: "历史项目", customer: "客户", region: "地区", category: "品类", requirement: "要求", material: "材料", evidence: "证据", lesson: "复盘", task: "任务", gap: "缺口", competitor: "竞争", decision: "决策", outcome: "结果" }[type] || type || "关系";
}

function bidMemoryAuditLabel(action) {
  return { project_archived: "项目进入记忆体", asset_confirm: "确认可复用", asset_correct: "纠正经验", asset_withdraw: "撤回经验" }[action] || action || "记忆已更新";
}

async function loadOpportunityBidMemoryPreview(noticeId) {
  const container = currentOpportunityBidMemoryContainer(noticeId);
  if (!container) return;
  if (!state.organizationWorkspaceId) {
    container.innerHTML = `<span>选择组织协作空间后，可查看相似项目、成功材料和历史缺口。</span>`;
    return;
  }
  const params = new URLSearchParams({ actor: "admin", notice_id: noticeId });
  const payload = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/bid-memory?${params}`);
  const recommendations = payload.recommendations || [];
  container.innerHTML = `<div><strong>${recommendations.length ? `找到 ${recommendations.length} 个相似历史项目` : "暂无可靠经验"}</strong><small>${escapeHtml(payload.sample?.message || "只提供可追溯参考，不生成胜率。")}</small></div><button type="button" data-open-bid-memory="${escapeHtml(noticeId)}">打开企业记忆图谱</button>`;
}

function currentOpportunityBidMemoryContainer(noticeId) {
  const container = el.opportunityDetailContent?.querySelector("[data-opportunity-bid-memory]");
  return container?.dataset.opportunityBidMemory === noticeId ? container : null;
}

function openBidMemoryArchiveDialog(noticeId) {
  if (!state.organizationWorkspaceId) throw new Error("请先选择组织协作空间");
  state.pendingBidMemoryArchiveNoticeId = noticeId;
  el.bidMemoryArchiveForm?.reset();
  const opportunity = state.opportunities.find((item) => item.notice_id === noticeId || item.id === noticeId);
  if (el.bidMemoryArchiveProject) el.bidMemoryArchiveProject.textContent = opportunity?.title || noticeId;
  if (el.bidMemoryArchiveStatus) el.bidMemoryArchiveStatus.textContent = "系统会保留来源、版本、有效期和操作记录；过期材料不会被标记为可直接复用。";
  if (!el.bidMemoryArchiveDialog?.open) el.bidMemoryArchiveDialog?.showModal();
}

function closeBidMemoryArchiveDialog() {
  el.bidMemoryArchiveDialog?.close();
}

async function archiveOpportunityToBidMemory(event) {
  event?.preventDefault();
  const noticeId = state.pendingBidMemoryArchiveNoticeId;
  if (!state.organizationWorkspaceId) throw new Error("请先选择组织协作空间");
  if (!noticeId) throw new Error("缺少待归档项目");
  const materialTitle = el.bidMemoryArchiveMaterialTitle?.value.trim() || "";
  const materialContent = el.bidMemoryArchiveMaterialContent?.value.trim() || "";
  if (Boolean(materialTitle) !== Boolean(materialContent)) throw new Error("可复用材料名称和内容需要同时填写");
  const tags = (el.bidMemoryArchiveTags?.value || "").split(/[，,]/).map((item) => item.trim()).filter(Boolean);
  const materials = materialTitle ? [{
    asset_type: "material", title: materialTitle, content: materialContent,
    valid_until: el.bidMemoryArchiveValidUntil?.value || "", reuse_status: "update_needed",
    permission_scope: el.bidMemoryArchivePermission?.value || "workspace",
    sensitivity: el.bidMemoryArchiveSensitivity?.value || "normal",
  }] : [];
  if (el.submitBidMemoryArchiveButton) el.submitBidMemoryArchiveButton.disabled = true;
  await api(`/api/opportunities/${encodeURIComponent(noticeId)}/bid-memory/archive`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: state.organizationWorkspaceId, actor: "admin", tags, materials }),
  });
  closeBidMemoryArchiveDialog();
  await Promise.all([refreshBidMemory(noticeId), loadOpportunityBidMemoryPreview(noticeId)]);
  showToast("项目要求、材料、缺口、决策与复盘已进入企业投标记忆体");
  if (el.submitBidMemoryArchiveButton) el.submitBidMemoryArchiveButton.disabled = false;
}

async function decideBidMemoryAsset(button) {
  const action = button.dataset.bidMemoryAssetAction || "";
  const assetId = button.dataset.assetId || "";
  const note = window.prompt(action === "confirm" ? "请填写确认依据" : action === "withdraw" ? "请填写撤回原因" : "请填写纠正说明", "");
  if (note === null) return;
  if (!note.trim()) throw new Error("人工处理说明不能为空");
  const body = { action, actor: "admin", note: note.trim(), corrections: {} };
  if (action === "correct") {
    const current = (state.bidMemory?.assets || []).find((item) => item.id === assetId);
    const content = window.prompt("请输入纠正后的经验内容", current?.content || "");
    if (content === null) return;
    body.corrections = { content: content.trim(), reuse_status: "update_needed" };
  }
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/bid-memory/assets/${encodeURIComponent(assetId)}/decision`, { method: "POST", body: JSON.stringify(body) });
  await refreshBidMemory();
  showToast({ confirm: "经验已确认可复用", correct: "经验已纠正并生成新版本", withdraw: "经验已撤回" }[action] || "经验已更新");
}

async function refreshPartnerWorkspaceOptions() {
  if (!state.organizationWorkspaces.length) {
    const payload = await api("/api/organization/workspaces");
    state.organizationWorkspaces = payload.items || [];
  }
  if (!state.organizationWorkspaceId && state.organizationWorkspaces.length) {
    state.organizationWorkspaceId = state.organizationWorkspaces[0].id;
  }
  if (!el.partnerWorkspaceSelect) return;
  el.partnerWorkspaceSelect.innerHTML = state.organizationWorkspaces.length
    ? state.organizationWorkspaces.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("")
    : '<option value="">暂无组织空间</option>';
  el.partnerWorkspaceSelect.value = state.organizationWorkspaceId;
}

async function refreshPartnerEntities() {
  const workspaceId = el.partnerWorkspaceSelect?.value || state.organizationWorkspaceId;
  if (!workspaceId) {
    state.partnerEntities = [];
    renderPartnerEntities();
    return;
  }
  state.organizationWorkspaceId = workspaceId;
  const params = new URLSearchParams({ actor: "admin" });
  const query = el.partnerSearchInput?.value.trim() || "";
  if (query) params.set("query", query);
  const payload = await api(`/api/organization/workspaces/${encodeURIComponent(workspaceId)}/companies?${params}`);
  state.partnerEntities = payload.items || [];
  if (!state.partnerEntities.some((item) => item.id === state.partnerEntityId)) {
    state.partnerEntityId = state.partnerEntities[0]?.id || "";
  }
  renderPartnerEntities();
  if (state.partnerEntityId) await openPartnerProfile(state.partnerEntityId);
  else {
    state.partnerProfile = null;
    renderPartnerProfile();
  }
}

function renderPartnerEntities() {
  if (el.partnerEntityCount) el.partnerEntityCount.textContent = `${state.partnerEntities.length} 家`;
  if (!el.partnerEntityList) return;
  if (!state.partnerEntities.length) {
    el.partnerEntityList.className = "partner-entity-list empty-state";
    el.partnerEntityList.textContent = state.organizationWorkspaceId ? "尚未建立合作方主体，可从上方新增。" : "请选择组织空间";
    return;
  }
  el.partnerEntityList.className = "partner-entity-list";
  el.partnerEntityList.innerHTML = state.partnerEntities.map((item) => `
    <button class="partner-entity-button ${item.id === state.partnerEntityId ? "active" : ""}" type="button" data-partner-entity="${escapeHtml(item.id)}">
      <strong>${escapeHtml(item.legal_name)}</strong>
      <span>${escapeHtml(item.region || "地区待确认")} · ${item.identity_status === "confirmed" ? "主体已确认" : "待主体消歧"}</span>
      <small>${escapeHtml(item.unified_credit_code_masked || "统一代码待补充")}</small>
    </button>`).join("");
}

async function openPartnerProfile(entityId) {
  if (!entityId || !state.organizationWorkspaceId) return;
  state.partnerEntityId = entityId;
  renderPartnerEntities();
  state.partnerProfile = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(entityId)}?actor=admin`);
  renderPartnerProfile();
}

function renderPartnerProfile() {
  if (!el.partnerProfile) return;
  const payload = state.partnerProfile;
  if (!payload) {
    el.partnerProfile.className = "partner-profile empty-state";
    el.partnerProfile.textContent = "选择合作方后查看六维画像、风险证据和尽调任务。";
    return;
  }
  const entity = payload.entity || {};
  const summary = payload.summary || {};
  const review = payload.current_review || null;
  const recommendationLabels = { pending: "待人工结论", cooperate: "合作", conditional: "有条件合作", pause: "暂停", reject: "拒绝" };
  const riskLabels = { critical: "高风险", warning: "需关注", pending: "待补证", clear: "未见有效风险" };
  const risks = (payload.risk_summary?.risks || []).filter((item) => ["active", "needs_review"].includes(item.signal_status));
  const missing = payload.risk_summary?.missing || [];
  const evidence = payload.evidence || [];
  const tasks = payload.tasks || [];
  const relationships = payload.relationships || [];
  el.partnerProfile.className = "partner-profile";
  el.partnerProfile.innerHTML = `
    <section class="partner-profile-hero">
      <div class="partner-profile-title"><span class="section-kicker">VERIFIED PARTNER PORTRAIT</span><h2>${escapeHtml(entity.legal_name || "合作方")}</h2><p>${escapeHtml(entity.region || "地区待确认")} · ${escapeHtml(entity.unified_credit_code_masked || "统一社会信用代码待补充")} · ${entity.verification_status === "official_verified" ? "官方已核验" : entity.identity_status === "confirmed" ? "人工已确认" : "待主体消歧"}</p></div>
      <div class="partner-metric"><span>合作建议</span><strong>${escapeHtml(recommendationLabels[summary.recommendation] || summary.recommendation || "待确认")}</strong></div>
      <div class="partner-metric"><span>风险等级</span><strong>${escapeHtml(riskLabels[summary.risk_level] || summary.risk_level || "待评估")}</strong></div>
      <div class="partner-metric"><span>证据完整度</span><strong>${escapeHtml(summary.evidence_completeness || 0)}%</strong></div>
      <div class="partner-metric"><span>人工复核</span><strong>${review ? `${escapeHtml(review.confirmed_by)} · ${escapeHtml(review.valid_until)}` : "待确认"}</strong></div>
    </section>
    <section class="partner-section"><header><div><span class="section-kicker">SIX DIMENSIONS</span><h3>六维企业画像</h3></div><small>缺失信息独立显示，不按负面风险计算</small></header><div class="partner-dimensions">${(payload.dimensions || []).map((item) => `<article class="partner-dimension state-${escapeHtml(item.state)}"><header><strong>${escapeHtml(item.label)}</strong><span class="badge badge-${item.state === "risk" ? "failed" : item.state === "covered" ? "finished" : "muted"}">${item.state === "risk" ? "有风险" : item.state === "covered" ? "已覆盖" : "待补证"}</span></header><p>证据 ${escapeHtml(item.evidence_count)} · 风险 ${escapeHtml(item.risk_count)} · 缺口 ${escapeHtml(item.missing_count)}</p></article>`).join("")}</div></section>
    <section class="partner-section"><header><div><span class="section-kicker">RISK CARDS</span><h3>风险解释卡</h3></div><small>${risks.length} 条风险 · ${missing.length} 个缺口</small></header><div class="partner-risk-list">${risks.length ? risks.map(renderPartnerRiskCard).join("") : '<div class="empty-state">当前没有有效负面风险证据；请继续核验缺失维度。</div>'}${missing.length ? `<article class="partner-risk-card"><header><strong>待确认清单</strong><span class="badge badge-muted">缺失不等于负面</span></header><p>${missing.slice(0, 6).map((item) => escapeHtml(item.fact_signal)).join("；")}</p></article>` : ""}</div></section>
    <section class="partner-section"><header><div><span class="section-kicker">RELATION GRAPH</span><h3>事实、推断与人工关系</h3></div><small>${relationships.length} 条关系</small></header><div class="partner-relation-list">${relationships.length ? relationships.map((item) => `<article class="partner-relation-card"><strong>${escapeHtml(item.related_label)}</strong><span class="badge badge-muted">${escapeHtml({ factual: "事实", inferred: "推断", manual: "人工" }[item.basis_type] || item.basis_type)}</span><small>${escapeHtml(item.relationship_type)} · 置信度 ${escapeHtml(item.confidence)}${item.evidence_id ? ` · 证据 ${escapeHtml(item.evidence_id)}` : ""}</small></article>`).join("") : '<div class="empty-state">尚无关系边；新增关系时会明确事实、推断或人工依据。</div>'}</div></section>
    <section class="partner-section"><header><div><span class="section-kicker">EVIDENCE LEDGER</span><h3>企业证据账本</h3></div><small>${evidence.length} 条 · 最近更新 ${escapeHtml(summary.last_updated_at || "-")}</small></header><div class="partner-evidence-list">${evidence.length ? evidence.slice(0, 12).map(renderPartnerEvidenceCard).join("") : '<div class="empty-state">暂无企业证据，请先聚合本地证据或上传授权材料。</div>'}</div></section>
    <section class="partner-section"><header><div><span class="section-kicker">FEISHU TASK RECEIPTS</span><h3>尽调任务与飞书回执</h3></div><small>${tasks.length} 项</small></header><div class="partner-task-list">${tasks.length ? tasks.map(renderPartnerTaskCard).join("") : '<div class="empty-state">暂无尽调任务；风险卡中的问题可分派给法务、财务、销售或交付。</div>'}</div></section>`;
}

function renderPartnerRiskCard(item) {
  return `<article class="partner-risk-card ${item.severity === "critical" ? "critical" : ""}"><header><strong>${escapeHtml(item.risk_interpretation)}</strong><span class="badge badge-${item.deterministic ? "failed" : "muted"}">${item.deterministic ? "已核验" : "待复核"} · ${escapeHtml(item.confidence)}</span></header><p>${escapeHtml(item.fact_signal)}</p><div class="partner-risk-grid"><div><strong>业务影响</strong>${escapeHtml(item.business_impact)}</div><div><strong>必须追问</strong>${escapeHtml(item.due_diligence_question)}</div><div><strong>缓释措施</strong>${escapeHtml(item.mitigation)}</div><div><strong>证据与有效期</strong>${item.evidence_id ? `企业证据 ${escapeHtml(item.evidence_id)}` : "待补证"} · ${escapeHtml(item.valid_until || "未设有效期")}</div></div>${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">打开原始证据 ↗</a>` : ""}</article>`;
}

function renderPartnerEvidenceCard(item) {
  return `<article class="partner-evidence-card"><header><strong>${escapeHtml(item.title)}</strong><span class="badge badge-${item.evidence_status === "verified" ? "finished" : "muted"}">${escapeHtml(item.evidence_status)}</span></header><p>${escapeHtml(item.content_text || "无可显示摘录")}</p><div class="partner-evidence-meta"><span>企业证据 ${escapeHtml(item.id)}</span><span>${escapeHtml(item.source_name || item.source_type)}</span><span>${escapeHtml(item.occurred_at || item.captured_at)}</span><span>快照 ${escapeHtml((item.snapshot_sha256 || "").slice(0, 12))}</span>${item.sensitive ? "<span>敏感材料已按角色脱敏</span>" : ""}</div>${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">查看来源 ↗</a>` : ""}</article>`;
}

function renderPartnerTaskCard(item) {
  return `<article class="partner-task-card"><header><strong>${escapeHtml(item.title)}</strong><span class="badge badge-${item.feishu_task_status === "open" ? "running" : item.feishu_task_status === "completed" ? "finished" : "muted"}">${escapeHtml(item.feishu_task_status)}</span></header><p>${escapeHtml(item.question)}</p><div class="partner-task-meta"><span>${escapeHtml(item.task_type)}</span><span>${escapeHtml(item.assignee_name || "待分派")}</span><span>截止 ${escapeHtml(item.due_at)}</span>${item.feishu_task_guid ? `<span>回执 ${escapeHtml(item.feishu_task_guid)}</span>` : ""}</div>${item.feishu_task_guid ? "" : `<button class="text-button" type="button" data-sync-partner-task="${escapeHtml(item.id)}">同步飞书任务</button>`}</article>`;
}

async function createPartnerEntity(event) {
  event.preventDefault();
  if (!state.organizationWorkspaceId) throw new Error("请先选择组织空间");
  const result = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies`, { method: "POST", body: JSON.stringify({ legal_name: el.partnerEntityName?.value.trim() || "", region: el.partnerEntityRegion?.value.trim() || "", actor: "admin" }) });
  state.partnerEntityId = result.entity.id;
  el.partnerEntityForm?.reset();
  await refreshPartnerEntities();
  showToast("合作方主体档案已建立；同名主体不会自动合并");
}

async function aggregatePartnerProfile() {
  if (!state.partnerEntityId) throw new Error("请先选择合作方主体");
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/aggregate`, { method: "POST", body: JSON.stringify({ actor: "admin" }) });
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/evaluate`, { method: "POST", body: JSON.stringify({ actor: "admin" }) });
  await openPartnerProfile(state.partnerEntityId);
  showToast("本地项目、结果、关系和组织材料已聚合并重新评估");
}

async function evaluatePartnerProfile() {
  if (!state.partnerEntityId) throw new Error("请先选择合作方主体");
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/evaluate`, { method: "POST", body: JSON.stringify({ actor: "admin" }) });
  await openPartnerProfile(state.partnerEntityId);
  showToast("风险有效性与六维缺口已重新计算");
}

async function savePartnerSnapshot() {
  if (!state.partnerEntityId) throw new Error("请先选择合作方主体");
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/snapshots`, { method: "POST", body: JSON.stringify({ actor: "admin", verified: true }) });
  showToast("已保存可离线打开的核验画像快照");
}

async function askPartnerQuestion(event) {
  event.preventDefault();
  if (!state.partnerEntityId) throw new Error("请先选择合作方主体");
  const answer = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/ask`, { method: "POST", body: JSON.stringify({ actor: "admin", question: el.partnerQuestionInput?.value.trim() || "" }) });
  if (el.partnerQuestionAnswer) {
    el.partnerQuestionAnswer.className = "partner-answer";
    el.partnerQuestionAnswer.innerHTML = `<p>${escapeHtml(answer.answer)}</p><p><strong>最坏影响：</strong>${escapeHtml(answer.worst_impact)}</p><p><strong>缓释措施：</strong>${escapeHtml(answer.mitigation)}</p><small>${escapeHtml(answer.basis)}</small>`;
  }
}

async function submitPartnerReview(event) {
  event.preventDefault();
  if (!state.partnerEntityId) throw new Error("请先选择合作方主体");
  const conditions = (el.partnerReviewConditions?.value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  const recommendation = el.partnerReviewRecommendation?.value || "conditional";
  if (recommendation === "conditional" && !conditions.length) throw new Error("有条件合作至少填写一个前置条件");
  const review = await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/reviews`, { method: "POST", body: JSON.stringify({ actor: "admin", recommendation, reason: el.partnerReviewReason?.value.trim() || "", valid_until: el.partnerReviewValidUntil?.value || "", conditions }) });
  if (el.partnerReviewStatus) el.partnerReviewStatus.textContent = `已由 ${review.confirmed_by} 确认，有效至 ${review.valid_until}`;
  await openPartnerProfile(state.partnerEntityId);
  showToast("人工合作结论已留痕，后续自动运行不会覆盖");
}

async function syncPartnerTask(taskId) {
  await api(`/api/organization/workspaces/${encodeURIComponent(state.organizationWorkspaceId)}/companies/${encodeURIComponent(state.partnerEntityId)}/tasks/${encodeURIComponent(taskId)}/sync-feishu?actor=admin`, { method: "POST" });
  await openPartnerProfile(state.partnerEntityId);
  showToast("飞书尽调任务已创建并保存回执");
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

function renderFeishuDeliveryWorkspaceOptions() {
  if (!el.feishuDeliveryWorkspace) return;
  const workspaces = state.organizationWorkspaces.filter((item) => item.status === "active");
  if (!workspaces.some((item) => item.id === state.feishuDeliveryWorkspaceId)) {
    state.feishuDeliveryWorkspaceId = "";
  }
  el.feishuDeliveryWorkspace.innerHTML = [
    '<option value="">默认飞书接收者</option>',
    ...workspaces.map(
      (item) => `<option value="${escapeHtml(item.id)}">项目群 · ${escapeHtml(item.name)}</option>`,
    ),
  ].join("");
  el.feishuDeliveryWorkspace.value = state.feishuDeliveryWorkspaceId;
  syncFeishuDeliveryTarget();
}

function syncFeishuDeliveryTarget() {
  const enabled = Boolean(el.feishuDeliveryInput?.checked);
  if (el.feishuDeliveryWorkspaceField) el.feishuDeliveryWorkspaceField.hidden = !enabled;
  if (el.feishuDeliveryWorkspace) el.feishuDeliveryWorkspace.disabled = !enabled;
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
    renderOrganizationReportDelivery(null);
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
    <div><span>连接状态</span><strong class="organization-online">飞书已连接</strong></div>
    <div class="organization-command-guide">
      <span>群聊协同</span>
      <div><code>记录组织记忆：内容</code><small>沉淀团队事实</small></div>
      <div><code>查询组织记忆：关键词</code><small>检索共享知识</small></div>
      <div><code>项目意见 机会编号：内容</code><small>写入机会协作审计链</small></div>
      <div><code>会审意见 机会编号 要求编号：内容</code><small>补充正式会审依据</small></div>
    </div>`;
  renderOrganizationReportDelivery(workspace);
}

function renderOrganizationReportDelivery(workspace) {
  if (!el.organizationReportDelivery) return;
  if (!workspace) {
    el.organizationReportDelivery.hidden = true;
    el.organizationReportDelivery.innerHTML = "";
    return;
  }
  const reports = state.outbox.slice(0, 3);
  el.organizationReportDelivery.hidden = false;
  el.organizationReportDelivery.innerHTML = `
    <div class="section-heading">
      <div><h2 id="organizationReportDeliveryTitle">共享报告</h2><span>发送到 ${escapeHtml(workspace.name)}</span></div>
    </div>
    ${reports.length ? `<div class="organization-report-list">${reports.map((report) => `
      <article class="organization-report-row">
        <div><strong title="${escapeHtml(report.name || "")}">${escapeHtml(report.name || "未命名报告")}</strong><small>${escapeHtml(compactDateTimeText(report.created_at || ""))}</small></div>
        <div class="organization-report-actions"><a class="text-link" href="${escapeHtml(report.download_url || "#")}" target="_blank" rel="noreferrer">下载</a><button class="text-link" type="button" data-send-workspace-report="${escapeHtml(report.name || "")}" data-workspace-id="${escapeHtml(workspace.id)}">发送到群</button></div>
      </article>`).join("")}</div>` : '<p class="organization-report-empty">暂无可共享的 Word 报告。</p>'}
  `;
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

async function sendWorkspaceReport(workspaceId, filename) {
  const report = state.outbox.find((item) => item.name === filename) || {};
  await api(
    `/api/organization/workspaces/${encodeURIComponent(workspaceId)}/outbox/${encodeURIComponent(filename)}/send-feishu`,
    {
      method: "POST",
      body: JSON.stringify({ run_id: report.run_id || "", subscription_id: report.subscription_id || "" }),
    },
  );
  await Promise.all([refreshOutbox(), refreshFeishu()]);
  showToast("Word 报告已发送到当前飞书项目群");
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
  if (result.status !== "sent") {
    showToast("飞书发送未完成");
  } else if (result.digest_status === "sent") {
    showToast("Word 报告和群内检索简报已发送");
  } else if (result.digest_status === "failed") {
    showToast("Word 报告已发送；群内简报发送失败，可稍后重试");
  } else {
    showToast("Word 报告已发送到飞书");
  }
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
  const sendToFeishu = Boolean(el.feishuDeliveryInput?.checked);
  return {
    query: el.queryInput?.value.trim() || "",
    max_pages: Number(el.maxPagesInput?.value || 1),
    max_results: Number(el.maxResultsInput?.value || 10),
    model_strategy: el.modelStrategySelect?.value || "config",
    delivery_channels: sendToFeishu
      ? ["web", "outbox", "feishu"]
      : ["web", "outbox"],
    feishu_workspace_id: sendToFeishu && state.feishuDeliveryWorkspaceId
      ? state.feishuDeliveryWorkspaceId
      : undefined,
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
  state.intentConfirmation = { query: "", confirmed: false };
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
    refreshFinalsHome(),
    refreshIntentPreview(),
    refreshOutbox(),
    refreshSubscriptions(),
    refreshSourcesPanel(),
    refreshRuns(),
    refreshEvaluation(),
    refreshOpportunities(),
    refreshMemoryWeekly(),
    refreshFeishu(),
    refreshOrganizationWorkspaces(),
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
    const sourceRelationDecisionForm = event.target.closest("[data-source-relation-decision]");
    if (sourceRelationDecisionForm) {
      event.preventDefault();
      decideSourceRelation(sourceRelationDecisionForm, event.submitter).catch(toastError("来源关系裁决失败"));
      return;
    }
    const sandboxScenarioForm = event.target.closest("[data-decision-sandbox-form]");
    if (sandboxScenarioForm) {
      event.preventDefault();
      createDecisionSandboxScenario(sandboxScenarioForm).catch(toastError("沙盘推演失败"));
      return;
    }
    const sandboxDecisionForm = event.target.closest("[data-sandbox-suggestion-decision]");
    if (sandboxDecisionForm) {
      event.preventDefault();
      decideDecisionSandboxSuggestion(sandboxDecisionForm, event.submitter).catch(toastError("沙盘建议裁决失败"));
      return;
    }
    const capabilityGapCompleteForm = event.target.closest("[data-capability-gap-complete]");
    if (capabilityGapCompleteForm) {
      event.preventDefault();
      completeCapabilityGapAction(capabilityGapCompleteForm).catch(toastError("缺口行动完成失败"));
      return;
    }
    const capabilityGapActionForm = event.target.closest("[data-capability-gap-action]");
    if (capabilityGapActionForm) {
      event.preventDefault();
      createCapabilityGapAction(capabilityGapActionForm).catch(toastError("缺口行动创建失败"));
      return;
    }
    const evidenceReviewForm = event.target.closest("[data-evidence-review-form]");
    if (evidenceReviewForm) {
      event.preventDefault();
      submitEvidenceReview(evidenceReviewForm).catch(toastError("证据核验保存失败"));
      return;
    }
    const reviewOpinionCompleteForm = event.target.closest("[data-review-opinion-complete]");
    if (reviewOpinionCompleteForm) {
      event.preventDefault();
      completeReviewOpinionAction(reviewOpinionCompleteForm).catch(toastError("会审行动完成失败"));
      return;
    }
    const reviewOpinionActionForm = event.target.closest("[data-review-opinion-action]");
    if (reviewOpinionActionForm) {
      event.preventDefault();
      createReviewOpinionAction(reviewOpinionActionForm).catch(toastError("会审行动创建失败"));
      return;
    }
    const businessMeasurementForm = event.target.closest("#businessMeasurementForm");
    if (businessMeasurementForm) {
      event.preventDefault();
      saveBusinessMeasurement(businessMeasurementForm).catch(toastError("实测任务保存失败"));
      return;
    }
    const capabilityDecisionForm = event.target.closest("[data-capability-match-decision]");
    if (capabilityDecisionForm) {
      event.preventDefault();
      decideCapabilityMatch(capabilityDecisionForm, event.submitter).catch(toastError("匹配结论保存失败"));
      return;
    }
    const capabilityEvidenceForm = event.target.closest("[data-capability-evidence-form]");
    if (capabilityEvidenceForm) {
      event.preventDefault();
      saveCapabilityEvidence(capabilityEvidenceForm).catch(toastError("企业能力证据保存失败"));
      return;
    }
    const humanReviewOpinionForm = event.target.closest("[data-human-review-opinion-form]");
    if (humanReviewOpinionForm) {
      event.preventDefault();
      saveHumanReviewOpinion(humanReviewOpinionForm).catch(toastError("会审意见保存失败"));
      return;
    }
    const collaborationNoteForm = event.target.closest("[data-collaboration-note-form]");
    if (collaborationNoteForm) {
      event.preventDefault();
      saveOpportunityCollaborationNote(collaborationNoteForm).catch(toastError("协作意见保存失败"));
      return;
    }
    const reviewForm = event.target.closest("[data-requirement-review-form]");
    if (reviewForm) {
      event.preventDefault();
      resolveOpportunityReviewCase(reviewForm).catch(toastError("会审裁决保存失败"));
      return;
    }
    const requirementForm = event.target.closest("[data-opportunity-requirements-form]");
    if (requirementForm) {
      event.preventDefault();
      saveOpportunityRequirement(requirementForm).catch(toastError("要求账本保存失败"));
      return;
    }
    const bidPricingForm = event.target.closest("[data-bid-pricing-form]");
    if (bidPricingForm) {
      event.preventDefault();
      saveBidPricing(bidPricingForm).catch(toastError("报价计划保存失败"));
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
  document.querySelectorAll("[data-finals-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.finalsView));
  });
  document.querySelectorAll("[data-finals-intent]").forEach((button) => {
    button.addEventListener("click", () => {
      if (el.finalsHomeIntentInput) el.finalsHomeIntentInput.value = button.dataset.finalsIntent || "";
      routeFinalsIntent();
    });
  });
  document.querySelectorAll("[data-finals-primary-case]").forEach((button) => {
    button.addEventListener("click", () => openFinalsPrimaryCase(button.dataset.noticeId || "").catch(toastError("主案例打开失败")));
  });
  el.finalsHomeIntentForm?.addEventListener("submit", routeFinalsIntent);
  el.finalsHomeRefreshButton?.addEventListener("click", () => refreshFinalsHome().catch(toastError("首页状态刷新失败")));
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
  el.motionToggleButton?.addEventListener("click", () => applyMotionPreference(!state.motionDisabled));
  el.presentationModeButton?.addEventListener("click", () => applyPresentationMode(!state.presentationMode));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.presentationMode) applyPresentationMode(false);
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
    const confirmIntentTarget = event.target.closest("[data-confirm-intent]");
    if (confirmIntentTarget) {
      const query = el.queryInput?.value.trim() || "";
      if (query) {
        state.intentConfirmation = { query, confirmed: true };
        refreshIntentPreview()
          .then(() => el.form?.requestSubmit())
          .catch(toastError("意图确认失败"));
      }
      return;
    }
    const editIntentTarget = event.target.closest("[data-edit-intent]");
    if (editIntentTarget) {
      el.queryInput?.focus();
      showToast("请补充明确的采购品类或地区");
      return;
    }
    const annotateGoldTarget = event.target.closest("[data-annotate-gold-case]");
    if (annotateGoldTarget) {
      try {
        openGoldAnnotationDialog(annotateGoldTarget.dataset.annotateGoldCase || "");
      } catch (error) {
        toastError("金标用例加载失败")(error);
      }
      return;
    }
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
    const loadChallengeTarget = event.target.closest("[data-load-live-challenge]");
    if (loadChallengeTarget) {
      loadLiveChallenge(loadChallengeTarget.dataset.loadLiveChallenge || "").catch(toastError("挑战记录打开失败"));
      return;
    }
    const challengeOpportunityTarget = event.target.closest("[data-challenge-opportunity]");
    if (challengeOpportunityTarget) {
      showView("opportunityView");
      openOpportunityDetail(challengeOpportunityTarget.dataset.challengeOpportunity || "").catch(toastError("机会档案加载失败"));
      return;
    }
    const demoCaseTarget = event.target.closest("[data-demo-case-id]");
    if (demoCaseTarget) {
      runDemoRehearsal(
        demoCaseTarget.dataset.demoCaseId || "",
        demoCaseTarget.dataset.demoMode || "live",
      ).catch(toastError("演示案例打开失败"));
      return;
    }
    const radarLocationTarget = event.target.closest("[data-radar-location]");
    if (radarLocationTarget) {
      selectRadarLocation(radarLocationTarget.dataset.radarLocation || "");
      return;
    }
    const radarOpportunityTarget = event.target.closest("[data-radar-open-opportunity]");
    if (radarOpportunityTarget) {
      showView("opportunityView");
      openOpportunityDetail(radarOpportunityTarget.dataset.radarOpenOpportunity || "").catch(toastError("机会档案加载失败"));
      return;
    }
    const radarQueryTarget = event.target.closest("[data-radar-query-location]");
    if (radarQueryTarget) {
      applyRadarQuery(radarQueryTarget.dataset.radarQueryLocation || "全国");
      return;
    }
    const radarCategoryTarget = event.target.closest("[data-radar-category]");
    if (radarCategoryTarget) {
      if (el.radarCategorySelect) el.radarCategorySelect.value = radarCategoryTarget.dataset.radarCategory || "";
      refreshOpportunityRadar().catch(toastError("雷达品类筛选失败"));
      return;
    }
    const battleEventTarget = event.target.closest("[data-battle-event]");
    if (battleEventTarget) {
      openBattleEvidence(battleEventTarget.dataset.battleEvent || "").catch(toastError("事件证据加载失败"));
      return;
    }
    const battleImpactTarget = event.target.closest("[data-review-battle-impact]");
    if (battleImpactTarget) {
      reviewBattleImpact(
        battleImpactTarget.dataset.reviewBattleImpact || "",
        battleImpactTarget.dataset.impactStatus || "monitoring",
      ).catch(toastError("候选影响复核失败"));
      return;
    }
    const partnerEntityTarget = event.target.closest("[data-partner-entity]");
    if (partnerEntityTarget) {
      openPartnerProfile(partnerEntityTarget.dataset.partnerEntity || "").catch(toastError("合作方画像加载失败"));
      return;
    }
    const partnerTaskTarget = event.target.closest("[data-sync-partner-task]");
    if (partnerTaskTarget) {
      syncPartnerTask(partnerTaskTarget.dataset.syncPartnerTask || "").catch(toastError("飞书尽调任务同步失败"));
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
    const bidMemoryNodeTarget = event.target.closest("[data-bid-memory-node]");
    if (bidMemoryNodeTarget && state.bidMemory) {
      state.bidMemorySelectedNodeId = bidMemoryNodeTarget.dataset.bidMemoryNode || "";
      renderBidMemory(state.bidMemory);
      return;
    }
    const bidMemoryAssetActionTarget = event.target.closest("[data-bid-memory-asset-action]");
    if (bidMemoryAssetActionTarget) {
      decideBidMemoryAsset(bidMemoryAssetActionTarget).catch(toastError("企业经验处理失败"));
      return;
    }
    const archiveBidMemoryTarget = event.target.closest("[data-archive-bid-memory]");
    if (archiveBidMemoryTarget) {
      try {
        openBidMemoryArchiveDialog(archiveBidMemoryTarget.dataset.archiveBidMemory || "");
      } catch (error) {
        toastError("项目归档到记忆体失败")(error);
      }
      return;
    }
    const openBidMemoryTarget = event.target.closest("[data-open-bid-memory]");
    if (openBidMemoryTarget) {
      el.opportunityDetailDialog?.close();
      showView("organizationView");
      refreshBidMemory(openBidMemoryTarget.dataset.openBidMemory || "").catch(toastError("企业投标记忆体加载失败"));
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
    const sendWorkspaceReportTarget = event.target.closest("[data-send-workspace-report]");
    if (sendWorkspaceReportTarget) {
      sendWorkspaceReport(
        sendWorkspaceReportTarget.dataset.workspaceId,
        sendWorkspaceReportTarget.dataset.sendWorkspaceReport,
      ).catch(toastError("发送项目群失败"));
      return;
    }
    const sendOpportunityTarget = event.target.closest("[data-send-opportunity-feishu]");
    if (sendOpportunityTarget) {
      openOpportunityOwnerDialog(sendOpportunityTarget.dataset.sendOpportunityFeishu).catch(
        toastError("负责人目录加载失败"),
      );
      return;
    }
    const toggleChangeImpactTarget = event.target.closest("[data-toggle-change-impact]");
    if (toggleChangeImpactTarget) {
      loadOpportunityChangeImpact(
        toggleChangeImpactTarget.dataset.toggleChangeImpact || "",
        toggleChangeImpactTarget.dataset.affectedOnly === "true",
      ).catch(toastError("公告冲击波筛选失败"));
      return;
    }
    const confirmChangeImpactTarget = event.target.closest("[data-confirm-change-impact]");
    if (confirmChangeImpactTarget) {
      confirmOpportunityChangeImpact(
        confirmChangeImpactTarget.dataset.confirmChangeImpact || "",
        confirmChangeImpactTarget.dataset.actionId || "",
      ).catch(toastError("变更行动确认失败"));
      return;
    }
    const dispatchChangeImpactTarget = event.target.closest("[data-dispatch-change-impact]");
    if (dispatchChangeImpactTarget) {
      dispatchOpportunityChangeImpact(
        dispatchChangeImpactTarget.dataset.dispatchChangeImpact || "",
        dispatchChangeImpactTarget.dataset.roundId || "",
      ).catch(toastError("公告冲击波同步飞书失败"));
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
    const confirmBidRequirementTarget = event.target.closest("[data-confirm-bid-requirement]");
    if (confirmBidRequirementTarget) {
      confirmBidRequirement(confirmBidRequirementTarget.dataset.opportunityId || "", confirmBidRequirementTarget.dataset.confirmBidRequirement || "").catch(toastError("要求确认失败"));
      return;
    }
    const splitBidRequirementTarget = event.target.closest("[data-split-bid-requirement]");
    if (splitBidRequirementTarget) {
      splitBidRequirement(splitBidRequirementTarget.dataset.opportunityId || "", splitBidRequirementTarget.dataset.splitBidRequirement || "").catch(toastError("要求拆分失败"));
      return;
    }
    const mergeBidRequirementsTarget = event.target.closest("[data-merge-selected-requirements]");
    if (mergeBidRequirementsTarget) {
      mergeSelectedRequirements(mergeBidRequirementsTarget.dataset.mergeSelectedRequirements || "").catch(toastError("要求合并失败"));
      return;
    }
    const buildBidWorkplanTarget = event.target.closest("[data-build-bid-workplan]");
    if (buildBidWorkplanTarget) {
      buildBidWorkplan(buildBidWorkplanTarget.dataset.buildBidWorkplan || "").catch(toastError("作战图生成失败"));
      return;
    }
    const completeBidTaskTarget = event.target.closest("[data-complete-bid-task]");
    if (completeBidTaskTarget) {
      completeBidTask(completeBidTaskTarget.dataset.opportunityId || "", completeBidTaskTarget.dataset.completeBidTask || "").catch(toastError("任务完成失败"));
      return;
    }
    const syncBidWorkplanTarget = event.target.closest("[data-sync-bid-workplan]");
    if (syncBidWorkplanTarget) {
      syncBidWorkplan(syncBidWorkplanTarget.dataset.syncBidWorkplan || "").catch(toastError("飞书作战图同步失败"));
      return;
    }
    const refreshBidTaskTarget = event.target.closest("[data-refresh-bid-task-status]");
    if (refreshBidTaskTarget) {
      refreshBidTaskStatus(refreshBidTaskTarget.dataset.refreshBidTaskStatus || "").catch(toastError("飞书任务回读失败"));
      return;
    }
    const exportBidWorkplanTarget = event.target.closest("[data-export-bid-workplan]");
    if (exportBidWorkplanTarget) {
      window.location.href = `/api/opportunities/${encodeURIComponent(exportBidWorkplanTarget.dataset.exportBidWorkplan || "")}/bid-workplan/export`;
      return;
    }
    const analyzeCapabilityMatchesTarget = event.target.closest("[data-analyze-capability-matches]");
    if (analyzeCapabilityMatchesTarget) {
      analyzeOpportunityCapabilityMatches(
        analyzeCapabilityMatchesTarget.dataset.analyzeCapabilityMatches || "",
      ).catch(toastError("能力匹配分析失败"));
      return;
    }
    const syncReviewOpinionActionTarget = event.target.closest("[data-sync-review-opinion-action]");
    if (syncReviewOpinionActionTarget) {
      syncReviewOpinionAction(
        syncReviewOpinionActionTarget.dataset.syncReviewOpinionAction || "",
        syncReviewOpinionActionTarget.dataset.actionId || "",
      ).catch(toastError("会审行动同步飞书失败"));
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
    const syncReviewBoardTarget = event.target.closest("[data-sync-review-board]");
    if (syncReviewBoardTarget) {
      syncOpportunityReviewBoard(syncReviewBoardTarget.dataset.syncReviewBoard || "").catch(
        toastError("会审队列生成失败"),
      );
      return;
    }
    const sendReviewBoardTarget = event.target.closest("[data-send-review-board-feishu]");
    if (sendReviewBoardTarget) {
      sendOpportunityReviewBoardToFeishu(
        sendReviewBoardTarget.dataset.sendReviewBoardFeishu || "",
      ).catch(toastError("同步群内会审失败"));
      return;
    }
    const runReviewAgentsTarget = event.target.closest("[data-run-review-agents]");
    if (runReviewAgentsTarget) {
      runOpportunityReviewAgents(runReviewAgentsTarget.dataset.runReviewAgents || "").catch(
        toastError("AI 会审失败"),
      );
      return;
    }
    const retryReviewAgentTarget = event.target.closest("[data-retry-review-agent]");
    if (retryReviewAgentTarget) {
      retryOpportunityReviewAgent(
        retryReviewAgentTarget.dataset.retryReviewAgent || "",
        retryReviewAgentTarget.dataset.reviewId || "",
        retryReviewAgentTarget.dataset.agentRole || "",
      ).catch(toastError("角色恢复失败"));
      return;
    }
    const opportunityJourneyTarget = event.target.closest("[data-scroll-opportunity-target]");
    if (opportunityJourneyTarget) {
      const target = el.opportunityDetailContent?.querySelector(
        `#${opportunityJourneyTarget.dataset.scrollOpportunityTarget || ""}`,
      );
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const launchWarRoomTarget = event.target.closest("[data-launch-war-room]");
    if (launchWarRoomTarget) {
      launchOpportunityWarRoom(launchWarRoomTarget.dataset.launchWarRoom || "").catch(
        toastError("飞书战情室启动失败"),
      );
      return;
    }
    const reloadWarRoomTarget = event.target.closest("[data-reload-war-room]");
    if (reloadWarRoomTarget) {
      loadOpportunityWarRoomPlan(reloadWarRoomTarget.dataset.reloadWarRoom || "").catch(
        toastError("战情室状态加载失败"),
      );
      return;
    }
    const retryWarRoomStepTarget = event.target.closest("[data-retry-war-room-step]");
    if (retryWarRoomStepTarget) {
      retryOpportunityWarRoomStep(retryWarRoomStepTarget).catch(toastError("战情室步骤重试失败"));
      return;
    }
    const syncWarRoomBackTarget = event.target.closest("[data-sync-war-room-back]");
    if (syncWarRoomBackTarget) {
      syncOpportunityWarRoomBack(syncWarRoomBackTarget.dataset.syncWarRoomBack || "").catch(toastError("团队状态回写失败"));
      return;
    }
    const dispatchWarRoomChangesTarget = event.target.closest("[data-dispatch-war-room-changes]");
    if (dispatchWarRoomChangesTarget) {
      dispatchOpportunityWarRoomChanges(dispatchWarRoomChangesTarget.dataset.dispatchWarRoomChanges || "").catch(toastError("增量变更发送失败"));
      return;
    }
    const archiveWarRoomTarget = event.target.closest("[data-archive-war-room]");
    if (archiveWarRoomTarget) {
      archiveOpportunityWarRoom(archiveWarRoomTarget.dataset.archiveWarRoom || "").catch(toastError("战情室归档失败"));
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
    const openEvidenceTarget = event.target.closest("[data-open-evidence-microscope]");
    if (openEvidenceTarget) {
      openEvidenceMicroscope(
        openEvidenceTarget.dataset.openEvidenceMicroscope || "",
        openEvidenceTarget.dataset.evidenceClaimType || "",
        openEvidenceTarget.dataset.evidenceClaimKey || "",
      ).catch(toastError("证据显微镜加载失败"));
      return;
    }
    const selectEvidenceClaimTarget = event.target.closest("[data-select-evidence-claim]");
    if (selectEvidenceClaimTarget && state.evidenceMicroscopePayload) {
      el.evidenceMicroscopeContent.innerHTML = renderEvidenceMicroscope(
        state.evidenceMicroscopePayload,
        selectEvidenceClaimTarget.dataset.selectEvidenceClaim || "",
      );
      return;
    }
    const closeEvidenceTarget = event.target.closest("[data-close-evidence-microscope]");
    if (closeEvidenceTarget) {
      closeEvidenceMicroscope();
      return;
    }
    const closeOpportunityTarget = event.target.closest("[data-close-opportunity-detail]");
    if (closeOpportunityTarget) {
      el.opportunityDetailDialog?.close();
      return;
    }
    const refreshDigitalTwinTarget = event.target.closest("[data-refresh-digital-twin]");
    if (refreshDigitalTwinTarget) {
      refreshDigitalTwinCockpit(refreshDigitalTwinTarget.dataset.refreshDigitalTwin)
        .catch(toastError("数字项目档案刷新失败"));
      return;
    }
    const selectDecisionScenarioTarget = event.target.closest("[data-select-decision-scenario]");
    if (selectDecisionScenarioTarget) {
      const noticeId = selectDecisionScenarioTarget.dataset.noticeId || "";
      state.selectedDecisionScenarios[noticeId] = selectDecisionScenarioTarget.dataset.selectDecisionScenario || "";
      const container = currentDecisionSandboxContainer(noticeId);
      const payload = state.decisionSandboxPayloads[noticeId];
      if (container && payload) container.innerHTML = renderDecisionSandbox(payload);
      return;
    }
    const recomputeDecisionScenarioTarget = event.target.closest("[data-recompute-decision-scenario]");
    if (recomputeDecisionScenarioTarget) {
      recomputeDecisionScenario(recomputeDecisionScenarioTarget).catch(toastError("方案复算失败"));
      return;
    }
    const promoteDecisionScenarioTarget = event.target.closest("[data-promote-decision-scenario]");
    if (promoteDecisionScenarioTarget) {
      promoteDecisionScenario(promoteDecisionScenarioTarget).catch(toastError("转为待确认建议失败"));
      return;
    }
    const compareDecisionScenariosTarget = event.target.closest("[data-compare-decision-scenarios]");
    if (compareDecisionScenariosTarget) {
      compareDecisionSandboxScenarios(compareDecisionScenariosTarget).catch(toastError("方案比较失败"));
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
  el.opportunityDetailDialog?.addEventListener("close", () => {
    state.opportunityDetailRequestSequence += 1;
    stopDigitalTwinRefresh();
  });
  el.evidenceMicroscopeDialog?.addEventListener("click", (event) => {
    if (event.target === el.evidenceMicroscopeDialog) closeEvidenceMicroscope();
  });
  el.evidenceMicroscopeDialog?.addEventListener("close", () => {
    state.evidenceMicroscopeNoticeId = "";
    state.evidenceMicroscopePayload = null;
  });
  el.goldAnnotationDialog?.addEventListener("click", (event) => {
    if (event.target === el.goldAnnotationDialog) closeGoldAnnotationDialog();
  });
  el.goldAnnotationForm?.addEventListener("submit", (event) =>
    submitGoldAnnotation(event).catch(toastError("人工金标保存失败")),
  );
  el.closeGoldAnnotationButton?.addEventListener("click", closeGoldAnnotationDialog);
  el.cancelGoldAnnotationButton?.addEventListener("click", closeGoldAnnotationDialog);
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
  el.bidMemoryArchiveDialog?.addEventListener("click", (event) => {
    if (event.target === el.bidMemoryArchiveDialog) closeBidMemoryArchiveDialog();
  });
  el.bidMemoryArchiveDialog?.addEventListener("close", () => {
    state.pendingBidMemoryArchiveNoticeId = "";
    if (el.submitBidMemoryArchiveButton) el.submitBidMemoryArchiveButton.disabled = false;
  });
  el.bidMemoryArchiveForm?.addEventListener("submit", (event) =>
    archiveOpportunityToBidMemory(event).catch((error) => {
      if (el.submitBidMemoryArchiveButton) el.submitBidMemoryArchiveButton.disabled = false;
      toastError("项目归档到记忆体失败")(error);
    }),
  );
  el.closeBidMemoryArchiveButton?.addEventListener("click", closeBidMemoryArchiveDialog);
  el.cancelBidMemoryArchiveButton?.addEventListener("click", closeBidMemoryArchiveDialog);
  el.form?.addEventListener("submit", submitRun);
  el.subscribeButton?.addEventListener("click", createSubscriptionFromForm);
  el.queryInput?.addEventListener("input", () => {
    state.intentConfirmation = { query: "", confirmed: false };
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
  el.feishuDeliveryInput?.addEventListener("change", syncFeishuDeliveryTarget);
  el.feishuDeliveryWorkspace?.addEventListener("change", () => {
    state.feishuDeliveryWorkspaceId = el.feishuDeliveryWorkspace.value;
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
  el.challengeForm?.addEventListener("submit", (event) =>
    startLiveChallenge(event).catch(toastError("现场挑战失败")),
  );
  el.challengeSupplementButton?.addEventListener("click", () =>
    supplementLiveChallenge().catch(toastError("联网补充启动失败")),
  );
  el.challengeCancelButton?.addEventListener("click", () =>
    cancelLiveChallenge().catch(toastError("停止联网失败")),
  );
  el.challengeCopyLinkButton?.addEventListener("click", () =>
    copyLiveChallengeLink().catch(toastError("复制入口失败")),
  );
  el.challengeRefreshHistoryButton?.addEventListener("click", () =>
    refreshLiveChallengeHistory().catch(toastError("挑战记录刷新失败")),
  );
  el.demoRefreshButton?.addEventListener("click", () =>
    refreshDemoReliability().catch(toastError("可靠性预检刷新失败")),
  );
  el.demoPrepareButton?.addEventListener("click", () =>
    prepareDemoReliability().catch(toastError("演示案例准备失败")),
  );
  el.demoRunThreeButton?.addEventListener("click", () =>
    runThreeDemoRehearsals().catch(toastError("连续演练失败")),
  );
  el.demoLayoutAuditButton?.addEventListener("click", () =>
    runDemoLayoutAudits().catch(toastError("投屏实测失败")),
  );
  el.visualAuditButton?.addEventListener("click", () =>
    runVisualSystemAudits().catch(toastError("方向15视觉验收失败")),
  );
  window.addEventListener("online", updateChallengeNetworkState);
  window.addEventListener("offline", updateChallengeNetworkState);
  updateChallengeNetworkState();
  document.querySelectorAll("[data-radar-scope]").forEach((button) => {
    button.addEventListener("click", () => {
      state.radarScope = button.dataset.radarScope || "all";
      state.radarSelectedLocationId = "";
      refreshOpportunityRadar().catch(toastError("雷达范围切换失败"));
    });
  });
  el.radarWindowSelect?.addEventListener("change", () => {
    state.radarSelectedLocationId = "";
    refreshOpportunityRadar().catch(toastError("雷达时间筛选失败"));
  });
  el.radarCategorySelect?.addEventListener("change", () => {
    state.radarSelectedLocationId = "";
    refreshOpportunityRadar().catch(toastError("雷达品类筛选失败"));
  });
  el.refreshRadarButton?.addEventListener("click", () =>
    refreshOpportunityRadar({ persist: true }).catch(toastError("本地雷达快照保存失败")),
  );
  el.radarMotionButton?.addEventListener("click", () => {
    applyMotionPreference(!state.motionDisabled);
  });
  el.radarPresentationButton?.addEventListener("click", () => {
    applyPresentationMode(!state.presentationMode);
  });
  document.querySelectorAll("[data-battle-scope]").forEach((button) => {
    button.addEventListener("click", () => {
      state.battleScope = button.dataset.battleScope || "global";
      refreshBattleMap().catch(toastError("战情图范围切换失败"));
    });
  });
  document.querySelectorAll("[data-battle-layer]").forEach((input) => {
    input.addEventListener("change", () => refreshBattleMap().catch(toastError("战情图图层切换失败")));
  });
  el.battleWindowSelect?.addEventListener("change", () => refreshBattleMap().catch(toastError("战情图时间筛选失败")));
  el.battleCategorySelect?.addEventListener("change", () => refreshBattleMap().catch(toastError("战情图品类筛选失败")));
  el.battleModeSelect?.addEventListener("change", () => refreshBattleMap().catch(toastError("战情图模式切换失败")));
  el.battleSyncButton?.addEventListener("click", () => refreshBattleMap({ sync: true }).catch(toastError("本地事件刷新失败")));
  el.battleExternalButton?.addEventListener("click", () => refreshBattleMap({ fetchExternal: true }).catch(toastError("USGS 官方事件同步失败")));
  el.battleReplayButton?.addEventListener("click", () => saveBattleReplay().catch(toastError("验证回放保存失败")));
  el.battleMotionButton?.addEventListener("click", () => applyMotionPreference(!state.motionDisabled));
  el.battlePresentationButton?.addEventListener("click", () => applyPresentationMode(!state.presentationMode));
  el.battlePlayButton?.addEventListener("click", toggleBattlePlayback);
  el.battleTimelineRange?.addEventListener("input", () => {
    state.battleTimelineIndex = Number(el.battleTimelineRange.value || 0);
    if (state.battleMap) renderBattleFrame(state.battleMap);
  });
  el.battleEvidenceCloseButton?.addEventListener("click", () => el.battleEvidenceDialog?.close());
  el.trainingSeedButton?.addEventListener("click", () =>
    refreshTrainingCenter({ seed: true }).catch(toastError("训练场景刷新失败")),
  );
  el.trainingSetupForm?.addEventListener("submit", (event) =>
    createTrainingFromForm(event).catch(toastError("训练会话建立失败")),
  );
  el.trainingHistoryButton?.addEventListener("click", () =>
    refreshTrainingHistory().catch(toastError("训练记录刷新失败")),
  );
  el.trainingScenarioList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-training-scenario]");
    const nextScenarioId = button?.dataset.trainingScenario || "";
    if (!nextScenarioId) return;
    if (state.trainingSession?.scenario_id !== nextScenarioId) {
      state.trainingSession = null;
      stopTrainingTimer();
      if (el.trainingReport) el.trainingReport.hidden = true;
      if (el.trainingStage) {
        el.trainingStage.className = "training-stage empty-state";
        el.trainingStage.innerHTML = "<b>选择角色与模式后建立训练会话</b><p>系统会按固定状态机连续追问，并保存首次回答与证据引用。</p>";
      }
    }
    selectTrainingScenario(nextScenarioId);
  });
  el.trainingHistory?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-training-session]");
    if (button) loadTrainingSession(button.dataset.trainingSession || "").catch(toastError("训练回放加载失败"));
  });
  el.loadBidMemoryButton?.addEventListener("click", () =>
    refreshBidMemory().catch(toastError("企业投标记忆体加载失败")),
  );
  el.bidMemoryTargetNoticeId?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      refreshBidMemory().catch(toastError("企业投标记忆体加载失败"));
    }
  });
  el.partnerWorkspaceSelect?.addEventListener("change", () => {
    state.organizationWorkspaceId = el.partnerWorkspaceSelect.value;
    state.partnerEntityId = "";
    refreshPartnerEntities().catch(toastError("合作方列表加载失败"));
  });
  el.partnerSearchButton?.addEventListener("click", () =>
    refreshPartnerEntities().catch(toastError("合作方搜索失败")),
  );
  el.partnerSearchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      refreshPartnerEntities().catch(toastError("合作方搜索失败"));
    }
  });
  el.partnerEntityForm?.addEventListener("submit", (event) =>
    createPartnerEntity(event).catch(toastError("合作方主体建立失败")),
  );
  el.partnerAggregateButton?.addEventListener("click", () =>
    aggregatePartnerProfile().catch(toastError("合作方证据聚合失败")),
  );
  el.partnerEvaluateButton?.addEventListener("click", () =>
    evaluatePartnerProfile().catch(toastError("合作方风险评估失败")),
  );
  el.partnerSnapshotButton?.addEventListener("click", () =>
    savePartnerSnapshot().catch(toastError("合作方快照保存失败")),
  );
  el.partnerQuestionForm?.addEventListener("submit", (event) =>
    askPartnerQuestion(event).catch(toastError("合作方证据追问失败")),
  );
  el.partnerReviewForm?.addEventListener("submit", (event) =>
    submitPartnerReview(event).catch(toastError("合作结论保存失败")),
  );
  el.organizationWorkspaceSelect?.addEventListener("change", () => {
    state.organizationWorkspaceId = el.organizationWorkspaceSelect.value;
    renderOrganizationSummary();
    Promise.all([refreshOrganizationMemories(), refreshBidMemory()]).catch(toastError("组织记忆加载失败"));
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
  const query = new URLSearchParams(window.location.search);
  state.pendingOpportunityId = query.get("opportunity")?.trim() || "";
  state.partnerEntityId = query.get("partner")?.trim() || "";
  const requestedRadarScope = query.get("radar_scope")?.trim() || "";
  if (["all", "domestic", "international"].includes(requestedRadarScope)) state.radarScope = requestedRadarScope;
  const requestedRadarDays = query.get("radar_days")?.trim() || "";
  if (el.radarWindowSelect && ["0", "30", "90", "365"].includes(requestedRadarDays)) el.radarWindowSelect.value = requestedRadarDays;
  const requestedBattleScope = query.get("battle_scope")?.trim() || "";
  if (["china", "global"].includes(requestedBattleScope)) state.battleScope = requestedBattleScope;
  const requestedBattleHours = query.get("battle_hours")?.trim() || "";
  if (el.battleWindowSelect && ["0", "1", "24", "168", "2160"].includes(requestedBattleHours)) el.battleWindowSelect.value = requestedBattleHours;
  normalizeWorkbenchLayout();
  if (el.partnerReviewValidUntil && !el.partnerReviewValidUntil.value) {
    const date = new Date();
    date.setDate(date.getDate() + 180);
    el.partnerReviewValidUntil.value = date.toISOString().slice(0, 10);
  }
  bindEvents();
  applyTheme(loadTheme());
  loadDisplayPreferences();
  applyDepthProfile(el.searchDepthSelect?.value || "standard");
  syncActionMode();
  await refreshAll();
  const requestedView = query.get("view") || "";
  if (document.getElementById(requestedView)?.classList.contains("view")) showView(requestedView);
  else if (query.get("memory_notice")) showView("organizationView");
  else if (state.pendingOpportunityId) showView("opportunityView");
  if (
    requestedView === "demoConsoleView"
    && query.get("autoLayoutAudit") === "1"
    && query.get("layoutAudit") !== "1"
  ) {
    window.setTimeout(() => runDemoLayoutAudits().catch(toastError("投屏自动实测失败")), 800);
  }
  if (
    requestedView === "demoConsoleView"
    && query.get("autoVisualAudit") === "1"
    && query.get("visualAuditFrame") !== "1"
  ) {
    window.setTimeout(() => runVisualSystemAudits().catch(toastError("方向15视觉自动验收失败")), 1200);
  }
}

init().catch((error) => showToast(`页面初始化失败：${error.message}`));
