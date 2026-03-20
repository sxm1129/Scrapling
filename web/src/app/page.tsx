"use client";
import { useEffect, useState, useMemo, useRef } from "react";
import { api, handleError } from "@/lib/api";
import {
  PieChart, Pie, Cell, BarChart, Bar, AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, Legend
} from "recharts";

interface DashboardData {
  total_offers: number;
  today_offers: number;
  total_violations: number;
  today_violations: number;
  platform_distribution: Record<string, number>;
  severity_distribution: Record<string, number>;
  latest_p0_alerts?: Array<{
    id: number;
    product_name: string;
    platform: string;
    final_price: number;
    baseline_price: number;
    shop_name: string;
    gap_percent: number;
    created_at: string;
  }>;
}

interface TrendPoint {
  date: string;
  avg_price: number;
  min_price: number;
  max_price: number;
  offer_count: number;
}

interface HealthPlatform {
  platform: string;
  total: number;
  success: number;
  failed: number;
  success_rate: number;
  fail_reasons: Record<string, number>;
}

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

const PLATFORM_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b", "#10b981", "#ef4444", "#06b6d4"];
const SEVERITY_COLORS: Record<string, string> = { P0: "#ef4444", P1: "#f97316", P2: "#eab308" };

/* ─── Chart Tooltip ─── */
const ChartTooltip = ({ active, payload, label }: any) => {
  if (active && payload?.length) {
    return (
      <div style={{ background: "rgba(15,23,42,0.95)", border: "1px solid #334155", padding: "10px 14px", borderRadius: 8, boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
        {label && <p style={{ margin: "0 0 6px", fontWeight: 600, color: "#fff", fontSize: "0.8rem" }}>{label}</p>}
        {payload.map((p: any, i: number) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8rem", color: "#e2e8f0", marginBottom: 2 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color || p.payload?.color }} />
            <span>{p.name}: <strong>{typeof p.value === 'number' && p.value < 1000 && p.name?.includes('价') ? `¥${p.value}` : p.value}</strong></span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

/* ─── P0 Alert Ticker ─── */
function P0AlertTicker({ alerts }: { alerts: NonNullable<DashboardData["latest_p0_alerts"]> }) {
  const [idx, setIdx] = useState(0);
  const timerRef = useRef<any>(null);

  useEffect(() => {
    if (alerts.length <= 1) return;
    timerRef.current = setInterval(() => setIdx(i => (i + 1) % alerts.length), 4000);
    return () => clearInterval(timerRef.current);
  }, [alerts.length]);

  if (alerts.length === 0) return null;
  const alert = alerts[idx];

  return (
    <div style={{
      background: "linear-gradient(90deg, rgba(239,68,68,0.15) 0%, rgba(239,68,68,0.05) 100%)",
      border: "1px solid rgba(239,68,68,0.4)",
      borderRadius: 10,
      padding: "10px 16px",
      marginBottom: "1.25rem",
      display: "flex",
      alignItems: "center",
      gap: 12,
      animation: "fadeIn 0.3s ease",
    }}>
      <span style={{ fontSize: "1.1rem", flexShrink: 0 }}>🚨</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
          <span style={{ background: "#ef4444", color: "#fff", fontSize: "0.65rem", fontWeight: 700, padding: "1px 6px", borderRadius: 4 }}>P0</span>
          <span style={{ color: "#fca5a5", fontSize: "0.8rem", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {alert.product_name?.slice(0, 50)}
          </span>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: "0.75rem", color: "#94a3b8" }}>
          <span>{PLATFORM_LABELS[alert.platform] || alert.platform}</span>
          <span style={{ color: "#f87171" }}>¥{alert.final_price} <span style={{ color: "#475569" }}>(基准 ¥{alert.baseline_price})</span></span>
          <span>店铺: {alert.shop_name || "未知"}</span>
          <span>差额: {(alert.gap_percent * 100).toFixed(1)}%</span>
        </div>
      </div>
      {alerts.length > 1 && (
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {alerts.map((_, i) => (
            <div key={i} onClick={() => setIdx(i)} style={{
              width: 6, height: 6, borderRadius: "50%", cursor: "pointer",
              background: i === idx ? "#ef4444" : "rgba(239,68,68,0.3)",
              transition: "background 0.2s",
            }} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Collection Health Panel ─── */
function HealthPanel({ platforms }: { platforms: HealthPlatform[] }) {
  if (platforms.length === 0) return null;
  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
        采集健康度 (近24h)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
        {platforms.map(p => {
          const rate = (p.success_rate * 100).toFixed(0);
          const color = p.success_rate >= 0.8 ? "#10b981" : p.success_rate >= 0.5 ? "#f59e0b" : "#ef4444";
          return (
            <div key={p.platform} style={{ background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: "10px 12px", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 6 }}>
                {PLATFORM_LABELS[p.platform] || p.platform}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ flex: 1, height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${rate}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.6s ease" }} />
                </div>
                <span style={{ fontSize: "0.75rem", fontWeight: 600, color, minWidth: 32, textAlign: "right" }}>{rate}%</span>
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 4 }}>
                {p.success}/{p.total} 成功
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Skeleton ─── */
function Skeleton({ width = "100%", height = 20 }: { width?: string | number; height?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 8 }} />;
}

function SkeletonDashboard() {
  return (
    <div className="animate-in">
      <div style={{ marginBottom: "1.5rem" }}><Skeleton width={200} height={28} /></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="stat-card" style={{ padding: "1.25rem" }}>
            <Skeleton width={80} height={14} />
            <div style={{ marginTop: 12 }}><Skeleton width={60} height={32} /></div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        <div className="card"><Skeleton height={250} /></div>
        <div className="card"><Skeleton height={250} /></div>
      </div>
      <div className="card"><Skeleton height={200} /></div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [recentViolations, setRecentViolations] = useState<any[]>([]);
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [healthData, setHealthData] = useState<HealthPlatform[]>([]);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const loadAll = () => {
    api.getDashboard()
      .then(setData)
      .catch((e) => { setError("看板数据加载失败"); console.error(e); });
    api.getViolations({ page_size: "5", severity: "P0" })
      .then((r: any) => setRecentViolations(r.items || []))
      .catch(console.error);
    // 真实趋势数据
    fetch("/api/offers/trend?days=7")
      .then(r => r.json())
      .then((r: any) => setTrendData(r.trend || []))
      .catch(console.error);
    // 采集健康度
    fetch("/api/collection/health-stats?hours=24")
      .then(r => r.json())
      .then((r: any) => setHealthData(r.platforms || []))
      .catch(console.error);
    setLastRefresh(new Date());
  };

  useEffect(() => {
    loadAll();
    // 30秒自动刷新
    const timer = setInterval(loadAll, 30_000);
    return () => clearInterval(timer);
  }, []);

  const triggerScan = async () => {
    setScanning(true);
    try {
      await api.triggerScan();
      setTimeout(loadAll, 2000); // 2秒后刷新数据
    } catch (e) { handleError(e, "触发扫描"); }
    setTimeout(() => setScanning(false), 3000);
  };

  // Pie chart data
  const platformPieData = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.platform_distribution)
      .map(([key, value]) => ({ name: PLATFORM_LABELS[key] || key, value }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  // Bar chart data
  const severityBarData = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.severity_distribution)
      .map(([key, value]) => ({ name: key, value, color: SEVERITY_COLORS[key] || "#6366f1" }));
  }, [data]);

  // Real trend data (from API) — split for type safety
  const isRealTrend = trendData.length > 0;

  const realChartData = useMemo(() =>
    trendData.map(d => ({
      name: d.date.slice(5),
      "均价": d.avg_price,
      "最低价": d.min_price,
      "采集量": d.offer_count,
    })),
  [trendData]);

  const syntheticChartData = useMemo(() => {
    if (!data) return [];
    const total = data.total_violations || 0;
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(Date.now() - (6 - i) * 86400000);
      const base = total / 7;
      const vol = Math.max(0, Math.round(base * (1 + Math.sin(i * 0.8) * 0.35)));
      const offers = Math.round(vol * 3.2);
      return { name: `${date.getMonth() + 1}/${date.getDate()}`, "违规": vol, "采集": offers };
    });
  }, [data]);

  if (error) return <div style={{ color: "var(--accent-red)", padding: "2rem" }}>{error}</div>;
  if (!data) return <SkeletonDashboard />;

  const p0Alerts = data.latest_p0_alerts || [];

  return (
    <div className="animate-in">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>监测看板</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: 4 }}>
            上次刷新: {lastRefresh.toLocaleTimeString("zh-CN")} · 每30秒自动刷新
          </p>
        </div>
        <button className="btn btn-primary" onClick={triggerScan} disabled={scanning}>
          {scanning ? "⏳ 扫描中..." : "▶ 手动触发扫描"}
        </button>
      </div>

      {/* P0 Alert Ticker */}
      {p0Alerts.length > 0 && <P0AlertTicker alerts={p0Alerts} />}

      {/* Stat Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard label="采集总量" value={data.total_offers} color="var(--accent-blue)" icon="📦" />
        <StatCard label="今日采集" value={data.today_offers} color="var(--accent-green)" icon="📥" />
        <StatCard label="违规总数" value={data.total_violations} color="var(--accent-red)" icon="🚨" />
        <StatCard label="今日违规" value={data.today_violations} color="var(--accent-orange)" icon="⚠️" />
      </div>

      {/* Collection Health Panel (A5) */}
      <HealthPanel platforms={healthData} />

      {/* Price Trend Chart (Real API Data — A1) */}
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
          近7日价格趋势 {trendData.length > 0 ? "(真实采集数据)" : "(模拟数据)"}
        </h3>
        <div style={{ height: 280 }}>
          {isRealTrend ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={realChartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <RechartsTooltip content={<ChartTooltip />} />
                <Legend verticalAlign="top" height={36} iconType="circle" />
                <Line type="monotone" dataKey="均价" stroke="#3b82f6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="最低价" stroke="#f59e0b" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={syntheticChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorOffers" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="colorViolations" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <RechartsTooltip content={<ChartTooltip />} />
                <Legend verticalAlign="top" height={36} iconType="circle" />
                <Area type="monotone" dataKey="采集" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorOffers)" />
                <Area type="monotone" dataKey="违规" stroke="#ef4444" strokeWidth={2} fillOpacity={1} fill="url(#colorViolations)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        {/* Platform Distribution Pie */}
        <div className="card">
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
            平台违规分布
          </h3>
          {platformPieData.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", padding: "2rem" }}>暂无数据</p>
          ) : (
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformPieData}
                    cx="50%" cy="50%"
                    innerRadius={60} outerRadius={95}
                    paddingAngle={3}
                    dataKey="value"
                    stroke="none"
                  >
                    {platformPieData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={PLATFORM_COLORS[index % PLATFORM_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<ChartTooltip />} />
                  <Legend verticalAlign="bottom" height={50} iconType="circle"
                    formatter={(value) => <span style={{ color: "#cbd5e1", fontSize: "0.75rem" }}>{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Severity Distribution Bar */}
        <div className="card">
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
            违规严重度分布
          </h3>
          {severityBarData.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", padding: "2rem" }}>暂无数据</p>
          ) : (
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={severityBarData} margin={{ top: 20, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 13 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                  <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                  <Bar dataKey="value" name="违规数" radius={[6, 6, 0, 0]} barSize={48}>
                    {severityBarData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Recent P0 Violations */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
            最新 P0 违规记录
          </h3>
          <a href="/violations" style={{ fontSize: "0.75rem", color: "var(--accent-blue)", textDecoration: "none" }}>
            查看全部 →
          </a>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>严重度</th>
              <th>平台</th>
              <th>商品</th>
              <th>到手价</th>
              <th>基准价</th>
              <th>差额</th>
              <th>店铺</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {recentViolations.map((v: any) => (
              <tr key={v.id}>
                <td><span className={`badge badge-${v.severity.toLowerCase()}`}>{v.severity}</span></td>
                <td>{PLATFORM_LABELS[v.platform] || v.platform}</td>
                <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {v.product_name}
                </td>
                <td style={{ color: "var(--accent-red)", fontWeight: 600 }}>¥{v.final_price}</td>
                <td>¥{v.baseline_price}</td>
                <td style={{ color: "var(--accent-orange)" }}>-{(v.gap_percent * 100).toFixed(1)}%</td>
                <td style={{ color: "var(--text-muted)" }}>{v.shop_name || "-"}</td>
                <td style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  {v.created_at ? new Date(v.created_at).toLocaleString("zh-CN") : "-"}
                </td>
              </tr>
            ))}
            {recentViolations.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)" }}>暂无 P0 违规记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value, color, icon }: { label: string; value: number; color: string; icon: string }) {
  return (
    <div className="stat-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4 }}>{label}</p>
          <p className="number" style={{ color }}>{value.toLocaleString()}</p>
        </div>
        <span style={{ fontSize: "1.5rem", opacity: 0.6 }}>{icon}</span>
      </div>
    </div>
  );
}
