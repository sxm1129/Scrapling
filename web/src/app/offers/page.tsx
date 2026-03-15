"use client";
import { useEffect, useState, useCallback } from "react";
import { api, handleError } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

const PAGE_SIZE = 30;

export default function OffersPage() {
  const [offers, setOffers] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [platform, setPlatform] = useState("");
  const [keyword, setKeyword] = useState("");
  const [shopName, setShopName] = useState("");
  const [sortBy, setSortBy] = useState("time_desc");

  // Detail modal
  const [detail, setDetail] = useState<any | null>(null);

  const fetchOffers = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(PAGE_SIZE),
      };
      if (platform) params.platform = platform;
      if (keyword) params.keyword = keyword;
      if (shopName) params.shop_name = shopName;
      if (sortBy) params.sort_by = sortBy;

      const res = await api.getOffers(params);
      setOffers(res.items || []);
      setTotal(res.total || 0);
    } catch (e) {
      handleError(e, "加载采集数据");
    }
    setLoading(false);
  }, [page, platform, keyword, shopName, sortBy]);

  useEffect(() => { fetchOffers(); }, [fetchOffers]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleSearch = () => { setPage(1); fetchOffers(); };
  const handleReset = () => {
    setPlatform(""); setKeyword(""); setShopName(""); setSortBy("time_desc"); setPage(1);
  };

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>采集数据</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: 4 }}>
            浏览所有平台采集到的商品价格数据
          </p>
        </div>
        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>共 {total} 条</span>
      </div>

      {/* Filters */}
      <div className="card" style={{ marginBottom: "1rem", display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <select
          className="input"
          style={{ width: 140 }}
          value={platform}
          onChange={(e) => { setPlatform(e.target.value); setPage(1); }}
        >
          <option value="">全部平台</option>
          {Object.entries(PLATFORM_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        
        <select
          className="input"
          style={{ width: 140 }}
          value={sortBy}
          onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
        >
          <option value="time_desc">最新采集</option>
          <option value="price_asc">价格从低到高</option>
          <option value="price_desc">价格从高到低</option>
        </select>

        <input
          className="input"
          style={{ width: 160 }}
          placeholder="搜索关键词"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />

        <input
          className="input"
          style={{ width: 160 }}
          placeholder="店铺名称"
          value={shopName}
          onChange={(e) => setShopName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />

        <button className="btn btn-primary" onClick={handleSearch} style={{ fontSize: "0.75rem" }}>
          搜索
        </button>
        <button className="btn btn-ghost" onClick={handleReset} style={{ fontSize: "0.75rem" }}>
          重置
        </button>
      </div>

      {/* Table */}
      <div className="card" style={{ overflow: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>平台</th>
              <th>关键词</th>
              <th style={{ maxWidth: 280 }}>商品名称</th>
              <th>原价</th>
              <th>到手价</th>
              <th>店铺</th>
              <th>发货地</th>
              <th>采集时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)" }}>加载中...</td></tr>
            ) : offers.length === 0 ? (
              <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)" }}>暂无采集数据</td></tr>
            ) : offers.map((o: any) => (
              <tr key={o.id}>
                <td>
                  <span className="badge" style={{ background: "var(--bg-secondary)", color: "var(--text-secondary)" }}>
                    {PLATFORM_LABELS[o.platform] || o.platform}
                  </span>
                </td>
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{o.keyword || "-"}</td>
                <td style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {o.canonical_url ? (
                    <a href={o.canonical_url} target="_blank" rel="noreferrer"
                       style={{ color: "var(--accent-blue)", textDecoration: "none" }}>
                      {o.product_name || o.product_id}
                    </a>
                  ) : (o.product_name || o.product_id)}
                </td>
                <td style={{ color: "var(--text-muted)" }}>
                  {o.original_price > 0 ? `¥${o.original_price}` : "-"}
                </td>
                <td style={{ color: "var(--accent-green)", fontWeight: 600 }}>
                  ¥{o.final_price || o.raw_price || 0}
                </td>
                <td style={{ fontSize: "0.75rem", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {o.shop_name || "-"}
                </td>
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{o.ship_from_city || "-"}</td>
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {o.captured_at ? new Date(o.captured_at).toLocaleString("zh-CN") : "-"}
                </td>
                <td>
                  <button className="btn btn-ghost" style={{ fontSize: "0.625rem", padding: "2px 8px" }}
                    onClick={() => setDetail(o)}>
                    详情
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", marginTop: "1rem", alignItems: "center" }}>
          <button className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            ← 上一页
          </button>
          <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            第 {page} / {totalPages} 页
          </span>
          <button className="btn btn-ghost" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
            下一页 →
          </button>
        </div>
      )}

      {/* Detail Modal */}
      {detail && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex",
          alignItems: "center", justifyContent: "center", zIndex: 9999,
        }} onClick={() => setDetail(null)}>
          <div className="card" onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 560, width: "90%", maxHeight: "80vh", overflow: "auto", position: "relative" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>商品详情</h3>
              <button className="btn btn-ghost" onClick={() => setDetail(null)} style={{ fontSize: "1rem" }}>✕</button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1rem", fontSize: "0.875rem" }}>
              <DetailRow label="平台" value={PLATFORM_LABELS[detail.platform] || detail.platform} />
              <DetailRow label="商品名" value={detail.product_name} />
              <DetailRow label="商品ID" value={detail.product_id} />
              <DetailRow label="关键词" value={detail.keyword} />
              <DetailRow label="原价" value={detail.original_price > 0 ? `¥${detail.original_price}` : "-"} />
              <DetailRow label="售价" value={`¥${detail.raw_price}`} />
              <DetailRow label="到手价" value={`¥${detail.final_price}`} highlight />
              <DetailRow label="优惠信息" value={detail.coupon_info || "-"} />
              <DetailRow label="店铺" value={detail.shop_name || "-"} />
              <DetailRow label="发货地" value={detail.ship_from_city || "-"} />
              <DetailRow label="销量" value={detail.sales_volume || "-"} />
              <DetailRow label="置信度" value={detail.confidence || "-"} />
              <DetailRow label="解析状态" value={detail.parse_status || "-"} />
              <DetailRow label="采集时间" value={detail.captured_at ? new Date(detail.captured_at).toLocaleString("zh-CN") : "-"} />
              {detail.canonical_url && (
                <DetailRow label="商品链接" value={
                  <a href={detail.canonical_url} target="_blank" rel="noreferrer"
                     style={{ color: "var(--accent-blue)", wordBreak: "break-all" }}>
                    {detail.canonical_url}
                  </a>
                } />
              )}
              {detail.screenshot_hash && (
                <DetailRow label="证据链Hash" value={
                  <span style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all" }}>
                    {detail.screenshot_hash}
                  </span>
                } />
              )}
            </div>
            {detail.screenshot_path && (
              <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
                <span style={{ color: "var(--text-muted)", fontWeight: 500, fontSize: "0.875rem", marginBottom: "0.5rem", display: "block" }}>页面防篡改截图</span>
                <img 
                  src={`/screenshots/${detail.screenshot_path.split('/').pop()}`} 
                  alt="Scrape Evidence Screenshot" 
                  style={{ width: "100%", borderRadius: 6, border: "1px solid var(--border-color)" }} 
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  return (
    <>
      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>{label}</span>
      <span style={{ color: highlight ? "var(--accent-green)" : "var(--text-primary)", fontWeight: highlight ? 600 : 400 }}>
        {value || "-"}
      </span>
    </>
  );
}
