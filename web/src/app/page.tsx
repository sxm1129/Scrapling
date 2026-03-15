"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

interface DashboardData {
  total_offers: number;
  today_offers: number;
  total_violations: number;
  today_violations: number;
  platform_distribution: Record<string, number>;
  severity_distribution: Record<string, number>;
}

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd: "京东",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
};

const PLATFORM_COLORS: Record<string, string> = {
  taobao: "#ff6600", tmall: "#e4393c", jd: "#e1251b",
  pinduoduo: "#e02e24", taobao_flash: "#ff4081",
};

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

  if (error) return <div style={{ color: "var(--accent-red)", padding: "2rem" }}>{error}</div>;

  if (!data) return <div style={{ color: "var(--text-muted)", padding: "2rem" }}>加载中...</div>;

  const platformTotal = Object.values(data.platform_distribution).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>监测看板</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: 4 }}>
            Antigravity 价格监测系统
          </p>
        </div>
        <button className="btn btn-primary" onClick={triggerScan} disabled={scanning}>
          {scanning ? "⏳ 扫描中..." : "▶ 手动触发扫描"}
        </button>
      </div>

      {/* Stat Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard label="采集总量" value={data.total_offers} color="var(--accent-blue)" />
        <StatCard label="今日采集" value={data.today_offers} color="var(--accent-green)" />
        <StatCard label="违规总数" value={data.total_violations} color="var(--accent-red)" />
        <StatCard label="今日违规" value={data.today_violations} color="var(--accent-orange)" />
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        {/* Platform Distribution */}
        <div className="card">
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
            平台违规分布
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {Object.entries(data.platform_distribution).map(([platform, count]) => (
              <div key={platform}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: "0.875rem" }}>
                  <span>{PLATFORM_LABELS[platform] || platform}</span>
                  <span style={{ color: "var(--text-muted)" }}>{count} 条</span>
                </div>
                <div style={{ height: 8, background: "var(--bg-secondary)", borderRadius: 4 }}>
                  <div style={{
                    height: "100%",
                    width: `${(count / platformTotal) * 100}%`,
                    background: PLATFORM_COLORS[platform] || "var(--accent-blue)",
                    borderRadius: 4,
                    transition: "width 0.5s ease",
                  }} />
                </div>
              </div>
            ))}
            {Object.keys(data.platform_distribution).length === 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>暂无数据</p>
            )}
          </div>
        </div>

        {/* Severity Distribution */}
        <div className="card">
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
            违规严重度分布
          </h3>
          <div style={{ display: "flex", gap: "2rem", alignItems: "center", justifyContent: "center", height: "80%" }}>
            {Object.entries(data.severity_distribution).map(([sev, count]) => (
              <div key={sev} style={{ textAlign: "center" }}>
                <div style={{
                  fontSize: "2.5rem", fontWeight: 700,
                  color: sev === "P0" ? "var(--accent-red)" : sev === "P1" ? "var(--accent-orange)" : "var(--accent-blue)",
                }}>
                  {count}
                </div>
                <div className={`badge badge-${sev.toLowerCase()}`} style={{ marginTop: 8 }}>{sev}</div>
              </div>
            ))}
            {Object.keys(data.severity_distribution).length === 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>暂无数据</p>
            )}
          </div>
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

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="stat-card">
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4 }}>{label}</p>
      <p className="number" style={{ color }}>{value.toLocaleString()}</p>
    </div>
  );
}
