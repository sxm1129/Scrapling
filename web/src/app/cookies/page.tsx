"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, handleError } from "@/lib/api";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip } from "recharts";

const STATUS_COLORS: Record<string, string> = {
  active: "#4caf50",
  cooldown: "#ff9800",
  invalid: "#f44336",
  unknown: "#9e9e9e",
};

const HEALTH_RING_COLORS = ["#22c55e", "#f97316", "#ef4444", "#64748b"];

export default function CookiesPage() {
  const [platforms, setPlatforms] = useState<any[]>([]);
  const [validating, setValidating] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<Record<string, any>>({});
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const load = useCallback(() => {
    api.getCookieStatus().then((r: any) => {
      setPlatforms(r.platforms || []);
      setLastRefresh(new Date());
    }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 30000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, load]);

  const handleValidate = async (platform: string) => {
    setValidating(platform);
    try {
      const result = await api.validateCookie(platform);
      setValidationResults(prev => ({ ...prev, [platform]: result }));
      load();
    } catch (e) { handleError(e, "验证 Cookie"); }
    setValidating(null);
  };

  const handleValidateAll = async () => {
    setValidating("__all__");
    try {
      const result = await api.validateAllCookies();
      const map: Record<string, any> = {};
      (result.results || []).forEach((r: any) => { map[r.platform] = r; });
      setValidationResults(prev => ({ ...prev, ...map }));
      load();
    } catch (e) { handleError(e, "批量验证"); }
    setValidating(null);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const r = await api.syncCookies();
      alert(`同步完成: ${r.synced} 个账号`);
      load();
    } catch (e) { handleError(e, "同步"); }
    setSyncing(false);
  };

  const handleDelete = async (platform: string, accountId: string) => {
    if (!confirm(`确定删除 ${platform} / ${accountId}?`)) return;
    try {
      await api.deleteCookieAccount(platform, accountId);
      load();
    } catch (e) { handleError(e, "删除"); }
  };

  const handleHarvest = async (platform: string) => {
    try {
      await api.harvestCookie(platform);
      alert(`已为 ${platform} 启动采集器窗口。请在弹出的新终端和浏览器中完成登录，然后回此页面点击"同步到 DB"。`);
    } catch (e) { handleError(e, "启动采集器"); }
  };

  // Stats
  const totalAccounts = platforms.reduce((s, p) => s + p.account_count, 0);
  const activeAccounts = platforms.reduce((s, p) => s + p.active_count, 0);
  const invalidAccounts = platforms.reduce((s, p) => s + p.invalid_count, 0);
  const cooldownAccounts = totalAccounts - activeAccounts - invalidAccounts;

  // Health ring data
  const healthData = [
    { name: "有效", value: activeAccounts, color: HEALTH_RING_COLORS[0] },
    { name: "冷却中", value: Math.max(0, cooldownAccounts), color: HEALTH_RING_COLORS[1] },
    { name: "失效", value: invalidAccounts, color: HEALTH_RING_COLORS[2] },
  ].filter(d => d.value > 0);

  if (healthData.length === 0 && totalAccounts === 0) {
    healthData.push({ name: "无数据", value: 1, color: HEALTH_RING_COLORS[3] });
  }

  return (
    <div className="animate-in">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Cookie 管理</h1>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>
            {totalAccounts} 个账号 · {activeAccounts} 有效 · {invalidAccounts} 失效
            {lastRefresh && <> · 最后刷新 {lastRefresh.toLocaleTimeString("zh-CN")}</>}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: "var(--text-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} style={{ width: 14, height: 14 }} />
            自动刷新
          </label>
          <button className="btn btn-ghost" onClick={handleSync} disabled={syncing}
            style={{ fontSize: "0.75rem" }}>
            {syncing ? "..." : "🔄 同步到 DB"}
          </button>
          <button className="btn btn-primary" onClick={handleValidateAll}
            disabled={validating === "__all__"} style={{ fontSize: "0.75rem" }}>
            {validating === "__all__" ? "⏳ 验证中..." : "🔍 验证全部"}
          </button>
        </div>
      </div>

      {/* Health Ring + Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
          <ResponsiveContainer width={160} height={160}>
            <PieChart>
              <Pie data={healthData} cx="50%" cy="50%" innerRadius={50} outerRadius={70} paddingAngle={3} dataKey="value" stroke="none">
                {healthData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <RechartsTooltip formatter={(value, name) => [value, name]} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ position: "absolute", textAlign: "center" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: totalAccounts > 0 && invalidAccounts === 0 ? "#22c55e" : invalidAccounts > 0 ? "#ef4444" : "var(--text-muted)" }}>
              {totalAccounts > 0 ? `${Math.round(activeAccounts / totalAccounts * 100)}%` : "—"}
            </div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>健康率</div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem" }}>
          {[
            { label: "有效账号", value: activeAccounts, color: "#22c55e" },
            { label: "失效账号", value: invalidAccounts, color: "#ef4444" },
            { label: "平台覆盖", value: platforms.filter(p => p.account_count > 0).length, color: "#3b82f6" },
          ].map(s => (
            <div key={s.label} className="card" style={{ textAlign: "center", padding: "1rem" }}>
              <div style={{ fontSize: "1.75rem", fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Platform Cards */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: "0.75rem",
      }}>
        {platforms.map((p: any) => {
          const vr = validationResults[p.platform];
          const healthColor = p.account_count === 0 ? "#9e9e9e"
            : p.invalid_count > 0 ? "#f44336"
              : p.active_count > 0 ? "#4caf50" : "#ff9800";

          return (
            <div key={p.platform} className="card" style={{
              padding: "0.75rem",
              borderLeft: `3px solid ${healthColor}`,
              cursor: "pointer",
            }}
              onClick={() => setExpanded(expanded === p.platform ? null : p.platform)}
            >
              {/* Card Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <span style={{ fontWeight: 600 }}>{p.display_name}</span>
                <div style={{ display: "flex", gap: "0.25rem", alignItems: "center" }}>
                  {p.account_count > 0 && (
                    <span style={{
                      fontSize: "0.625rem", padding: "2px 6px", borderRadius: 4,
                      background: healthColor + "22", color: healthColor, fontWeight: 600,
                    }}>
                      {p.active_count}/{p.account_count}
                    </span>
                  )}
                  <button
                    className="btn btn-secondary"
                    style={{ padding: "2px 6px", fontSize: "0.625rem", background: "#2196f322", color: "#2196f3" }}
                    onClick={(e) => { e.stopPropagation(); handleHarvest(p.platform); }}
                  >
                    启动采集
                  </button>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: "2px 6px", fontSize: "0.625rem" }}
                    onClick={(e) => { e.stopPropagation(); handleValidate(p.platform); }}
                    disabled={validating === p.platform || p.account_count === 0}
                  >
                    {validating === p.platform ? "..." : "验证"}
                  </button>
                </div>
              </div>

              {/* Card Body */}
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                {p.account_count === 0 ? (
                  <span>尚未采集 Cookie</span>
                ) : (
                  <>
                    <span>采集: {p.harvested_at
                      ? new Date(p.harvested_at).toLocaleString("zh-CN", {
                        month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })
                      : "—"}</span>
                    {vr && (
                      <div style={{ marginTop: 4, color: vr.valid ? "#4caf50" : "#f44336", fontWeight: 500 }}>
                        {vr.valid ? "✅" : "❌"} {vr.detail}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Expanded — Account Details */}
              {expanded === p.platform && p.accounts?.length > 0 && (
                <div style={{
                  marginTop: "0.75rem", paddingTop: "0.75rem",
                  borderTop: "1px solid var(--border)",
                }}>
                  {p.accounts.map((acc: any) => (
                    <div key={acc.id} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "0.25rem 0", fontSize: "0.75rem",
                    }}>
                      <div>
                        <span style={{ fontWeight: 500 }}>{acc.id}</span>
                        <span style={{
                          marginLeft: 6, fontSize: "0.625rem", padding: "1px 5px",
                          borderRadius: 3,
                          background: (STATUS_COLORS[acc.status] || "#999") + "22",
                          color: STATUS_COLORS[acc.status] || "#999",
                        }}>
                          {acc.status}
                        </span>
                        <span style={{ marginLeft: 6, color: "var(--text-muted)" }}>
                          {acc.cookie_count} cookies
                        </span>
                      </div>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "1px 4px", fontSize: "0.625rem", color: "#f44336" }}
                        onClick={(e) => { e.stopPropagation(); handleDelete(p.platform, acc.id); }}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Empty state */}
      {platforms.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "4rem 2rem" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem", opacity: 0.4 }}>🍪</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>正在加载 Cookie 状态...</p>
        </div>
      )}

      {/* Hint */}
      <div className="card" style={{
        marginTop: "1.5rem", background: "linear-gradient(135deg, #1a2234, #1e2a42)",
        fontSize: "0.75rem", color: "var(--text-secondary)",
      }}>
        <strong>使用方法:</strong>&nbsp;
        运行 <code style={{ background: "rgba(255,255,255,0.1)", padding: "1px 4px", borderRadius: 3 }}>
          python -m price_monitor.cookie_harvester -p &lt;platform&gt;
        </code> 在浏览器中登录后自动采集 Cookie, 然后点击&quot;同步到 DB&quot;保存到数据库。
      </div>
    </div>
  );
}
