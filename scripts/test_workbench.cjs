const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/dist/app.js"), "utf8");
function render(name, context, argument) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf("\nfunction ", start + 1);
  vm.runInNewContext(`${source.slice(start, end)}\n${name}(argument);`, {
    escapeHtml: (value) => String(value),
    argument,
    ...context,
  });
}

function renderArgs(name, context, argument) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf("\nfunction ", start + 1);
  vm.runInNewContext(`${source.slice(start, end)}\n${name}(...argument);`, {
    escapeHtml: (value) => String(value),
    argument,
    ...context,
  });
}

test("workbench counts active subscriptions and excludes inactive ones", () => {
  const workbenchContext = { innerHTML: "", querySelectorAll: () => [] };
  render("renderWorkbenchContext", {
    el: { workbenchContext },
    state: { subscriptions: [{ status: "active" }, { status: "paused" }] },
  });
  assert.match(workbenchContext.innerHTML, /1 项订阅已启用/);
  assert.doesNotMatch(workbenchContext.innerHTML, /尚未启用订阅/);
});

test("intent preview shows explicit nationwide scope", () => {
  const intentPreview = { innerHTML: "", className: "" };
  render("renderIntentPreview", {
    el: { intentPreview },
    state: { intentConfirmation: {} },
    clarificationQuestions: () => [],
  }, { region: { scope: "domestic", aliases: ["全国"] }, topic: { core: ["服务器"] },
    time: { kind: "relative" }, schedule: { kind: "immediate" } });
  assert.match(intentPreview.innerHTML, /区域：全国/);
  assert.doesNotMatch(intentPreview.innerHTML, /未识别区域/);
});

test("partner profile renders six dimensions, evidence ledger, and Feishu receipts", () => {
  const partnerProfile = { innerHTML: "", className: "" };
  render("renderPartnerProfile", {
    el: { partnerProfile },
    state: {
      partnerProfile: {
        entity: { legal_name: "脱敏合作方", region: "北京", identity_status: "confirmed" },
        summary: { recommendation: "conditional", risk_level: "warning", evidence_completeness: 67, evidence_count: 3, last_updated_at: "2026-09-29" },
        current_review: { confirmed_by: "负责人", valid_until: "2027-03-31" },
        dimensions: [
          { label: "主体与股权", state: "covered", evidence_count: 1, risk_count: 0, missing_count: 0 },
          { label: "经营与信用", state: "risk", evidence_count: 1, risk_count: 1, missing_count: 0 },
          { label: "司法与合规", state: "missing", evidence_count: 0, risk_count: 0, missing_count: 1 },
          { label: "历史项目与履约", state: "covered", evidence_count: 1, risk_count: 0, missing_count: 0 },
          { label: "关系与冲突", state: "missing", evidence_count: 0, risk_count: 0, missing_count: 1 },
          { label: "舆情与外部事件", state: "missing", evidence_count: 0, risk_count: 0, missing_count: 1 },
        ],
        risk_summary: { risks: [], missing: [{ signal_status: "needs_evidence", fact_signal: "司法信息待补" }] },
        relationships: [], evidence: [], tasks: [{ title: "法务核验", question: "请核验", task_type: "legal", assignee_name: "负责人", due_at: "2026-10-06", feishu_task_status: "open", feishu_task_guid: "task-1" }],
      },
    },
    renderPartnerRiskCard: () => "",
    renderPartnerEvidenceCard: () => "",
    renderPartnerTaskCard: (item) => `<article>${item.title} 回执 ${item.feishu_task_guid}</article>`,
  });
  assert.match(partnerProfile.innerHTML, /六维企业画像/);
  assert.match(partnerProfile.innerHTML, /主体与股权/);
  assert.match(partnerProfile.innerHTML, /舆情与外部事件/);
  assert.match(partnerProfile.innerHTML, /企业证据账本/);
  assert.match(partnerProfile.innerHTML, /回执 task-1/);
  assert.match(partnerProfile.innerHTML, /缺失不等于负面/);
});

