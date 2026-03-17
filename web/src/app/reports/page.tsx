"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

export default function ReportsPage() {
  const [kpis, setKpis] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [totalReports, setTotalReports] = useState(0);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [pushFeishu, setPushFeishu] = useState(false);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const loadKpis = (d = days) => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - d * 86400000).toISOString();
    api.getKPIs({ start, end }).then(setKpis).catch(e => handleError(e, "加载KPI")).finally(() => setLoading(false));
  };

  const loadHistory = () => {
    api.listReports().then((r: any) => { setReports(r.reports || []); setTotalReports(r.total || 0); }).catch(e => handleError(e, "加载报表历史"));
  };

  useEffect(() => { loadKpis(); loadHistory(); }, []);

  const handleGenerate = async () => {
    setGenLoading(true);
    const end = customEnd || new Date().toISOString();
    const start = customStart || new Date(Date.now() - days * 86400000).toISOString();
    await api.generateReport({ start, end, report_type: "CUSTOM", feishu_webhook_url: webhookUrl || null, push_to_feishu: pushFeishu && !!webhookUrl })
      .then(() => { loadHistory(); loadKpis(); })
      .catch(e => handleError(e, "生成报表"))
      .finally(() => setGenLoading(false));
  };

  const KPICard = ({ label, value, color = "var(--accent)", sub = "" }: any) => (
    <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
      <div style={{ fontSize: "2rem", fontWeight: 800, color }}>{value ?? "—"}</div>
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );

  return (
    <div className="animate-in">
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>周报 / 月报</h1>
        <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
          {[7, 30, 90].map(d => (
            <button key={d} className={`btn ${days === d ? "btn-primary" : ""}`} onClick={() => { setDays(d); loadKpis(d); }}>{d}天</button>
          ))}
        </div>
      </div>

      {/* KPI Grid (all 8) */}
      {loading ? <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>加载中...</div> : kpis && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
          <KPICard label="低价发现总数" value={kpis.kpi1_violations_total} color="#ef4444" />
          <KPICard label="违规率" value={(kpis.kpi2_violation_rate * 100).toFixed(1) + "%"} color="#f97316" sub={`共 ${kpis.kpi2_total_offers} 条记录`} />
          <KPICard label="工单闭环率" value={(kpis.kpi3_workorder_close_rate * 100).toFixed(1) + "%"} color="#22c55e" sub={`${kpis.kpi3_workorder_resolved}/${kpis.kpi3_workorder_total}`} />
          <KPICard label="平均响应时长" value={kpis.kpi4_avg_response_hours ? kpis.kpi4_avg_response_hours.toFixed(1) + "h" : "N/A"} color="#6366f1" />
          <KPICard label="SLA 达成率" value={kpis.kpi4_sla_achievement_rate != null ? (kpis.kpi4_sla_achievement_rate * 100).toFixed(1) + "%" : "N/A"} color="#0ea5e9" />
          <KPICard label="违规最多平台" value={kpis.kpi5_top_platform || "N/A"} color="#a855f7" />
          <KPICard label="平均价差" value={kpis.kpi6_avg_gap_percent ? kpis.kpi6_avg_gap_percent.toFixed(1) + "%" : "N/A"} color="#f43f5e" />
          <KPICard label="白名单命中率" value={(kpis.kpi7_whitelist_hit_rate * 100).toFixed(1) + "%"} color="#14b8a6" sub={`${kpis.kpi7_whitelist_hit_count} 次命中`} />
          <KPICard label="工单复发率" value={(kpis.kpi8_reoccur_rate * 100).toFixed(1) + "%"} color="#fb923c" sub={`${kpis.kpi8_reoccur_count} 单复发`} />
        </div>
      )}

      {/* Generate Report Section */}
      <div className="card" style={{ padding: "1.5rem", marginBottom: "2rem" }}>
        <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>生成 & 推送报告</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>开始日期</label>
            <input type="date" className="input" style={{ display: "block" }} value={customStart} onChange={e => setCustomStart(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>结束日期</label>
            <input type="date" className="input" style={{ display: "block" }} value={customEnd} onChange={e => setCustomEnd(e.target.value)} />
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>飞书 Webhook URL（选填）</label>
            <input className="input" style={{ display: "block", width: "100%" }} placeholder="https://open.feishu.cn/open-apis/bot/..." value={webhookUrl} onChange={e => setWebhookUrl(e.target.value)} />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer", paddingTop: 18 }}>
            <input type="checkbox" checked={pushFeishu} onChange={e => setPushFeishu(e.target.checked)} />
            推送到飞书
          </label>
          <button className="btn btn-primary" style={{ paddingTop: 18 }} onClick={handleGenerate} disabled={genLoading}>
            {genLoading ? "生成中..." : "生成报告"}
          </button>
        </div>
      </div>

      {/* Report History */}
      <h2 style={{ fontWeight: 600, marginBottom: "1rem" }}>历史报告 ({totalReports})</h2>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr><th>ID</th><th>类型</th><th>周期</th><th>状态</th><th>推送时间</th><th>触发方式</th></tr>
          </thead>
          <tbody>
            {reports.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>暂无历史记录</td></tr>
            ) : reports.map((r: any) => (
              <tr key={r.id}>
                <td style={{ color: "var(--text-muted)" }}>#{r.id}</td>
                <td>{r.report_type}</td>
                <td style={{ fontSize: "0.8rem" }}>{r.start_date?.slice(0, 10)} ~ {r.end_date?.slice(0, 10)}</td>
                <td><span style={{ color: r.status === "DONE" ? "#22c55e" : r.status === "FAILED" ? "#ef4444" : "#eab308" }}>{r.status}</span></td>
                <td style={{ fontSize: "0.8rem" }}>{r.pushed_at ? new Date(r.pushed_at).toLocaleString("zh-CN") : "—"}</td>
                <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{r.triggered_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
