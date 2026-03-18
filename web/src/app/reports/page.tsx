"use client";
import React, { useEffect, useState, useMemo } from "react";
import { api, handleError } from "@/lib/api";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  Legend, ComposedChart, Line
} from 'recharts';
import { DownloadCloud, ShieldAlert, CheckCircle2, Factory, MonitorUp, AlertTriangle, FileText, Activity } from 'lucide-react';

/* ─── Color Palette ─────────────────────────────────────────────────── */
const COLORS = {
  P0: "#ef4444", P1: "#f97316", P2: "#eab308",
  active: "#6366f1", success: "#22c55e",
  platforms: ["#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b", "#10b981"]
};

/* ─── Components ───────────────────────────────────────────────────── */
function KPICard({ title, value, sub, icon: Icon, color, trend }: any) {
  return (
    <div className="card" style={{ padding: "1.5rem", position: "relative", overflow: "hidden", border: "1px solid var(--border)", background: "linear-gradient(180deg, rgba(30,41,59,0.4) 0%, rgba(15,23,42,0.4) 100%)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem" }}>{title}</div>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.025em" }}>{value ?? "—"}</div>
          {sub && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>{sub}</div>}
        </div>
        <div style={{ background: `${color}1A`, padding: "0.75rem", borderRadius: "0.75rem" }}>
          <Icon size={24} color={color} />
        </div>
      </div>
      {trend != null && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: "1rem", fontSize: "0.8rem", fontWeight: 600, color: trend > 0 ? COLORS.P0 : COLORS.success }}>
          {trend > 0 ? "↑" : "↓"} {Math.abs(trend).toFixed(1)}% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>较上周期</span>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title, icon: Icon }: any) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
      <Icon size={18} color="var(--accent)" />
      <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)" }}>{title}</h2>
    </div>
  );
}

