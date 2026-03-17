"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

export default function WhitelistAuditPage() {
  const [rules, setRules] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [kpis, setKpis] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "", expires_at: "" });

  const load = () => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - 30 * 86400000).toISOString();
    Promise.all([
      api.getWhitelist(),
      api.getKPIs({ start, end }),
    ]).then(([wl, k]) => {
      const items = Array.isArray(wl) ? wl : (wl as any).items || [];
      setRules(items);
      setTotal(items.length);
      setKpis(k);
    }).catch(e => handleError(e, "加载白名单")).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await api.createWhitelist(form).catch(e => handleError(e, "创建白名单"));
    setShowAdd(false);
    setForm({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "", expires_at: "" });
    load();
  };

  const handleRevoke = async (id: number) => {
    if (!confirm("确认撤销该白名单规则？")) return;
    await api.revokeWhitelist(id).catch(e => handleError(e, "撤销白名单"));
    load();
  };

  const now = new Date();
  const expiringRules = rules.filter(r => r.expires_at && new Date(r.expires_at) < new Date(now.getTime() + 7 * 86400000) && new Date(r.expires_at) > now);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>白名单审计</h1>

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: "#22c55e" }}>{total}</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>有效规则数</div>
        </div>
        <div className="card" style={{ padding: "1.25rem", textAlign: "center", borderColor: expiringRules.length > 0 ? "#f97316" : undefined }}>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: expiringRules.length > 0 ? "#f97316" : "var(--text-muted)" }}>{expiringRules.length}</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>即将过期（7天内）</div>
        </div>
        {kpis && (<>
          <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: "#0ea5e9" }}>{kpis.kpi7_whitelist_hit_count}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>近30天命中次数</div>
          </div>
          <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: "#14b8a6" }}>{(kpis.kpi7_whitelist_hit_rate * 100).toFixed(1)}%</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>低价命中白名单率</div>
          </div>
        </>)}
      </div>

      {/* Expiry Alerts */}
      {expiringRules.length > 0 && (
        <div style={{ background: "#f9731622", border: "1px solid #f97316", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.5rem", color: "#f97316", fontSize: "0.875rem" }}>
          ⚠️ 以下 {expiringRules.length} 条白名单规则将在 7 天内过期，请及时续期或撤销：{expiringRules.map(r => r.match_pattern).join("、")}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ 新建白名单</button>
      </div>

      {showAdd && (
        <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem" }}>
          <h3 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "0.95rem" }}>新建白名单规则</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem" }}>
            <div>
              <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>规则类型</label>
              <select className="input" style={{ display: "block", width: "100%" }} value={form.rule_type} onChange={e => setForm({ ...form, rule_type: e.target.value })}>
                {["SHOP", "SKU", "URL", "PROJECT"].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {[
              { key: "match_pattern", label: "匹配模式（店铺名/SKU/URL）*" },
              { key: "platform", label: "平台（留空=所有）" },
              { key: "reason", label: "白名单原因" },
              { key: "approved_by", label: "审批人" },
            ].map(({ key, label }) => (
              <div key={key}>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{label}</label>
                <input className="input" style={{ display: "block", width: "100%" }} value={(form as any)[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} />
              </div>
            ))}
            <div>
              <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>过期时间</label>
              <input type="date" className="input" style={{ display: "block", width: "100%" }} value={form.expires_at} onChange={e => setForm({ ...form, expires_at: e.target.value })} />
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button className="btn btn-primary" onClick={handleCreate}>保存</button>
            <button className="btn" onClick={() => setShowAdd(false)}>取消</button>
          </div>
        </div>
      )}

      {/* Rules Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead><tr><th>类型</th><th>匹配模式</th><th>平台</th><th>原因</th><th>审批人</th><th>到期时间</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: "center", padding: "2rem" }}>加载中...</td></tr>
            ) : rules.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>暂无白名单规则</td></tr>
            ) : rules.map((r: any) => {
              const expired = r.expires_at && new Date(r.expires_at) < now;
              const expiring = !expired && r.expires_at && new Date(r.expires_at) < new Date(now.getTime() + 7 * 86400000);
              return (
                <tr key={r.id}>
                  <td><span className="badge badge-primary">{r.rule_type}</span></td>
                  <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.match_pattern}</td>
                  <td style={{ fontSize: "0.8rem" }}>{r.platform || "全部"}</td>
                  <td style={{ fontSize: "0.8rem", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.reason || "—"}</td>
                  <td style={{ fontSize: "0.8rem" }}>{r.approved_by || "—"}</td>
                  <td style={{ fontSize: "0.75rem", color: expired ? "#ef4444" : expiring ? "#f97316" : "inherit" }}>
                    {r.expires_at ? new Date(r.expires_at).toLocaleDateString("zh-CN") : "永久"}
                    {expiring && " ⚠️"}
                    {expired && " 已过期"}
                  </td>
                  <td><span style={{ color: r.status === "ACTIVE" ? "#22c55e" : "#ef4444", fontWeight: 600, fontSize: "0.8rem" }}>{r.status}</span></td>
                  <td><button className="btn btn-sm" style={{ color: "#ef4444" }} onClick={() => handleRevoke(r.id)}>撤销</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
