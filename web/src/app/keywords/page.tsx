"use client";
import { useEffect, useState, useRef } from "react";
import { api, handleError } from "@/lib/api";

export default function KeywordsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [newKw, setNewKw] = useState("");
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.getKeywords().then((r: any) => setItems(r.items || [])).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!newKw.trim()) return;
    try {
      await api.addKeyword({ keyword: newKw.trim(), priority: 0 });
      setNewKw("");
      load();
    } catch (e) { handleError(e, "添加关键词"); }
  };

  const handleToggle = async (id: number, enabled: boolean) => {
    try {
      await api.toggleKeyword(id, !enabled);
      load();
    } catch (e) { handleError(e, "切换关键词"); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除?")) return;
    try {
      await api.deleteKeyword(id);
      load();
    } catch (e) { handleError(e, "删除关键词"); }
  };

  const handleCSVUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      const lines = text.split(/[\r\n]+/).map(l => l.trim()).filter(Boolean);
      // Skip header if it looks like one
      const keywords = lines[0]?.toLowerCase().includes("keyword") ? lines.slice(1) : lines;
      // Extract first column if CSV
      const cleaned = keywords.map(k => k.split(",")[0].trim()).filter(k => k && k.length <= 100);
      if (cleaned.length === 0) {
        alert("CSV 文件中没有找到有效的关键词");
        return;
      }
      const result = await api.batchAddKeywords(cleaned);
      alert(`导入成功：新增 ${result.added} 个关键词（去重后），当前共 ${result.total} 个`);
      load();
    } catch (err) {
      handleError(err, "CSV 导入");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleExport = () => {
    window.open(api.exportKeywordsUrl, "_blank");
  };

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>关键词管理</h1>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="btn btn-ghost" onClick={handleExport} style={{ fontSize: "0.8rem" }}>
            📥 导出 CSV
          </button>
          <label className="btn btn-ghost" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
            📤 {importing ? "导入中..." : "导入 CSV"}
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.txt"
              style={{ display: "none" }}
              onChange={handleCSVUpload}
              disabled={importing}
            />
          </label>
        </div>
      </div>

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
        <div className="card" style={{ textAlign: "center", padding: "4rem 2rem" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem", opacity: 0.4 }}>🔍</div>
          <p style={{ color: "var(--text-muted)", marginBottom: "1rem", fontSize: "0.95rem" }}>还没有添加任何关键词</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1.5rem" }}>添加关键词后，系统将自动在各电商平台搜索并监测价格</p>
          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center" }}>
            <button className="btn btn-primary" onClick={() => document.querySelector<HTMLInputElement>('.input')?.focus()}>
              手动添加
            </button>
            <label className="btn btn-ghost" style={{ cursor: "pointer" }}>
              📤 从 CSV 批量导入
              <input type="file" accept=".csv,.txt" style={{ display: "none" }} onChange={handleCSVUpload} />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
