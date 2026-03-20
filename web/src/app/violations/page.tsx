"use client";
import { useEffect, useState, useCallback } from "react";
import { api, handleError } from "@/lib/api";
import ResizableTable from "@/components/ResizableTable";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

/* ─── Screenshot Preview Modal ─── */
function ScreenshotModal({ path, onClose }: { path: string; onClose: () => void }) {
  const imgSrc = path.startsWith("http") ? path : `/screenshots/${path.replace(/^.*\/screenshots\//, "")}`;
  return (
    <div className="modal-overlay" onClick={onClose} style={{ zIndex: 1000 }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "#0f172a",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: "1.5rem",
        maxWidth: "90vw",
        maxHeight: "90vh",
        overflow: "auto",
        position: "relative",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h3 style={{ fontWeight: 600, fontSize: "0.9rem" }}>截图证据</h3>
          <button className="btn btn-ghost" style={{ padding: "0.25rem 0.5rem" }} onClick={onClose}>✕</button>
        </div>
        <img
          src={imgSrc}
          alt="违规截图"
          style={{ maxWidth: "80vw", maxHeight: "70vh", borderRadius: 8, display: "block" }}
          onError={(e: any) => { e.target.src = ""; e.target.alt = "截图加载失败"; }}
        />
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem", wordBreak: "break-all" }}>
          {path}
        </p>
      </div>
    </div>
  );
}

export default function ViolationsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ platform: "", severity: "" });
  const [selected, setSelected] = useState<any>(null);
  const [screenshotPath, setScreenshotPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Batch selection
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
  const [batchAction, setBatchAction] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = { page: String(page), page_size: "20" };
    if (filters.platform) params.platform = filters.platform;
    if (filters.severity) params.severity = filters.severity;
    api.getViolations(params).then((r: any) => {
      setItems(r.items || []);
      setTotal(r.total || 0);
    }).catch((e) => handleError(e, "加载违规列表")).finally(() => setLoading(false));
  }, [page, filters]);

  useEffect(() => { load(); setCheckedIds(new Set()); }, [load]);

  const totalPages = Math.ceil(total / 20);
  const allChecked = items.length > 0 && items.every(v => checkedIds.has(v.id));

  const toggleAll = () => {
    if (allChecked) setCheckedIds(new Set());
    else setCheckedIds(new Set(items.map(v => v.id)));
  };

  const toggleItem = (id: number) => {
    const s = new Set(checkedIds);
    s.has(id) ? s.delete(id) : s.add(id);
    setCheckedIds(s);
  };

  const handleBatchOp = async () => {
    if (checkedIds.size === 0) return;
    const ids = [...checkedIds];
    if (batchAction === "whitelist") {
      const matched = items.filter(v => ids.includes(v.id));
      for (const v of matched) {
        if (!v.shop_name) continue;
        await fetch("/api/whitelist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule_type: "SHOP", match_pattern: v.shop_name, platform: v.platform, reason: "批量加白名单" }),
        });
      }
      alert(`已将 ${ids.length} 条记录的店铺加入白名单`);
      setCheckedIds(new Set());
      load();
    } else if (batchAction === "workorder") {
      // 创建工单：跳转到工单页并预填
      alert(`已选 ${ids.length} 条，请前往工单页创建批量工单（功能开发中）`);
    }
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>违规管理</h1>

      {/* Filters & Batch Actions */}
      <div className="filter-bar" style={{ marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
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

        {checkedIds.size > 0 && (
          <div style={{ display: "flex", gap: 8, marginLeft: 8 }}>
            <span style={{ fontSize: "0.8rem", color: "var(--accent-blue)", alignSelf: "center" }}>
              已选 {checkedIds.size} 条
            </span>
            <select className="input" style={{ width: 120 }} value={batchAction}
              onChange={e => setBatchAction(e.target.value)}>
              <option value="">批量操作...</option>
              <option value="whitelist">批量加白名单</option>
              <option value="workorder">批量创建工单</option>
            </select>
            {batchAction && (
              <button className="btn btn-primary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.8rem" }}
                onClick={handleBatchOp}>
                执行
              </button>
            )}
          </div>
        )}

        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginLeft: "auto" }}>
          共 {total} 条记录
        </span>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <ResizableTable id="violations_table" stickyFirstCol={true}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <input type="checkbox" checked={allChecked} onChange={toggleAll}
                    style={{ cursor: "pointer", width: 14, height: 14 }} />
                </th>
                <th>ID</th>
                <th>严重度</th>
                <th>平台</th>
                <th>商品名称</th>
                <th>到手价</th>
                <th>基准价</th>
                <th>差额%</th>
                <th>店铺</th>
                <th>发货城市</th>
                <th>截图</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((v: any) => (
                <tr key={v.id} style={{ background: checkedIds.has(v.id) ? "rgba(59,130,246,0.07)" : undefined }}>
                  <td>
                    <input type="checkbox" checked={checkedIds.has(v.id)} onChange={() => toggleItem(v.id)}
                      style={{ cursor: "pointer", width: 14, height: 14 }} />
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>#{v.id}</td>
                  <td><span className={`badge badge-${v.severity.toLowerCase()}`}>{v.severity}</span></td>
                  <td>{PLATFORM_LABELS[v.platform] || v.platform}</td>
                  <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.canonical_url ? (
                      <a href={v.canonical_url.startsWith('http') ? v.canonical_url : '#'} target="_blank" rel="noopener"
                        style={{ color: "inherit", textDecoration: "none" }}
                        title={v.product_name}>
                        {v.product_name}
                      </a>
                    ) : v.product_name}
                  </td>
                  <td style={{ color: "var(--accent-red)", fontWeight: 600 }}>¥{v.final_price}</td>
                  <td>¥{v.baseline_price}</td>
                  <td style={{ color: "var(--accent-orange)" }}>-{(v.gap_percent * 100).toFixed(1)}%</td>
                  <td style={{ color: "var(--text-muted)", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.shop_name || "-"}
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>{v.ship_from_city || "-"}</td>
                  <td>
                    {v.screenshot_path ? (
                      <button className="btn btn-ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.7rem" }}
                        onClick={() => setScreenshotPath(v.screenshot_path)}>
                        🖼️ 查看
                      </button>
                    ) : <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>无</span>}
                  </td>
                  <td>
                    <button className="btn btn-ghost" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                      onClick={() => setSelected(v)}>
                      详情
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={12} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无违规记录</td></tr>
              )}
            </tbody>
          </table>
        </ResizableTable>
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

      {/* Screenshot Preview Modal */}
      {screenshotPath && <ScreenshotModal path={screenshotPath} onClose={() => setScreenshotPath(null)} />}

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
                  <a href={selected.canonical_url?.startsWith('http') ? selected.canonical_url : '#'} target="_blank" rel="noopener"
                    style={{ color: "var(--accent-blue)", wordBreak: "break-all" }}>
                    {selected.canonical_url.substring(0, 60)}...
                  </a>
                </Row>
              )}
              {selected.screenshot_path && (
                <Row label="截图">
                  <button className="btn btn-ghost" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                    onClick={() => { setSelected(null); setScreenshotPath(selected.screenshot_path); }}>
                    🖼️ 查看截图
                  </button>
                </Row>
              )}
              <Row label="创建时间">{selected.created_at ? new Date(selected.created_at).toLocaleString("zh-CN") : "-"}</Row>

              {/* Quick Actions */}
              <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: "0.75rem", display: "flex", gap: 8, flexWrap: "wrap" }}>
                {selected.shop_name && (
                  <button className="btn btn-ghost" style={{ fontSize: "0.75rem" }}
                    onClick={async () => {
                      await fetch("/api/whitelist", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ rule_type: "SHOP", match_pattern: selected.shop_name, platform: selected.platform, reason: "快速加白名单" }),
                      });
                      alert(`已将 "${selected.shop_name}" 加入白名单`);
                      setSelected(null);
                      load();
                    }}>
                    🟢 加白名单
                  </button>
                )}
                <a href="/workorders" className="btn btn-ghost" style={{ fontSize: "0.75rem", textDecoration: "none" }}>
                  📋 查看工单
                </a>
              </div>
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
