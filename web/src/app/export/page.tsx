"use client";
import { useState } from "react";
import { api, handleError } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

export default function ExportPage() {
  const [platform, setPlatform] = useState("");
  const [severity, setSeverity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [exportType, setExportType] = useState<"standard" | "evidence">("standard");
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (platform) params.platform = platform;
      if (severity) params.severity = severity;
      if (startDate) params.start = new Date(startDate).toISOString();
      if (endDate) params.end = new Date(endDate + "T23:59:59").toISOString();
      const data = await api.exportViolations(params);
      const items = data.items || [];

      // CSV helper
      const escapeCsv = (val: any) => {
        const s = String(val ?? "");
        return /[,"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      };

      let headers: string[];
      let rows: any[][];

      if (exportType === "evidence") {
        // Evidence chain export: includes screenshot path, hash, canonical URL
        headers = [
          "ID", "严重度", "平台", "商品名称", "到手价", "基准价", "差额%", "差额¥",
          "店铺", "发货城市", "白名单", "链接", "截图路径", "截图哈希", "操作人", "时间"
        ];
        rows = items.map((v: any) => [
          v.id, v.severity,
          PLATFORM_LABELS[v.platform] || v.platform,
          escapeCsv(v.product_name || ""),
          v.final_price, v.baseline_price,
          `${(v.gap_percent * 100).toFixed(1)}%`,
          v.gap_value,
          escapeCsv(v.shop_name || ""),
          escapeCsv(v.ship_from_city || ""),
          v.is_whitelisted ? "是" : "否",
          escapeCsv(v.canonical_url || ""),
          escapeCsv(v.screenshot_path || ""),
          escapeCsv(v.screenshot_hash || ""),
          escapeCsv(v.operator || "system"),
          v.created_at || "",
        ]);
      } else {
        headers = ["ID", "严重度", "平台", "商品名称", "到手价", "基准价", "差额%", "差额¥", "店铺", "发货城市", "白名单", "链接", "时间"];
        rows = items.map((v: any) => [
          v.id, v.severity,
          PLATFORM_LABELS[v.platform] || v.platform,
          escapeCsv(v.product_name || ""),
          v.final_price, v.baseline_price,
          `${(v.gap_percent * 100).toFixed(1)}%`,
          v.gap_value,
          escapeCsv(v.shop_name || ""),
          escapeCsv(v.ship_from_city || ""),
          v.is_whitelisted ? "是" : "否",
          escapeCsv(v.canonical_url || ""),
          v.created_at || "",
        ]);
      }

      const csv = "\uFEFF" + [headers.join(","), ...rows.map((r: any[]) => r.join(","))].join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const suffix = exportType === "evidence" ? "_evidence_chain" : "";
      a.download = `violations_export${suffix}_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      handleError(e, "导出");
    }
    setLoading(false);
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>数据导出</h1>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Standard Export */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <h3 style={{ fontWeight: 600, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            📥 违规数据导出
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {/* Export type toggle */}
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: 4 }}>导出类型</label>
              <div style={{ display: "flex", gap: 4, background: "var(--bg-secondary)", borderRadius: 8, padding: 4 }}>
                {[
                  { key: "standard" as const, label: "标准导出" },
                  { key: "evidence" as const, label: "完整证据链" },
                ].map(t => (
                  <button key={t.key}
                    style={{
                      flex: 1, padding: "6px 12px", borderRadius: 6, border: "none",
                      background: exportType === t.key ? "var(--accent-blue)" : "transparent",
                      color: exportType === t.key ? "#fff" : "var(--text-muted)",
                      fontSize: "0.8rem", fontWeight: exportType === t.key ? 600 : 400,
                      cursor: "pointer", transition: "all 0.2s",
                    }}
                    onClick={() => setExportType(t.key)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Date range */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>起始日期</label>
                <input className="input" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>截止日期</label>
                <input className="input" type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
              </div>
            </div>

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
                <option value="P2">P2 轻微</option>
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleExport} disabled={loading} style={{ marginTop: "0.5rem" }}>
              {loading ? "⏳ 导出中..." : exportType === "evidence" ? "📋 导出完整证据链 CSV" : "📥 导出 CSV"}
            </button>
          </div>
        </div>

        {/* Export info panel */}
        <div className="card" style={{ padding: "1.5rem", background: "linear-gradient(135deg, #1a2234, #1e2a42)" }}>
          <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>导出说明</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <div>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>📥 标准导出</div>
              包含违规记录的核心字段：ID、平台、价格、店铺、时间等基础信息，适用于日常运营分析。
            </div>
            <div>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>📋 完整证据链</div>
              在标准字段基础上，额外包含截图文件路径、截图指纹哈希、操作人等证据链字段，适用于法务取证和合规审计。
            </div>
            <div style={{ padding: "0.75rem", background: "rgba(59,130,246,0.1)", borderRadius: 8, borderLeft: "3px solid var(--accent-blue)", fontSize: "0.8rem" }}>
              <strong>提示：</strong>导出文件使用 UTF-8 BOM 编码，可直接用 Excel 打开而不会出现中文乱码。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
