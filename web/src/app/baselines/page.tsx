"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function BaselinesPage() {
  const [items, setItems] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ product_pattern: "", sku_name: "", baseline_price: "", note: "" });

  const load = () => api.getBaselines().then((r: any) => setItems(r.items || [])).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.product_pattern || !form.baseline_price) return;
    await api.createBaseline({
      product_pattern: form.product_pattern,
      sku_name: form.sku_name,
      baseline_price: parseFloat(form.baseline_price),
      note: form.note,
    });
    setForm({ product_pattern: "", sku_name: "", baseline_price: "", note: "" });
    setShowAdd(false);
    load();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除?")) return;
    await api.deleteBaseline(id);
    load();
  };

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>基准价管理</h1>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ 添加基准价</button>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr><th>匹配模式</th><th>SKU 名称</th><th>基准价</th><th>备注</th><th>更新时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {items.map((b: any) => (
              <tr key={b.id}>
                <td style={{ fontFamily: "monospace", color: "var(--accent-purple)" }}>{b.product_pattern}</td>
                <td>{b.sku_name || "-"}</td>
                <td style={{ fontWeight: 600 }}>¥{b.baseline_price}</td>
                <td style={{ color: "var(--text-muted)" }}>{b.note || "-"}</td>
                <td style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  {b.updated_at ? new Date(b.updated_at).toLocaleString("zh-CN") : "-"}
                </td>
                <td>
                  <button className="btn btn-danger" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                    onClick={() => handleDelete(b.id)}>删除</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
                暂无基准价，点击右上角添加
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Add Modal */}
      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>添加基准价</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>匹配模式 *</label>
                <input className="input" placeholder="如: 卡士007" value={form.product_pattern}
                  onChange={e => setForm({ ...form, product_pattern: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>SKU 名称</label>
                <input className="input" placeholder="如: 卡士007酸奶 1kg" value={form.sku_name}
                  onChange={e => setForm({ ...form, sku_name: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>基准价 (¥) *</label>
                <input className="input" type="number" step="0.01" placeholder="69.90" value={form.baseline_price}
                  onChange={e => setForm({ ...form, baseline_price: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>备注</label>
                <input className="input" placeholder="MAP价/供价等" value={form.note}
                  onChange={e => setForm({ ...form, note: e.target.value })} />
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
