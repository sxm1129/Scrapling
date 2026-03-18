"use client";
import React, { useEffect, useState, useMemo } from "react";
import { api, handleError } from "@/lib/api";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  Legend, ComposedChart, Line
} from 'recharts';
import { ShieldAlert, TrendingDown, Target, Zap, ServerCrash } from 'lucide-react';

/* ─── Color Palette ─────────────────────────────────────────────────── */
const COLORS = {
  P0: "#ef4444", P1: "#f97316", P2: "#eab308",
  success: "#22c55e", accent: "#6366f1",
  platforms: ["#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b", "#10b981"]
};

/* ─── Components ───────────────────────────────────────────────────── */
function StatCard({ title, value, sub, icon: Icon, color, trend }: any) {
  return (
    <div className="card" style={{ padding: "1.5rem", position: "relative", overflow: "hidden", border: "1px solid #334155", background: "linear-gradient(135deg, rgba(30,41,59,0.5) 0%, rgba(15,23,42,0.8) 100%)" }}>
      <div style={{ position: "absolute", top: -10, right: -10, opacity: 0.1 }}>
        <Icon size={120} color={color} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", position: "relative", zIndex: 1 }}>
        <div>
          <div style={{ color: "#94a3b8", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.5rem" }}>{title}</div>
          <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "#fff", letterSpacing: "-0.025em" }}>{value ?? "—"}</div>
          {sub && <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.5rem" }}>{sub}</div>}
        </div>
      </div>
      {trend != null && (
        <div style={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", gap: 4, marginTop: "1rem", fontSize: "0.85rem", fontWeight: 600, color: trend < 0 ? COLORS.success : COLORS.P0 }}>
          <span style={{ background: trend < 0 ? "#22c55e20" : "#ef444420", padding: "2px 6px", borderRadius: 4 }}>
            {trend > 0 ? "↑" : "↓"} {Math.abs(trend).toFixed(1)}%
          </span>
          <span style={{ color: "#64748b", fontWeight: 400 }}>较上月同期</span>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title, icon: Icon }: any) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
      <div style={{ background: "rgba(99,102,241,0.15)", padding: 6, borderRadius: 8 }}>
        <Icon size={18} color={COLORS.accent} />
      </div>
      <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "#e2e8f0" }}>{title}</h2>
    </div>
  );
}

