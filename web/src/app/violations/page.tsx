"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd: "京东",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
};

export default function ViolationsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ platform: "", severity: "" });
  const [selected, setSelected] = useState<any>(null);

  const load = () => {
    const params: Record<string, string> = { page: String(page), page_size: "20" };
    if (filters.platform) params.platform = filters.platform;
    if (filters.severity) params.severity = filters.severity;
    api.getViolations(params).then((r: any) => {
      setItems(r.items || []);
      setTotal(r.total || 0);
    }).catch(console.error);
  };

  useEffect(() => { load(); }, [page, filters]);

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>违规管理</h1>

      {/* Filters */}
      <div className="filter-bar" style={{ marginBottom: "1rem" }}>
        <select className="input" style={{ width: 150 }} value={filters.platform}
          onChange={e => { setFilters({ ...filters, platform: e.target.value }); setPage(1); }}>
          <option value="">全部平台</option>
          {Object.entries(PLATFORM_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="input" style={{ width: 120 }} value={filters.severity}
          onChange={e => { setFilters({ ...filters, severity: e.target.value }); setPage(1); }}>
          <option value="">全部级别</option>
          <option value="P0">P0 严重</option>
          <option value="P1">P1 一般</option>
        </select>
        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginLeft: "auto" }}>
          共 {total} 条记录
        </span>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>严重度</th>
              <th>平台</th>
              <th>商品名称</th>
              <th>到手价</th>
              <th>基准价</th>
              <th>差额%</th>
              <th>店铺</th>
              <th>发货城市</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((v: any) => (
              <tr key={v.id}>
                <td style={{ color: "var(--text-muted)" }}>#{v.id}</td>
                <td><span className={`badge badge-${v.severity.toLowerCase()}`}>{v.severity}</span></td>
                <td>{PLATFORM_LABELS[v.platform] || v.platform}</td>
                <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {v.product_name}
                </td>
                <td style={{ color: "var(--accent-red)", fontWeight: 600 }}>¥{v.final_price}</td>
                <td>¥{v.baseline_price}</td>
                <td style={{ color: "var(--accent-orange)" }}>-{(v.gap_percent * 100).toFixed(1)}%</td>
                <td style={{ color: "var(--text-muted)", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {v.shop_name || "-"}
                </td>
                <td style={{ color: "var(--text-muted)" }}>{v.ship_from_city || "-"}</td>
                <td>
                  <button className="btn btn-ghost" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                    onClick={() => setSelected(v)}>
                    详情
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无违规记录</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination" style={{ marginTop: "1rem", justifyContent: "center" }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
          {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => (
            <button key={i + 1} className={page === i + 1 ? "active" : ""} onClick={() => setPage(i + 1)}>
              {i + 1}
            </button>
          ))}
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
        </div>
      )}

      {/* Detail Modal */}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
              <h3 style={{ fontWeight: 600 }}>违规详情 #{selected.id}</h3>
              <button className="btn btn-ghost" style={{ padding: "0.25rem" }} onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.875rem" }}>
              <Row label="严重度"><span className={`badge badge-${selected.severity.toLowerCase()}`}>{selected.severity}</span></Row>
              <Row label="平台">{PLATFORM_LABELS[selected.platform] || selected.platform}</Row>
              <Row label="商品">{selected.product_name}</Row>
              <Row label="到手价"><span style={{ color: "var(--accent-red)", fontWeight: 600 }}>¥{selected.final_price}</span></Row>
              <Row label="基准价">¥{selected.baseline_price}</Row>
              <Row label="差额">-{(selected.gap_percent * 100).toFixed(1)}% (¥{selected.gap_value})</Row>
              <Row label="店铺">{selected.shop_name || "-"}</Row>
              <Row label="发货城市">{selected.ship_from_city || "-"}</Row>
              <Row label="白名单">{selected.is_whitelisted ? "✅ 已命中" : "❌ 未命中"}</Row>
              {selected.canonical_url && (
                <Row label="链接">
                  <a href={selected.canonical_url} target="_blank" rel="noopener"
                    style={{ color: "var(--accent-blue)", wordBreak: "break-all" }}>
                    {selected.canonical_url.substring(0, 50)}...
                  </a>
                </Row>
              )}
              <Row label="创建时间">{selected.created_at ? new Date(selected.created_at).toLocaleString("zh-CN") : "-"}</Row>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: "1rem" }}>
      <span style={{ color: "var(--text-muted)", minWidth: 80, flexShrink: 0 }}>{label}</span>
      <span>{children}</span>
    </div>
  );
}
