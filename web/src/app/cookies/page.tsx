"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function CookiesPage() {
  const [items, setItems] = useState<any[]>([]);

  const load = () => api.getCookies().then((r: any) => setItems(r.items || [])).catch(console.error);
  useEffect(() => { load(); }, []);

  const statusColor = (s: string) => s === "ACTIVE" ? "var(--accent-green)" : s === "EXPIRED" ? "var(--accent-red)" : "var(--accent-orange)";

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>Cookie 管理</h1>

      <div className="card" style={{ marginBottom: "1rem", background: "linear-gradient(135deg, #1a2234, #1e2a42)" }}>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          💡 Cookie 用于平台登录验证。当 Cookie 过期时，系统会通过飞书推送过期提醒。
          请在对应平台重新登录后，通过 API 更新 Cookie。
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
        {items.map((c: any) => (
          <div key={c.id} className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <span style={{ fontWeight: 600, fontSize: "1rem" }}>{c.platform}</span>
              <span className="badge" style={{ background: `${statusColor(c.status)}22`, color: statusColor(c.status) }}>
                {c.status}
              </span>
            </div>
            <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <span>账号: {c.account_id}</span>
              <span>Cookie 数: {c.cookie_count}</span>
              <span>最后使用: {c.last_used ? new Date(c.last_used).toLocaleString("zh-CN") : "从未"}</span>
              {c.expired_at && <span style={{ color: "var(--accent-red)" }}>过期时间: {new Date(c.expired_at).toLocaleString("zh-CN")}</span>}
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="card" style={{ gridColumn: "1 / -1", textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
            暂无 Cookie 账号。运行采集后会自动从本地 accounts.json 导入。
          </div>
        )}
      </div>
    </div>
  );
}
