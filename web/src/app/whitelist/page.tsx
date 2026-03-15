"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

export default function WhitelistPage() {
  const [items, setItems] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "" });

  const load = () => api.getWhitelist().then((r: any) => setItems(r.items || [])).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.match_pattern) return;
    try {
      await api.createWhitelist(form);
      setForm({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "" });
      setShowAdd(false);
      load();
    } catch (e) { handleError(e, "添加白名单"); }
  };

  const handleRevoke = async (id: number) => {
    if (!confirm("确定撤销?")) return;
    try {
      await api.revokeWhitelist(id);
      load();
    } catch (e) { handleError(e, "撤销白名单"); }
  };

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>白名单管理</h1>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ 添加规则</button>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr><th>类型</th><th>匹配模式</th><th>平台</th><th>原因</th><th>审批人</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {items.map((w: any) => (
              <tr key={w.id}>
                <td><span className="badge badge-active">{w.rule_type}</span></td>
                <td style={{ fontFamily: "monospace" }}>{w.match_pattern}</td>
                <td>{w.platform || "全部"}</td>
                <td style={{ color: "var(--text-muted)" }}>{w.reason || "-"}</td>
                <td style={{ color: "var(--text-muted)" }}>{w.approved_by || "-"}</td>
                <td>
                  <span className={`badge ${w.status === "ACTIVE" ? "badge-active" : "badge-expired"}`}>
                    {w.status}
                  </span>
                </td>
                <td>
                  {w.status === "ACTIVE" && (
                    <button className="btn btn-danger" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                      onClick={() => handleRevoke(w.id)}>撤销</button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无白名单规则</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>添加白名单规则</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>规则类型</label>
                <select className="input" value={form.rule_type}
                  onChange={e => setForm({ ...form, rule_type: e.target.value })}>
                  <option value="SHOP">店铺</option>
                  <option value="SKU">SKU</option>
                  <option value="URL">链接</option>
                  <option value="PROJECT">项目</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>匹配模式 *</label>
                <input className="input" placeholder="店铺名/商品关键词/URL片段" value={form.match_pattern}
                  onChange={e => setForm({ ...form, match_pattern: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>限定平台</label>
                <select className="input" value={form.platform}
                  onChange={e => setForm({ ...form, platform: e.target.value })}>
                  <option value="">全部平台</option>
                  <option value="taobao">淘宝</option><option value="tmall">天猫</option>
                  <option value="jd">京东</option><option value="pinduoduo">拼多多</option>
                  <option value="taobao_flash">淘宝闪购</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>原因</label>
                <input className="input" placeholder="已报备项目价等" value={form.reason}
                  onChange={e => setForm({ ...form, reason: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>审批人</label>
                <input className="input" placeholder="审批人姓名" value={form.approved_by}
                  onChange={e => setForm({ ...form, approved_by: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.5rem" }}>
                <button className="btn btn-ghost" onClick={() => setShowAdd(false)}>取消</button>
                <button className="btn btn-primary" onClick={handleAdd}>保存</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
