import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive,
  BadgeCheck,
  CheckCircle2,
  CirclePause,
  CircleX,
  ExternalLink,
  Flag,
  RefreshCw,
  Send,
  Settings,
  Trophy,
  UploadCloud,
  X,
  type LucideIcon,
} from "lucide-react";
import { bitable } from "@lark-opdev/block-bitable-api";
import "./styles.css";

type Intelligence = {
  score: number;
  level: string;
  level_label: string;
  stage: string;
  scores: Record<string, number>;
  risks: string[];
  recommended_actions: Array<{ role: string; action: string }>;
  project_target: string;
  strategy: string;
  market_signals: string[];
  competition?: {
    message?: string;
    evidence_excerpt?: string;
    historical_suppliers?: Array<{ name: string; count: number }>;
  };
  requirement_review?: {
    coverage_score: number;
    covered_count: number;
    total_count: number;
    missing: string[];
    recommendations: string[];
    basis: string;
    dimensions: Array<{ name: string; status: string; evidence?: string }>;
  };
  market_context?: {
    benchmark?: { message?: string; sample_count?: number };
    signals?: string[];
    sample_scope?: { notice_count?: number; budget_sample_count?: number };
  };
};

type RecordContext = {
  table: any;
  recordId: string;
  values: Record<string, string>;
};

type Workflow = {
  stage: string;
  stage_label: string;
  owner_name: string;
  owner_open_id: string;
  feishu_task_guid: string;
  feishu_task_status: string;
  qualification_score: number;
  qualification_status: string;
  decision: string;
  decision_reason: string;
  decision_by: string;
  due_at: string;
};

type Qualification = {
  score: number;
  status: string;
  blockers?: Record<string, string[]>;
};

type OpportunityWorkspace = {
  opportunity: {
    intelligence?: Intelligence;
    workflow?: Workflow;
    qualification?: Qualification;
    action_state?: Record<string, unknown>;
    action_contract?: ActionContract;
  };
};

type WorkflowAction = {
  action: string;
  label: string;
  intent: string;
  group: string;
  enabled: boolean;
  blocked_reasons: string[];
  accepts_reason: boolean;
  requires_member_identity: boolean;
};

type ActionContract = {
  version: number;
  stage: string;
  stage_label: string;
  actions: WorkflowAction[];
};

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const fieldLabels: Record<string, string> = {
  title: "标题",
  publish_time: "发布时间",
  region: "地区",
  purchaser: "采购人",
  project_no: "项目编号",
  source_url: "来源链接",
  source_site: "来源",
  core_content: "核心内容",
  budget: "预算",
  bid_deadline: "投标截止",
};

function textValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join(" ");
  if (typeof value === "object") {
    const item = value as Record<string, unknown>;
    return textValue(item.text || item.name || item.link || item.value || "");
  }
  return "";
}

async function currentRecord(): Promise<RecordContext> {
  const selection = (await bitable.base.getSelection()) as any;
  if (!selection?.tableId || !selection?.recordId) {
    throw new Error("请先在多维表格中展开一条记录");
  }
  const table = await bitable.base.getTableById(selection.tableId);
  const [record, fieldList] = await Promise.all([
    table.getRecordById(selection.recordId),
    table.getFieldList(),
  ]);
  const metas = await Promise.all(fieldList.map((field: any) => table.getFieldMetaById(field.id)));
  const values: Record<string, string> = {};
  metas.forEach((meta: any) => {
    values[meta.name] = textValue(record.fields?.[meta.id]);
  });
  return { table, recordId: selection.recordId, values };
}

function apiConfig() {
  return {
    base: localStorage.getItem("tendertrace_api_base") || "http://127.0.0.1:8000",
    token: localStorage.getItem("tendertrace_api_token") || "",
  };
}