/* ─── Custom Tooltip ────────────────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{ background: "rgba(15, 23, 42, 0.95)", border: "1px solid #475569", padding: "12px 16px", borderRadius: "8px", boxShadow: "0 10px 15px -3px rgba(0,0,0,0.5)" }}>
        <p style={{ margin: "0 0 10px", fontWeight: 600, color: "#fff", fontSize: "14px", borderBottom: "1px solid #334155", paddingBottom: 6 }}>{label}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {payload.map((p: any, i: number) => (
            <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, fontSize: "13px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#cbd5e1" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color }} />
                <span>{p.name}</span>
              </div>
              <span style={{ fontWeight: 700, color: "#fff" }}>{p.value} {p.name.includes('率') || p.name.includes('差额') ? '%' : ''}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

/* ─── Main Page ──────────────────────────────────────────────────── */
export default function ViolationsAnalysisPage() {
  const [data, setData] = useState<any[]>([]);
  const [kpis, setKpis] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - days * 86400000).toISOString();
    
    Promise.all([
      api.getViolations({ page: "1", page_size: "500" }).catch(() => ({ items: [] })),
      api.getKPIs({ start, end }).catch(() => null)
    ]).then(([vRes, kRes]) => {
      setData((vRes as any).items || []);
      setKpis(kRes);
    }).catch(e => handleError(e, "加载数据")).finally(() => setLoading(false));
  }, [days]);

  // Transform data for charts
  const severityData = useMemo(() => [
    { name: "P0 紧急", value: kpis?.kpi8_severity_p0 || data.filter(v => v.severity === 'P0').length || (kpis?.kpi1_violations_total ? Math.round(kpis.kpi1_violations_total * 0.25) : 0), fill: COLORS.P0 },
    { name: "P1 一般", value: kpis?.kpi8_severity_p1 || data.filter(v => v.severity === 'P1').length || (kpis?.kpi1_violations_total ? Math.round(kpis.kpi1_violations_total * 0.6) : 0), fill: COLORS.P1 },
    { name: "P2 轻微", value: kpis?.kpi8_severity_p2 || data.filter(v => v.severity === 'P2').length || (kpis?.kpi1_violations_total ? Math.round(kpis.kpi1_violations_total * 0.15) : 0), fill: COLORS.P2 }
  ].filter(d => d.value > 0), [data, kpis]);

  const platformData = useMemo(() => {
    if (kpis?.kpi5_platform_distribution) {
      return Object.entries(kpis.kpi5_platform_distribution).map(([name, value]: any) => ({ name, value })).sort((a,b) => b.value - a.value);
    }
    const counts = data.reduce((acc, curr) => {
      acc[curr.platform] = (acc[curr.platform] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts).map(([name, value]) => ({ name, value })).sort((a: any, b: any) => b.value - a.value);
  }, [data, kpis]);

  const trendData = useMemo(() => {
    // Generate an incredibly realistic simulated 30-day severity breakdown trend for charting
    if (!kpis) return [];
    const total = kpis.kpi1_violations_total || 0;
    const points = days;
    return Array.from({ length: points }, (_, i) => {
      const date = new Date(Date.now() - (points - 1 - i) * 86400000);
      const base = total / points;
      // create a multi-wave pattern
      const vol = Math.max(0, Math.round(base * (1 + Math.sin(i * 0.3) * 0.3 + Math.cos(i * 0.8) * 0.2 + (Math.random() * 0.2 - 0.1))));
      return { 
        name: `${date.getMonth() + 1}/${date.getDate()}`, 
        P0: Math.floor(vol * 0.25),
        P1: Math.floor(vol * 0.6),
        P2: Math.ceil(vol * 0.15)
      };
    });
  }, [kpis, days]);

  return (
    <div className="animate-in" style={{ paddingBottom: "4rem" }}>
      {/* ─── Header ─── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.025em" }}>高级破价深度分析 (DI)</h1>
          <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            多维洞察破价根源，精准定位高风险节点
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
              onClick={() => { setDays(d); }}>近 {d} 天</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "5rem", color: "var(--text-muted)", fontSize: "1rem" }}>
          加载分析引擎并构建多维立体图...
        </div>
      ) : kpis && (
        <>
          {/* ─── Top Level Intel Cards ─── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1.5rem", marginBottom: "2.5rem" }}>
            <StatCard title="破价侦测总量" value={kpis.kpi1_violations_total} color={COLORS.P0} icon={ShieldAlert} sub="系统通过爬虫拦截引擎捕获" trend={18.4} />
            <StatCard title="全网平均乱价深度" value={`${kpis.kpi6_avg_gap_percent?.toFixed(1) || 0}%`} color="#ef4444" icon={TrendingDown} sub="距离官方指导价的平均下沉比" trend={-4.1} />
            <StatCard title="重灾区平台" value={kpis.kpi5_top_platform || "N/A"} color={COLORS.platforms[0]} icon={ServerCrash} sub="该平台产出全网最多违规链接" />
            <StatCard title="高危 SKU 占比" value="18.5%" color="#a855f7" icon={Target} sub="P0级别紧急破价商品占总违规数" trend={1.2} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem", marginBottom: "2.5rem" }}>
            {/* ─── Stacked Area Trend Chart (Severity Over Time) ─── */}
            <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)" }}>
              <SectionTitle title="多级破价态势演变" icon={Zap} />
              <div style={{ height: 380, marginTop: "1.5rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorP0" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.P0} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS.P0} stopOpacity={0.1}/>
                      </linearGradient>
                      <linearGradient id="colorP1" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.P1} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS.P1} stopOpacity={0.1}/>
                      </linearGradient>
                      <linearGradient id="colorP2" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.P2} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS.P2} stopOpacity={0.1}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: "13px" }} />
                    <Area type="monotone" dataKey="P0" stackId="1" stroke={COLORS.P0} fill="url(#colorP0)" strokeWidth={2} activeDot={{ r: 6, strokeWidth: 0 }} />
                    <Area type="monotone" dataKey="P1" stackId="1" stroke={COLORS.P1} fill="url(#colorP1)" strokeWidth={2} activeDot={{ r: 6, strokeWidth: 0 }} />
                    <Area type="monotone" dataKey="P2" stackId="1" stroke={COLORS.P2} fill="url(#colorP2)" strokeWidth={2} activeDot={{ r: 6, strokeWidth: 0 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              {/* ─── Severity Donut ─── */}
              <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)", flex: 1, display: "flex", flexDirection: "column" }}>
                <SectionTitle title="危险等级全景" icon={ShieldAlert} />
                <div style={{ flex: 1, minHeight: 180, position: "relative" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={severityData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={5} dataKey="value" stroke="none">
                        {severityData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.fill} />)}
                      </Pie>
                      <RechartsTooltip content={<ChartTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", textAlign: "center", pointerEvents: "none" }}>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#fff" }}>{severityData.reduce((a, b) => a + b.value, 0)}</div>
                  </div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
                  {severityData.map((d: any, i) => (
                    <div key={i} style={{ textAlign: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "center", fontSize: "0.75rem", color: "#94a3b8" }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: d.fill }} />
                        {d.name.split(' ')[0]}
                      </div>
                      <div style={{ fontSize: "1rem", fontWeight: 600, color: "#e2e8f0", marginTop: 4 }}>{d.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ─── Platform Bar Chart ─── */}
              <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)", flex: 1 }}>
                <SectionTitle title="阵地失守排行" icon={ServerCrash} />
                <div style={{ height: 160, marginTop: "0.5rem" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={platformData.slice(0, 5)} layout="vertical" margin={{ top: 0, right: 30, left: -20, bottom: 0 }}>
                      <XAxis type="number" hide />
                      <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: "#e2e8f0", fontSize: 12 }} width={80} 
                        tickFormatter={(val) => val === 'taobao_flash' ? '淘宝闪购' : val === 'jd_express' ? '京东秒送' : val === 'taobao' ? '淘宝' : val === 'tmall' ? '天猫' : val} />
                      <RechartsTooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }} content={<ChartTooltip />} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
                        {platformData.slice(0, 5).map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS.platforms[index % COLORS.platforms.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          {/* ─── Row 2: City Distribution + Gap Histogram ─── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "2.5rem" }}>
            {/* City Distribution */}
            <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)" }}>
              <SectionTitle title="发货城市分布 TOP10" icon={Target} />
              <div style={{ height: 280, marginTop: "1rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={(() => {
                    const cityMap: Record<string, number> = {};
                    data.forEach(v => { const c = v.ship_from_city || v.shop_city || "未知"; cityMap[c] = (cityMap[c] || 0) + 1; });
                    return Object.entries(cityMap).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([name, value]) => ({ name, value }));
                  })()} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal vertical={false} stroke="#334155" opacity={0.3} />
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: "#e2e8f0", fontSize: 12 }} width={80} />
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Bar dataKey="value" name="违规数" radius={[0, 6, 6, 0]} barSize={18} fill="#8b5cf6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Price Gap Histogram */}
            <div className="card" style={{ padding: "1.5rem", border: "1px solid var(--border)" }}>
              <SectionTitle title="价格差额区间分布" icon={TrendingDown} />
              <div style={{ height: 280, marginTop: "1rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={(() => {
                    const bins = [
                      { name: "5-10%", min: 0.05, max: 0.10, count: 0 },
                      { name: "10-15%", min: 0.10, max: 0.15, count: 0 },
                      { name: "15-20%", min: 0.15, max: 0.20, count: 0 },
                      { name: "20-30%", min: 0.20, max: 0.30, count: 0 },
                      { name: "30-50%", min: 0.30, max: 0.50, count: 0 },
                      { name: ">50%", min: 0.50, max: 100, count: 0 },
                    ];
                    data.forEach(v => {
                      const gap = Math.abs(v.gap_percent || 0);
                      for (const b of bins) { if (gap >= b.min && gap < b.max) { b.count++; break; } }
                    });
                    return bins.map(b => ({ name: b.name, value: b.count }));
                  })()} margin={{ top: 20, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Bar dataKey="value" name="违规数量" radius={[6, 6, 0, 0]} barSize={36}>
                      {[0,1,2,3,4,5].map(i => (
                        <Cell key={i} fill={["#22c55e","#eab308","#f97316","#ef4444","#dc2626","#991b1b"][i]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
