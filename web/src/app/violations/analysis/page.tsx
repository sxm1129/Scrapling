"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购",
};

export default function ViolationAnalysisPage() {
  const [kpis, setKpis] = useState<any>(null);
  const [trends, setTrends] = useState<any[]>([]);
  const [topViolators, setTopViolators] = useState<any[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - days * 86400000).toISOString();
    Promise.all([
      api.getKPIs({ start, end }),
      api.getTrends({ metric: "violations", days: String(days) }),
      api.getTopViolators({ limit: "10" }),
    ]).then(([k, t, tv]) => {
      setKpis(k);
      setTrends(t.data || []);
      setTopViolators(tv.violators || []);
    }).catch(e => handleError(e, "加载分析数据")).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [days]);

  const maxTrendVal = Math.max(...trends.map(d => d.value), 1);
  const maxViolatorCount = Math.max(...topViolators.map(d => d.violation_count), 1);

  return (
    <div className="animate-in">
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>低价违规分析</h1>
        <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
          {[7, 30, 90].map(d => (
            <button key={d} className={`btn ${days === d ? "btn-primary" : ""}`} onClick={() => setDays(d)}>{d}天</button>
          ))}
        </div>
      </div>

      {loading ? <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>加载中...</div> : kpis && (
        <>
          {/* KPI Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
            {[
              { label: "违规总数", value: kpis.kpi1_violations_total, color: "#ef4444" },
              { label: "违规率", value: (kpis.kpi2_violation_rate * 100).toFixed(1) + "%", color: "#f97316" },
              { label: "工单闭环率", value: (kpis.kpi3_workorder_close_rate * 100).toFixed(1) + "%", color: "#22c55e" },
              { label: "平均价差", value: kpis.kpi6_avg_gap_percent ? kpis.kpi6_avg_gap_percent.toFixed(1) + "%" : "N/A", color: "#a855f7" },
              { label: "白名单命中率", value: (kpis.kpi7_whitelist_hit_rate * 100).toFixed(1) + "%", color: "#0ea5e9" },
              { label: "复发率", value: (kpis.kpi8_reoccur_rate * 100).toFixed(1) + "%", color: "#f43f5e" },
            ].map(({ label, value, color }) => (
              <div key={label} className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
                <div style={{ fontSize: "2rem", fontWeight: 800, color }}>{value}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
            {/* Trend Chart */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>每日违规趋势</h2>
              {trends.length === 0 ? (
                <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无数据</div>
              ) : (
                <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", height: 140 }}>
                  {trends.map((d: any) => (
                    <div key={d.day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}
                      title={`${d.day}: ${d.value}条`}>
                      <div style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>{d.value}</div>
                      <div style={{
                        width: "100%", height: `${Math.round((d.value / maxTrendVal) * 100)}px`,
                        minHeight: 2, background: "linear-gradient(to top, #6366f1, #a5b4fc)", borderRadius: "2px 2px 0 0"
                      }} />
                      <div style={{ fontSize: "0.55rem", color: "var(--text-muted)", transform: "rotate(-45deg)", transformOrigin: "center" }}>{d.day.slice(5)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Platform Breakdown */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>各平台违规分布</h2>
              {Object.entries(kpis.kpi1_violations_by_platform || {}).length === 0 ? (
                <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无数据</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {Object.entries(kpis.kpi1_violations_by_platform as Record<string, number>)
                    .sort(([, a], [, b]) => b - a)
                    .map(([platform, count]) => {
                      const total = kpis.kpi1_violations_total || 1;
                      return (
                        <div key={platform}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: 2 }}>
                            <span>{PLATFORM_LABELS[platform] || platform}</span>
                            <span style={{ color: "var(--text-muted)" }}>{count} ({(count / total * 100).toFixed(0)}%)</span>
                          </div>
                          <div style={{ height: 8, background: "var(--bg)", borderRadius: 4, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${count / total * 100}%`, background: "linear-gradient(to right, #6366f1, #a5b4fc)", borderRadius: 4 }} />
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>

            {/* Severity Distribution */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>严重度分布</h2>
              <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
                {Object.entries(kpis.severity_distribution || {}).map(([sev, cnt]: [string, any]) => (
                  <div key={sev} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: "2.5rem", fontWeight: 800, color: sev === "P0" ? "#ef4444" : sev === "P1" ? "#f97316" : "#eab308" }}>{cnt}</div>
                    <div className="badge" style={{ background: (sev === "P0" ? "#ef444422" : sev === "P1" ? "#f9731622" : "#eab30822"), color: (sev === "P0" ? "#ef4444" : sev === "P1" ? "#f97316" : "#eab308") }}>{sev}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Violators */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>TOP 10 违规商家</h2>
              {topViolators.length === 0 ? (
                <div style={{ textAlign: "center", color: "var(--text-muted)" }}>暂无数据</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {topViolators.map((v: any, i: number) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem" }}>
                      <span style={{ color: i < 3 ? "#ef4444" : "var(--text-muted)", fontWeight: 700, minWidth: 20 }}>#{i + 1}</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.shop_name}</span>
                      <span style={{ color: "var(--text-muted)" }}>{PLATFORM_LABELS[v.platform] || v.platform}</span>
                      <div style={{ width: 60, height: 6, background: "var(--bg)", borderRadius: 3 }}>
                        <div style={{ width: `${v.violation_count / maxViolatorCount * 100}%`, height: "100%", background: "#ef4444", borderRadius: 3 }} />
                      </div>
                      <span style={{ fontWeight: 700, color: "#ef4444", minWidth: 24, textAlign: "right" }}>{v.violation_count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