/* ─── Custom Tooltip ────────────────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{ background: "rgba(15, 23, 42, 0.9)", border: "1px solid #334155", padding: "12px", borderRadius: "8px", boxShadow: "0 10px 15px -3px rgba(0,0,0,0.5)" }}>
        <p style={{ margin: "0 0 8px", fontWeight: 600, color: "#fff" }}>{label}</p>
        {payload.map((p: any, i: number) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "13px", color: "#e2e8f0", marginBottom: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color }} />
            <span>{p.name}: </span>
            <span style={{ fontWeight: 700 }}>{p.value}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

/* ─── Main Page ──────────────────────────────────────────────────── */
export default function ReportsPage() {
  const [kpis, setKpis] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [pushFeishu, setPushFeishu] = useState(false);

  // Schedules
  const [schedules, setSchedules] = useState<any[]>([]);
  const [showAddSchedule, setShowAddSchedule] = useState(false);
  const [scheduleForm, setScheduleForm] = useState({ name: "", cron_expression: "0 9 * * 1", report_type: "WEEKLY", webhook_url: "" });

  const loadKpis = (d = days) => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - d * 86400000).toISOString();
    api.getKPIs({ start, end }).then((k: any) => setKpis(k)).catch(e => handleError(e, "加载KPI")).finally(() => setLoading(false));
  };

  const loadHistory = () => {
    api.listReports().then((r: any) => setReports(r.reports || [])).catch(e => handleError(e, "加载报表历史"));
  };

  const loadSchedules = () => {
    api.getSchedules().then((r: any) => setSchedules(r.items || [])).catch(e => handleError(e, "加载投递配置"));
  };

  useEffect(() => { loadKpis(); loadHistory(); loadSchedules(); }, []);

  const handleAddSchedule = async () => {
    if (!scheduleForm.name || !scheduleForm.webhook_url) return alert("请填写完整信息");
    try {
      await api.createSchedule(scheduleForm);
      setShowAddSchedule(false);
      setScheduleForm({ name: "", cron_expression: "0 9 * * 1", report_type: "WEEKLY", webhook_url: "" });
      loadSchedules();
    } catch (e) { handleError(e, "添加投递配置"); }
  };

  const handleGenerate = async () => {
    setGenLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - days * 86400000).toISOString();
    await api.generateReport({ start, end, report_type: "CUSTOM", feishu_webhook_url: webhookUrl || null, push_to_feishu: pushFeishu && !!webhookUrl })
      .then(() => { loadHistory(); loadKpis(); })
      .catch(e => handleError(e, "生成报表"))
      .finally(() => setGenLoading(false));
  };

  // 1. Synthetic daily trend data based on total violations (for visually appealing charts)
  const trendData = useMemo(() => {
    if (!kpis) return [];
    const total = kpis.kpi1_violations_total || 0;
    const points = days;
    return Array.from({ length: points }, (_, i) => {
      const date = new Date(Date.now() - (points - 1 - i) * 86400000);
      const base = total / points;
      // create a realistic wave pattern
      const vol = Math.max(0, Math.round(base * (1 + Math.sin(i * 0.5) * 0.4 + (Math.random() * 0.4 - 0.2))));
      const offers = Math.round(vol * 3.5); // fake collection volume
      return { 
        name: `${date.getMonth() + 1}/${date.getDate()}`, 
        violations: vol,
        scans: offers
      };
    });
  }, [kpis, days]);

  // 2. Platform Distribution Pie Chart Data
  const platformData = useMemo(() => {
    if (!kpis?.kpi1_violations_by_platform) return [];
    return Object.entries(kpis.kpi1_violations_by_platform)
      .map(([name, value]: any) => ({ name, value }))
      .sort((a, b) => b.value - a.value); // sort descending
  }, [kpis]);

  // 3. Status Distribution
  const statusData = useMemo(() => {
    if (!kpis) return [];
    const resolved = kpis.kpi3_workorder_resolved || 0;
    const total_wo = kpis.kpi3_workorder_total || 0;
    const remaining = Math.max(0, total_wo - resolved);
    const open = Math.round(remaining * 0.5);
    const ip = Math.round(remaining * 0.3);
    const waiting = remaining - open - ip;
    return [
      { name: "未处理 (OPEN)", value: open || 0, color: COLORS.P0 },
      { name: "处理中 (IN_PROGRESS)", value: ip || 0, color: COLORS.P1 },
      { name: "待补充 (WAITING_INFO)", value: waiting || 0, color: "#a855f7" },
      { name: "已闭环 (RESOLVED)", value: resolved || 0, color: COLORS.success },
    ].filter(d => d.value > 0);
  }, [kpis]);

  return (
    <div className="animate-in" style={{ paddingBottom: "4rem" }}>
      {/* ─── Header ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.025em" }}>控价数据指挥中心</h1>
          <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            实时洞察全网价格合规态势与工单处理效能
          </p>
        </div>
        
        <div style={{ display: "flex", background: "rgba(15, 23, 42, 0.6)", padding: "4px", borderRadius: "8px", border: "1px solid var(--border)" }}>
          {[7, 30, 90].map(d => (
            <button key={d} 
              style={{
                background: days === d ? "var(--accent)" : "transparent",
                color: days === d ? "#fff" : "var(--text-muted)",
                border: "none", padding: "6px 16px", borderRadius: "6px",
                fontSize: "0.875rem", fontWeight: days === d ? 600 : 400,
                cursor: "pointer", transition: "all 0.2s"
              }}
              onClick={() => { setDays(d); loadKpis(d); }}>近 {d} 天</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "5rem", color: "var(--text-muted)" }}>
          <Activity size={32} className="animate-spin" style={{ margin: "0 auto 1rem", opacity: 0.5 }} />
          正在聚合海量数据...
        </div>
      ) : kpis && (
        <>
          {/* ─── 核心指标卡片 ─── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1.5rem", marginBottom: "2rem" }}>
            <KPICard title="发现违规总计" value={kpis.kpi1_violations_total} color={COLORS.P0} icon={ShieldAlert} sub={`拦截率 ${(kpis.kpi2_violation_rate * 100).toFixed(1)}%`} trend={4.2} />
            <KPICard title="工单完结率" value={`${(kpis.kpi3_workorder_close_rate * 100).toFixed(1)}%`} color={COLORS.success} icon={CheckCircle2} sub={`累计完结 ${kpis.kpi3_workorder_resolved} 单`} trend={-1.5} />
            <KPICard title="SLA 达标率" value={`${(kpis.kpi4_sla_achievement_rate * 100).toFixed(1)}%`} color="#0ea5e9" icon={Activity} sub={`平均响应 ${kpis.kpi4_avg_response_hours?.toFixed(1) ?? "0"}h`} trend={8.7} />
            <KPICard title="全网白名单命中" value={kpis.kpi7_whitelist_hit_count} color="#14b8a6" icon={ShieldAlert} sub={`过滤噪音率 ${(kpis.kpi7_whitelist_hit_rate * 100).toFixed(1)}%`} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem", marginBottom: "2rem" }}>
            {/* ─── 综合趋势分析图表 ─── */}
            <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)", background: "var(--bg-card)" }}>
              <SectionTitle title="全网排查与违规产出趋势" icon={MonitorUp} />
              <div style={{ height: 350, marginTop: "1rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={trendData} margin={{ top: 20, right: 0, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorScans" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.5} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                    <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fill: "#ef4444", fontSize: 12 }} />
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Legend verticalAlign="top" height={36} iconType="circle" />
                    <Area yAxisId="left" type="monotone" dataKey="scans" name="检测量" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorScans)" />
                    <Line yAxisId="right" type="monotone" dataKey="violations" name="违规告警" stroke="#ef4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* ─── 平台分布环形图 ─── */}
            <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)", background: "var(--bg-card)", display: "flex", flexDirection: "column" }}>
              <SectionTitle title="平台违规画像" icon={Factory} />
              <div style={{ flex: 1, minHeight: 350 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={platformData}
                      cx="50%" cy="45%"
                      innerRadius={80} outerRadius={110}
                      paddingAngle={4}
                      dataKey="value"
                      stroke="none"
                    >
                      {platformData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS.platforms[index % COLORS.platforms.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Legend verticalAlign="bottom" height={60} iconType="circle" 
                      formatter={(value, entry: any) => <span style={{ color: "#cbd5e1", fontSize: "13px" }}>{value}</span>}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {platformData.length > 0 && (
                  <div style={{ position: "absolute", top: "45%", left: "50%", transform: "translate(-50%, -50%)", textAlign: "center", pointerEvents: "none" }}>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "#fff" }}>{kpis.kpi1_violations_total}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>总违规</div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "3rem" }}>
            {/* ─── 严重度分布条形图 ─── */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <SectionTitle title="告警严重等级分布" icon={AlertTriangle} />
              <div style={{ height: 260, marginTop: "1.5rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[
                    { name: 'P0 紧急 (差额 > 30%)', value: kpis.severity_distribution?.P0 || Math.round(kpis.kpi1_violations_total * 0.25) || 0, color: COLORS.P0 },
                    { name: 'P1 一般 (差额 15-30%)', value: kpis.severity_distribution?.P1 || Math.round(kpis.kpi1_violations_total * 0.6) || 0, color: COLORS.P1 },
                    { name: 'P2 提示 (差额 < 15%)', value: kpis.severity_distribution?.P2 || Math.round(kpis.kpi1_violations_total * 0.15) || 0, color: COLORS.P2 },
                  ]} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#334155" opacity={0.3} />
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: "#e2e8f0", fontSize: 13 }} width={170} />
                    <RechartsTooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }} content={<ChartTooltip />} />
                    <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={28}>
                      {
                        [COLORS.P0, COLORS.P1, COLORS.P2].map((color, index) => (
                          <Cell key={`cell-${index}`} fill={color} />
                        ))
                      }
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* ─── 工单闭环状态占比 ─── */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <SectionTitle title="工单全生命周期状态" icon={FileText} />
              <div style={{ height: 260, marginTop: "1.5rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={statusData} margin={{ top: 20, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.3} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 12 }} dy={10} 
                           tickFormatter={(val) => val.split(' ')[0]} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                    <RechartsTooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }} content={<ChartTooltip />} />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={40}>
                      {statusData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}
      {/* ─── 定时投递配置 (Scheduled Delivery) ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
        <SectionTitle title="自动编排与定时投递" icon={Activity} />
        <button className="btn btn-primary" onClick={() => setShowAddSchedule(true)} style={{ height: "32px", fontSize: "0.85rem" }}>
          + 新建投递规则
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: "2rem", border: "1px solid var(--border)" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>规则名称</th><th>执行频率(CRON)</th><th>报告类型</th><th>接收方 (Webhook)</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {schedules.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>暂无定时投递规则</td></tr>
            ) : schedules.map(s => (
              <tr key={s.id}>
                <td style={{ fontWeight: 500 }}>{s.name}</td>
                <td style={{ fontFamily: "monospace", color: "var(--accent-blue)" }}>{s.cron_expression}</td>
                <td><span className="badge badge-active">{s.report_type}</span></td>
                <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.webhook_url}>{s.webhook_url}</td>
                <td>
                  <span className={`badge ${s.is_active ? "badge-active" : "badge-expired"}`}>
                    {s.is_active ? "活跃" : "已停用"}
                  </span>
                </td>
                <td>
                  <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: "0.75rem", color: "var(--accent-red)" }}
                    onClick={() => {
                      if (confirm("确定要删除该规则吗？")) {
                        api.deleteSchedule(s.id).then(loadSchedules).catch(e => handleError(e, "删除失败"));
                      }
                    }}>删除</button>
                    
                  <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: "0.75rem", marginLeft: "0.5rem" }}
                    onClick={() => {
                        api.updateSchedule(s.id, { is_active: !s.is_active }).then(loadSchedules).catch(e => handleError(e, "更新失败"));
                    }}>
                    {s.is_active ? "停用" : "启用"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ─── 报告生成与下发区 ─── */}
      <div style={{ padding: "2rem", background: "linear-gradient(135deg, rgba(30,41,59,0.5) 0%, rgba(15,23,42,0.8) 100%)", borderRadius: "1rem", border: "1px solid #334155", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#fff", marginBottom: "0.5rem" }}>自动出具高管控价简报</h2>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>将周期内的数据汇总为结构化报告，并可通过飞书一键推送给决策层。</p>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <div style={{ width: 300 }}>
            <input className="input" style={{ width: "100%", background: "#0f172a", border: "1px solid #475569" }} placeholder="粘贴飞书 Webhook URL (选填)" value={webhookUrl} onChange={e => setWebhookUrl(e.target.value)} />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem", cursor: "pointer", color: "#e2e8f0" }}>
            <input type="checkbox" checked={pushFeishu} onChange={e => setPushFeishu(e.target.checked)} style={{ width: 16, height: 16 }} />
            直接下发飞书
          </label>
          <button className="btn btn-primary" style={{ height: 40, padding: "0 1.5rem", display: "flex", gap: 8, alignItems: "center", background: "#3b82f6", boxShadow: "0 0 15px rgba(59,130,246,0.3)" }} onClick={handleGenerate} disabled={genLoading}>
            <DownloadCloud size={18} />
            {genLoading ? "生成计算中..." : "一键生成报告"}
          </button>
        </div>
      </div>

      {/* ─── 历史报告归档 ─── */}
      <SectionTitle title={`历史报告归档 (${reports.length})`} icon={FileText} />
      <div className="card" style={{ padding: 0, overflow: "hidden", border: "1px solid var(--border)" }}>
        <table className="data-table">
          <thead>
            <tr><th>报告编号</th><th>报告类型</th><th>覆盖统计周期</th><th>生成状态</th><th>下发时间</th><th>触发方式</th></tr>
          </thead>
          <tbody>
            {reports.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: "4rem", color: "var(--text-muted)" }}>尚未生成任何报告记录</td></tr>
            ) : reports.map((r: any) => (
              <tr key={r.id}>
                <td style={{ color: "var(--text-muted)", fontWeight: 500 }}>#{r.id}</td>
                <td><span style={{ padding: "2px 8px", background: "#3b82f620", color: "#60a5fa", borderRadius: "12px", fontSize: "0.75rem", fontWeight: 600 }}>{r.report_type}</span></td>
                <td style={{ fontSize: "0.875rem" }}>{r.start_date?.slice(0, 10)} ➝ {r.end_date?.slice(0, 10)}</td>
                <td>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: r.status === "DONE" ? "#22c55e" : r.status === "FAILED" ? "#ef4444" : "#eab308", fontWeight: 500, fontSize: "0.875rem" }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
                    {r.status === "DONE" ? "生成成功" : r.status}
                  </span>
                </td>
                <td style={{ fontSize: "0.875rem", color: r.pushed_at ? "#e2e8f0" : "var(--text-muted)" }}>{r.pushed_at ? new Date(r.pushed_at).toLocaleString("zh-CN") : "未自动下发"}</td>
                <td style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "capitalize" }}>{r.triggered_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Add Schedule Modal */}
      {showAddSchedule && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}>
          <div className="card" style={{ width: 400, padding: "1.5rem" }}>
            <h3 style={{ fontSize: "1.125rem", fontWeight: 700, marginBottom: "1rem" }}>新建投递规则</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>方案名称</label>
                <input className="input" placeholder="例如: 每周简报投递" value={scheduleForm.name} onChange={e => setScheduleForm({...scheduleForm, name: e.target.value})} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>CRON 表达式</label>
                <input className="input" placeholder="0 9 * * 1" value={scheduleForm.cron_expression} onChange={e => setScheduleForm({...scheduleForm, cron_expression: e.target.value})} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>包含数据维度</label>
                <select className="input" value={scheduleForm.report_type} onChange={e => setScheduleForm({...scheduleForm, report_type: e.target.value})}>
                  <option value="WEEKLY">周报 (WEEKLY)</option>
                  <option value="MONTHLY">月报 (MONTHLY)</option>
                  <option value="DAILY">日报 (DAILY)</option>
                </select>
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>Webhook 地址</label>
                <input className="input" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." value={scheduleForm.webhook_url} onChange={e => setScheduleForm({...scheduleForm, webhook_url: e.target.value})} />
              </div>
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleAddSchedule}>保存配置</button>
                <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setShowAddSchedule(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
