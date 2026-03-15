"use client";
import { useState } from "react";
import { api } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

export default function ExportPage() {
  const [platform, setPlatform] = useState("");
  const [severity, setSeverity] = useState("");
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (platform) params.platform = platform;
      if (severity) params.severity = severity;
      const data = await api.exportViolations(params);
      const items = data.items || [];

      // Convert to CSV
      const headers = ["ID", "严重度", "平台", "商品名称", "到手价", "基准价", "差额%", "差额¥", "店铺", "发货城市", "白名单", "链接", "时间"];
      const rows = items.map((v: any) => [
        v.id, v.severity,
        PLATFORM_LABELS[v.platform] || v.platform,
        `"${(v.product_name || "").replace(/"/g, '""')}"`,
        v.final_price, v.baseline_price,
        `${(v.gap_percent * 100).toFixed(1)}%`,
        v.gap_value,
        `"${(v.shop_name || "").replace(/"/g, '""')}"`,
        v.ship_from_city || "",
        v.is_whitelisted ? "是" : "否",
        v.canonical_url || "",
        v.created_at || "",
      ]);

      const csv = "\uFEFF" + [headers.join(","), ...rows.map((r: any[]) => r.join(","))].join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `violations_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("导出失败");
    }
    setLoading(false);
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>数据导出</h1>

      <div className="card" style={{ maxWidth: 500 }}>
        <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>导出违规数据</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>平台筛选</label>
            <select className="input" value={platform} onChange={e => setPlatform(e.target.value)}>
              <option value="">全部平台</option>
              {Object.entries(PLATFORM_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>严重度筛选</label>
            <select className="input" value={severity} onChange={e => setSeverity(e.target.value)}>
              <option value="">全部级别</option>
              <option value="P0">P0 严重</option>
              <option value="P1">P1 一般</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={handleExport} disabled={loading} style={{ marginTop: "0.5rem" }}>
            {loading ? "⏳ 导出中..." : "📥 导出 CSV"}
          </button>
        </div>
      </div>
    </div>
  );
}