async function request(path: string, options: RequestInit = {}) {
  const config = apiConfig();
  const response = await fetch(`${config.base.replace(/\/$/, "")}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(config.token ? { "X-TenderTrace-Token": config.token } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail?.reasons) && detail.reasons.length
        ? detail.reasons.join("；")
        : detail?.message || payload.message || `TenderTrace API ${response.status}`;
    throw new ApiError(response.status, message);
  }
  return response.json();
}

function actionIcon(action: string): LucideIcon {
  return {
    archive: Archive,
    approve_bid: CheckCircle2,
    claim: Send,
    hold: CirclePause,
    mark_lost: CircleX,
    mark_won: Trophy,
    prepare_bid: CheckCircle2,
    pursue: Flag,
    reject: CircleX,
  }[action] || Flag;
}

function payloadFrom(values: Record<string, string>) {
  const payload: Record<string, string> = { ...values };
  Object.entries(fieldLabels).forEach(([key, label]) => {
    payload[key] = values[label] || "";
  });
  return payload;
}

function QualityLine({ label, value }: { label: string; value: number }) {
  const score = Math.max(0, Math.min(value || 0, 100));
  return (
    <div className="quality-line">
      <span>{label}</span><i><b style={{ width: `${score}%` }} /></i><strong>{score}</strong>
    </div>
  );
}

function App() {
  const [context, setContext] = useState<RecordContext | null>(null);
  const [intelligence, setIntelligence] = useState<Intelligence | null>(null);
  const [workspace, setWorkspace] = useState<OpportunityWorkspace | null>(null);
  const [baseActorId, setBaseActorId] = useState("");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [acting, setActing] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiBase, setApiBase] = useState(apiConfig().base);
  const [apiToken, setApiToken] = useState(apiConfig().token);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const next = await currentRecord();
      const nextNoticeId = next.values["公告ID"]?.trim() || "";
      const workspaceRequest = nextNoticeId
        ? request(`/api/opportunities/${encodeURIComponent(nextNoticeId)}/facts`).catch((error) => {
            if (error instanceof ApiError && error.status === 404) return null;
            throw error;
          })
        : Promise.resolve(null);
      const [result, linkedWorkspace, userId] = await Promise.all([
        request("/api/opportunities/analyze", {
          method: "POST",
          body: JSON.stringify(payloadFrom(next.values)),
        }),
        workspaceRequest,
        bitable.bridge.getBaseUserId().catch(() => ""),
      ]);
      setContext(next);
      setWorkspace(linkedWorkspace);
      setBaseActorId(userId);
      setIntelligence(linkedWorkspace?.opportunity?.intelligence || result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return bitable.base.onSelectionChange(() => load());
  }, [load]);

  const title = context?.values["标题"] || "当前机会";
  const sourceUrl = context?.values["来源链接"] || "";
  const noticeId = context?.values["公告ID"] || "";
  const factFieldCount = ["采购人", "项目编号", "预算", "投标截止", "地区"]
    .filter((name) => Boolean(context?.values[name]?.trim())).length;
  const factStatus = context?.values["事实核验状态"] || "待核验";
  const factEvidenceReady = Boolean(context?.values["事实核验证据"]?.trim());
  const workflow = workspace?.opportunity?.workflow || null;
  const qualification = workspace?.opportunity?.qualification || null;
  const availableActions = workspace?.opportunity?.action_contract?.actions || [];
  const claimAction = availableActions.find((item) => item.requires_member_identity);
  const directActions = availableActions.filter((item) => !item.requires_member_identity);
  const quality = intelligence?.scores || {};
  const marketBenchmark = intelligence?.market_context?.benchmark;
  const marketContextSignals = intelligence?.market_context?.signals || [];
  const competition = intelligence?.competition;
  const requirementReview = intelligence?.requirement_review;
  const actionCount = intelligence?.recommended_actions?.length || 0;
  const riskCount =
    (intelligence?.risks?.length || 0) +
    (intelligence?.market_signals?.length || 0) +
    marketContextSignals.length;
  const statusText = useMemo(
    () => intelligence ? `${intelligence.level} 级 · ${intelligence.level_label}` : "等待研判",
    [intelligence],
  );

  function saveSettings() {
    localStorage.setItem("tendertrace_api_base", apiBase.trim().replace(/\/$/, ""));
    if (apiToken.trim()) localStorage.setItem("tendertrace_api_token", apiToken.trim());
    else localStorage.removeItem("tendertrace_api_token");
    setSettingsOpen(false);
    load();
  }

  async function writeBack() {
    if (!context || !intelligence) return;
    const updates: Record<string, string> = {
      "机会等级": `${intelligence.level} · ${intelligence.level_label}`,
      "机会评分": String(intelligence.score),
      "信息完整度": String(quality.completeness || 0),
      "信息可信度": String(quality.credibility || 0),
      "时效评分": String(quality.freshness || 0),
      "销售阶段": workflow?.stage_label || intelligence.stage,
      "项目目标": intelligence.project_target,
      "建议策略": intelligence.strategy,
      "跟进建议": intelligence.recommended_actions.map((item) => `${item.role}：${item.action}`).join("\n"),
      "风险提示": intelligence.risks.join("\n"),
      "市场价格位置": marketBenchmark?.message || "样本不足",
      "市场样本数": String(marketBenchmark?.sample_count || 0),
      "竞争情报": competition?.message || "样本不足",
      "竞争证据": competition?.evidence_excerpt || "",
      "历史竞争者": (competition?.historical_suppliers || []).map((item) => `${item.name}（${item.count} 次）`).join("、"),
      "需求覆盖率": `${requirementReview?.coverage_score || 0}/100 · ${requirementReview?.covered_count || 0}/${requirementReview?.total_count || 0} 项`,
      "需求待核对": (requirementReview?.missing || []).join("、"),
      "需求优化建议": (requirementReview?.recommendations || []).join("\n"),
    };
    try {
      for (const [name, value] of Object.entries(updates)) {
        const field = await context.table.getFieldByName(name).catch(() => null);
        if (field) {
          await context.table.setCellValue(field.id, context.recordId, [{ type: "text", text: value }]);
        }
      }
      setMessage("研判结果已同步到当前记录");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "同步失败");
    }
  }

  async function sendFeishu() {
    if (!noticeId) {
      setMessage("当前记录缺少公告ID，请先从 TenderTrace 同步该记录");
      return;
    }
    try {
      await request("/api/opportunities/send-feishu", {
        method: "POST",
        body: JSON.stringify({ notice_id: noticeId }),
      });
      setMessage(workflow?.stage === "identified" ? "认领卡已发送，请在飞书会话中点击认领" : "机会情报已发送到默认飞书会话");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "发送失败");
    }
  }

  async function applyWorkflowAction(action: string) {
    if (!noticeId || !baseActorId) {
      setMessage(!noticeId ? "当前记录缺少公告ID" : "无法读取当前飞书成员标识，请刷新后重试");
      return;
    }
    setActing(action);
    try {
      await request(`/api/opportunities/${encodeURIComponent(noticeId)}/actions`, {
        method: "POST",
        body: JSON.stringify({
          action,
          actor_open_id: `base:${baseActorId}`,
          actor_name: context?.values["负责人"] || context?.values["事实核验人"] || "飞书记录视图用户",
          reason: decisionReason.trim(),
          channel: "feishu_record_view",
        }),
      });
      await load();
      setDecisionReason("");
      setMessage("机会阶段已更新，并同步到飞书台账");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "机会动作执行失败");
    } finally {
      setActing("");
    }
  }

  async function verifyFacts() {
    setVerifying(true);
    try {
      const current = await currentRecord();
      const currentNoticeId = current.values["公告ID"]?.trim() || "";
      const facts = Object.fromEntries(
        [
          ["purchaser", current.values["采购人"]],
          ["project_no", current.values["项目编号"]],
          ["budget", current.values["预算"]],
          ["bid_deadline", current.values["投标截止"]],
          ["region", current.values["地区"]],
        ].filter((item): item is [string, string] => Boolean(item[1]?.trim())),
      );
      const sourceUrl = current.values["来源链接"]?.trim() || "";
      const evidenceText = current.values["事实核验证据"]?.trim() || "";
      if (!currentNoticeId) {
        setMessage("当前记录缺少公告ID，请先从 TenderTrace 同步该记录");
        return;
      }
      if (!sourceUrl) {
        setMessage("当前记录缺少来源链接");
        return;
      }
      if (!evidenceText) {
        setMessage("请先填写“事实核验证据”字段");
        return;
      }
      if (!Object.keys(facts).length) {
        setMessage("当前记录没有可核验的事实字段");
        return;
      }
      const result = await request(`/api/opportunities/${encodeURIComponent(currentNoticeId)}/facts`, {
        method: "PATCH",
        body: JSON.stringify({
          facts,
          source_url: sourceUrl,
          evidence_text: evidenceText,
          note: current.values["事实核验备注"] || "",
          actor: current.values["事实核验人"] || "飞书记录视图",
          channel: "feishu_record_view",
        }),
      });
      if (result?.opportunity?.intelligence) setIntelligence(result.opportunity.intelligence);
      await load();
      setMessage(
        result.status === "unchanged"
          ? "事实未变化，无需重复写入"
          : "事实已核验，机会等级与销售准入已重新计算",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "事实核验失败");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <main>
      <header>
        <div><span className="eyebrow">TENDERTRACE</span><h1>机会研判</h1></div>
        <div className="toolbar">
          <button title="刷新当前记录" aria-label="刷新当前记录" onClick={load}><RefreshCw size={17} /></button>
          <button title="连接设置" aria-label="连接设置" onClick={() => setSettingsOpen(true)}><Settings size={17} /></button>
        </div>
      </header>

      {settingsOpen && (
        <section className="settings-panel">
          <div className="section-title"><strong>连接设置</strong><button aria-label="关闭" onClick={() => setSettingsOpen(false)}><X size={16} /></button></div>
          <label>TenderTrace API<input value={apiBase} onChange={(event) => setApiBase(event.target.value)} /></label>
          <label>API Token（可选）<input type="password" value={apiToken} onChange={(event) => setApiToken(event.target.value)} /></label>
          <button className="primary" onClick={saveSettings}>保存并重连</button>
        </section>
      )}

      {loading ? (
        <div className="loading"><span />正在读取当前记录</div>
      ) : intelligence ? (
        <>
          <section className="record-head">
            <div className={`grade grade-${intelligence.level.toLowerCase()}`}><strong>{intelligence.level}</strong><span>{intelligence.score} 分</span></div>
            <div><span className="stage">{statusText} · {intelligence.stage}</span><h2>{title}</h2><p>{context?.values["采购人"] || "采购人待确认"} · {context?.values["地区"] || "地区待确认"}</p></div>
          </section>

          <section className="quality-grid">
            <QualityLine label="时效" value={quality.freshness} />
            <QualityLine label="完整" value={quality.completeness} />
            <QualityLine label="可信" value={quality.credibility} />
            <QualityLine label="行动" value={quality.readiness} />
          </section>

          <section className="decision-section">
            <div><span>项目目标</span><strong>{intelligence.project_target}</strong></div>
            <div><span>建议策略</span><strong>{intelligence.strategy}</strong></div>
          </section>

          <section className="workflow-section">
            <div className="section-title">
              <strong>机会工作流</strong>
              <span>{workflow ? workflow.stage_label : "未关联本地机会"}</span>
            </div>
            {workflow ? (
              <>
                <div className="workflow-grid">
                  <div><span>负责人</span><strong>{workflow.owner_name || "待认领"}</strong></div>
                  <div><span>资格评估</span><strong>{qualification?.score ?? workflow.qualification_score} · {qualification?.status || workflow.qualification_status}</strong></div>
                  <div><span>飞书任务</span><strong>{workflow.feishu_task_status || "not_created"}</strong></div>
                  <div><span>投标决策</span><strong>{workflow.decision || "待决策"}</strong></div>
                </div>
                {workflow.decision_reason && (
                  <p className="workflow-reason">{workflow.decision_reason}{workflow.decision_by ? ` · ${workflow.decision_by}` : ""}</p>
                )}
                {claimAction && (
                  <div className="claim-gate">
                    <p>首次认领需由成员在飞书机会卡中确认，认领后才能正确分派任务。</p>
                    <button className="primary" disabled={!claimAction.enabled} onClick={sendFeishu}>
                      <Send size={16} />发送认领卡
                    </button>
                  </div>
                )}
                {directActions.length ? (
                  <>
                    {directActions.some((item) => item.accepts_reason) && (
                      <label className="decision-reason">
                        决策依据
                        <textarea
                          value={decisionReason}
                          onChange={(event) => setDecisionReason(event.target.value)}
                          placeholder="补充判断依据、待办条件或风险说明"
                          rows={2}
                        />
                      </label>
                    )}
                    <div className="workflow-actions">
                      {directActions.map((item) => {
                        const Icon = actionIcon(item.action);
                        return (
                          <button
                            className={item.intent === "danger" ? "danger" : ""}
                            disabled={Boolean(acting) || !item.enabled}
                            key={item.action}
                            onClick={() => applyWorkflowAction(item.action)}
                            title={item.blocked_reasons.join("；")}
                          >
                            <Icon size={15} />{acting === item.action ? "处理中" : item.label}
                          </button>
                        );
                      })}
                    </div>
                    {directActions.some((item) => !item.enabled) && (
                      <div className="workflow-blockers">
                        {directActions
                          .filter((item) => !item.enabled)
                          .map((item) => <p key={item.action}>{item.label}：{item.blocked_reasons.join("、")}</p>)}
                      </div>
                    )}
                  </>
                ) : !claimAction && <p className="workflow-hint">当前阶段没有待执行动作。</p>}
              </>
            ) : (
              <p className="workflow-hint">
                当前行可进行即时研判，但只有从 TenderTrace 入库并带有公告ID的记录才能进入销售工作流。
              </p>
            )}
          </section>

          <section className="fact-verification">
            <div className="section-title"><strong>事实核验</strong><span>{factStatus}</span></div>
            <div className="verification-grid">
              <div><span>业务字段</span><strong>{factFieldCount} / 5</strong></div>
              <div><span>证据摘录</span><strong>{factEvidenceReady ? "已填写" : "待补充"}</strong></div>
            </div>
            <button className="verify-button" disabled={verifying} onClick={verifyFacts}>
              <BadgeCheck size={16} />{verifying ? "核验中" : "核验并重算"}
            </button>
          </section>

          <section>
            <div className="section-title"><strong>市场与竞争</strong><span>{competition?.historical_suppliers?.length || 0} 家样本</span></div>
            <div className="decision-section market-section">
              <div><span>价格位置</span><strong>{marketBenchmark?.message || "同品类预算样本不足"}</strong></div>
              <div><span>竞争结论</span><strong>{competition?.message || "同品类结果样本不足"}</strong></div>
            </div>
            {!!competition?.historical_suppliers?.length && (
              <div className="supplier-list">
                {competition.historical_suppliers.slice(0, 5).map((item, index) => <span key={index}>{item.name} · {item.count}</span>)}
              </div>
            )}
            {competition?.evidence_excerpt && <blockquote>{competition.evidence_excerpt}</blockquote>}
          </section>

          <section>
            <div className="section-title"><strong>需求覆盖</strong><span>{requirementReview?.covered_count || 0} / {requirementReview?.total_count || 0} 项</span></div>
            <div className="requirement-grid">
              {(requirementReview?.dimensions || []).map((item, index) => (
                <div className={item.status === "covered" ? "covered" : "verify"} key={index}>
                  <span>{item.status === "covered" ? "已覆盖" : "待核对"}</span><strong>{item.name}</strong>
                </div>
              ))}
            </div>
            {!!requirementReview?.recommendations?.length && (
              <div className="advice-list">
                {requirementReview.recommendations.map((item, index) => <p key={index}>{item}</p>)}
              </div>
            )}
            {requirementReview?.basis && <small className="basis">{requirementReview.basis}</small>}
          </section>

          <section>
            <div className="section-title"><strong>角色行动</strong><span>{actionCount}</span></div>
            <div className="action-list">
              {intelligence.recommended_actions.map((item, index) => <div key={index}><span>{item.role}</span><strong>{item.action}</strong></div>)}
            </div>
          </section>

          <section>
            <div className="section-title"><strong>风险与市场信号</strong><span>{riskCount}</span></div>
            <div className="signal-list">
              {intelligence.risks.map((item, index) => <p className="risk" key={`risk-${index}`}>{item}</p>)}
              {marketContextSignals.map((item, index) => <p key={`context-${index}`}>{item}</p>)}
              {intelligence.market_signals.map((item, index) => <p key={`signal-${index}`}>{item}</p>)}
            </div>
          </section>

          <footer>
            <button className="primary" onClick={writeBack}><UploadCloud size={16} />同步到记录</button>
            <button onClick={sendFeishu}><Send size={16} />发送飞书</button>
            {sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} />原文</a>}
          </footer>
        </>
      ) : <div className="empty">{message || "未能读取当前记录"}</div>}
      {message && intelligence && <div className="notice">{message}</div>}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
