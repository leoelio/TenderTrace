import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { ExternalLink, RefreshCw, Send, Settings, UploadCloud, X } from "lucide-react";
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
};

type RecordContext = {
  table: any;
  recordId: string;
  values: Record<string, string>;
};

const fieldLabels: Record<string, string> = {
  title: "标题",
  publish_time: "发布时间",
  region: "地区",
  purchaser: "采购人",
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
    throw new Error(payload.detail || `TenderTrace API ${response.status}`);
  }
  return response.json();
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
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiBase, setApiBase] = useState(apiConfig().base);
  const [apiToken, setApiToken] = useState(apiConfig().token);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const next = await currentRecord();
      const result = await request("/api/opportunities/analyze", {
        method: "POST",
        body: JSON.stringify(payloadFrom(next.values)),
      });
      setContext(next);
      setIntelligence(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const title = context?.values["标题"] || "当前机会";
  const sourceUrl = context?.values["来源链接"] || "";
  const noticeId = context?.values["公告ID"] || "";
  const quality = intelligence?.scores || {};
  const actionCount = intelligence?.recommended_actions?.length || 0;
  const riskCount = intelligence?.risks?.length || 0;
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
      "销售阶段": intelligence.stage,
      "项目目标": intelligence.project_target,
      "建议策略": intelligence.strategy,
      "跟进建议": intelligence.recommended_actions.map((item) => `${item.role}：${item.action}`).join("\n"),
      "风险提示": intelligence.risks.join("\n"),
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
      setMessage("机会情报已发送到默认飞书会话");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "发送失败");
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
