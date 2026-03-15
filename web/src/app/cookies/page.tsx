"use client";
import { useEffect, useState, useCallback } from "react";
import { api, handleError } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  active: "#4caf50",
  cooldown: "#ff9800",
  invalid: "#f44336",
  unknown: "#9e9e9e",
};

export default function CookiesPage() {
  const [platforms, setPlatforms] = useState<any[]>([]);
  const [validating, setValidating] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<Record<string, any>>({});

  const load = useCallback(() => {
    api.getCookieStatus().then((r: any) => setPlatforms(r.platforms || [])).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

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

  // 统计
  const totalAccounts = platforms.reduce((s, p) => s + p.account_count, 0);
  const activeAccounts = platforms.reduce((s, p) => s + p.active_count, 0);
  const invalidAccounts = platforms.reduce((s, p) => s + p.invalid_count, 0);

  return (
    <div className="animate-in">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Cookie 管理</h1>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>
            {totalAccounts} 个账号 · {activeAccounts} 有效 · {invalidAccounts} 失效
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
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
        <div className="card" style={{ textAlign: "center", color: "var(--text-muted)", padding: "3rem" }}>
          加载中...
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
        </code> 在浏览器中登录后自动采集 Cookie, 然后点击"同步到 DB"保存到数据库。
      </div>
    </div>
  );
}
