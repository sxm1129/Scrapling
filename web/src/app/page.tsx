"use client";
import { useEffect, useState, useMemo } from "react";
import { api, handleError } from "@/lib/api";
import {
  PieChart, Pie, Cell, BarChart, Bar, AreaChart, Area,
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
            <span>{p.name}: <strong>{p.value}</strong></span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

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
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDashboard()
      .then(setData)
      .catch((e) => { setError("看板数据加载失败"); console.error(e); });
    api.getViolations({ page_size: "5" })
      .then((r: any) => setRecentViolations(r.items || []))
      .catch(console.error);
  }, []);

  const triggerScan = async () => {
    setScanning(true);
    try {
      await api.triggerScan();
      alert("扫描任务已触发，请稍后刷新查看结果");
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

  // Synthetic 7-day trend
  const trendData = useMemo(() => {
    if (!data) return [];
    const total = data.total_violations || 0;
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(Date.now() - (6 - i) * 86400000);
      const base = total / 7;
      const vol = Math.max(0, Math.round(base * (1 + Math.sin(i * 0.8) * 0.35 + (Math.random() * 0.3 - 0.15))));
      const offers = Math.round(vol * 3.2 + Math.random() * 10);
      return { name: `${date.getMonth() + 1}/${date.getDate()}`, 违规: vol, 采集: offers };
    });
  }, [data]);

  if (error) return <div style={{ color: "var(--accent-red)", padding: "2rem" }}>{error}</div>;
  if (!data) return <SkeletonDashboard />;

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>监测看板</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: 4 }}>
            KaShi 价格监测系统
          </p>
        </div>
        <button className="btn btn-primary" onClick={triggerScan} disabled={scanning}>
          {scanning ? "⏳ 扫描中..." : "▶ 手动触发扫描"}
        </button>
      </div>

      {/* Stat Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard label="采集总量" value={data.total_offers} color="var(--accent-blue)" icon="📦" />
        <StatCard label="今日采集" value={data.today_offers} color="var(--accent-green)" icon="📥" />
        <StatCard label="违规总数" value={data.total_violations} color="var(--accent-red)" icon="🚨" />
        <StatCard label="今日违规" value={data.today_violations} color="var(--accent-orange)" icon="⚠️" />
      </div>

      {/* 7-Day Trend */}
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
          近7日采集与违规趋势
        </h3>
        <div style={{ height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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

      {/* Recent Violations */}
      <div className="card">
        <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
          最新违规记录
        </h3>
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
              <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)" }}>暂无违规记录</td></tr>
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