test("partner due diligence view declares responsive breakpoints and core controls", () => {
  const html = fs.readFileSync(path.join(__dirname, "../web/dist/index.html"), "utf8");
  const css = fs.readFileSync(path.join(__dirname, "../web/dist/styles.css"), "utf8");
  for (const id of ["partnerView", "partnerWorkspaceSelect", "partnerProfile", "partnerQuestionForm", "partnerReviewForm"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(css, /@media \(max-width: 1040px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /\.partner-dimensions/);
});

test("battle map list preserves evidence access when motion is disabled", () => {
  const battleEventList = { innerHTML: "", className: "" };
  const battleListMeta = { textContent: "" };
  renderArgs("renderBattleEventList", {
    el: { battleEventList, battleListMeta },
    compactDateTimeText: (value) => value,
  }, [[{ id: "event-1", layer: "opportunity", title: "服务器采购", region_name: "北京", event_time: "2026-09-29", coordinate_precision: "province", source_name: "ccgp" }], [], []]);
  assert.match(battleEventList.innerHTML, /data-battle-event="event-1"/);
  assert.match(battleEventList.innerHTML, /服务器采购/);
  assert.match(battleEventList.innerHTML, /province/);
  assert.match(battleListMeta.textContent, /1 条/);
});

test("battle map declares four layers, replay, evidence, and target viewports", () => {
  const html = fs.readFileSync(path.join(__dirname, "../web/dist/index.html"), "utf8");
  const css = fs.readFileSync(path.join(__dirname, "../web/dist/styles.css"), "utf8");
  for (const id of ["battleMapView", "battleMap", "battleTimelineRange", "battleImpactList", "battleEventList", "battleEvidenceDialog"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  for (const layer of ["opportunity", "award", "flow", "external"]) {
    assert.match(html, new RegExp(`data-battle-layer="${layer}"`));
  }
  assert.match(css, /\.battle-presentation \.battle-map/);
  assert.match(css, /@media \(max-width: 1180px\)/);
  assert.match(css, /@media \(max-width: 820px\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});

test("training center declares six phases, evidence boundaries, replay, and responsive layouts", () => {
  const html = fs.readFileSync(path.join(__dirname, "../web/dist/index.html"), "utf8");
  const css = fs.readFileSync(path.join(__dirname, "../web/dist/styles.css"), "utf8");
  for (const id of ["trainingView", "trainingScenarioList", "trainingPhaseRail", "trainingStage", "trainingReport", "trainingEvidenceList", "trainingTeamReadiness", "trainingHistory"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  for (const phase of ["开场", "基础事实", "证据追问", "风险变化", "行动计划", "总结"]) {
    assert.match(html, new RegExp(phase));
  }
  assert.match(html, /准备模式 · 不提前给答案/);
  assert.match(html, /模拟回答和场景变化不会写回正式公告/);
  assert.match(source, /FIVE-DIMENSION REPORT/);
  assert.match(source, /展开完整训练回放/);
  assert.match(source, /state\.trainingSession = null/);
  assert.match(css, /\.training-command/);
  assert.match(css, /@media \(max-width: 1250px\)/);
  assert.match(css, /@media \(max-width: 560px\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});

test("home prioritizes the core tender workflow and keeps secondary tools available", () => {
  const html = fs.readFileSync(path.join(__dirname, "../web/dist/index.html"), "utf8");
  const css = fs.readFileSync(path.join(__dirname, "../web/dist/styles.css"), "utf8");
  assert.match(html, /id="finalsHomeView" class="view active"/);
  assert.match(html, /从查项目到交标书，一条线完成/);
  for (const entrance of ["首页", "查招标", "投标项目", "团队协作"]) {
    assert.match(html, new RegExp(`>${entrance}<\\/button>`));
  }
  assert.match(html, /<summary>更多<\/summary>/);
  for (const view of ["radarView", "partnerView", "battleMapView", "trainingView", "sourcesView", "settingsView"]) {
    assert.match(html, new RegExp(`data-view="${view}"`));
  }
  assert.match(html, /class="primary-workflow"/);
  assert.match(html, /class="home-status-details"/);
  assert.doesNotMatch(html, /四层架构，共用同一组业务编号/);
  assert.match(html, /id="presentationExitButton"/);
  assert.match(html, /id="organizationMemberPicker"/);
  assert.match(html, /class="deferred-tool-section"/);
  assert.match(source, /\/api\/demo-reliability\?compact=true/);
  assert.match(source, /function routeFinalsIntent/);
  assert.match(source, /function renderOrganizationMemberPicker/);
  assert.match(css, /\.primary-workflow/);
  assert.match(css, /\.presentation-exit-button/);
  assert.match(css, /\.organization-member-choice/);
});
