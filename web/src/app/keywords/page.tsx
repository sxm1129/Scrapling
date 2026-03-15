"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function KeywordsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [newKw, setNewKw] = useState("");

  const load = () => api.getKeywords().then((r: any) => setItems(r.items || [])).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!newKw.trim()) return;
    await api.addKeyword({ keyword: newKw.trim(), priority: 0 });
    setNewKw("");
    load();
  };

  const handleToggle = async (id: number, enabled: boolean) => {
    await api.toggleKeyword(id, !enabled);
    load();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除?")) return;
    await api.deleteKeyword(id);
    load();
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>关键词管理</h1>

      {/* Add Form */}
      <div className="card" style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
        <input className="input" style={{ flex: 1 }} placeholder="输入新关键词，如: 卡士酸奶"
          value={newKw} onChange={e => setNewKw(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleAdd()} />
        <button className="btn btn-primary" onClick={handleAdd}>添加</button>
      </div>

      {/* Keywords Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "0.75rem" }}>
        {items.map((kw: any) => (
          <div key={kw.id} className="card" style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            opacity: kw.enabled ? 1 : 0.5,
          }}>
            <div>
              <span style={{ fontWeight: 500 }}>{kw.keyword}</span>
              {kw.priority > 0 && <span className="badge badge-p1" style={{ marginLeft: 8 }}>重点</span>}
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button className={`btn ${kw.enabled ? "btn-ghost" : "btn-primary"}`}
                style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                onClick={() => handleToggle(kw.id, kw.enabled)}>
                {kw.enabled ? "禁用" : "启用"}
              </button>
              <button className="btn btn-danger" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                onClick={() => handleDelete(kw.id)}>删除</button>
            </div>
          </div>
        ))}
      </div>
      {items.length === 0 && (
        <p style={{ color: "var(--text-muted)", textAlign: "center", marginTop: "2rem" }}>暂无关键词</p>
      )}
    </div>
  );
}
