"use client";
import { useEffect, useState } from "react";
import { api, handleError } from "@/lib/api";

export default function AttributionPage() {
  const [topViolators, setTopViolators] = useState<any[]>([]);
  const [kpis, setKpis] = useState<any>(null);
  const [rules, setRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddRule, setShowAddRule] = useState(false);
  const [newRule, setNewRule] = useState({ dealer_name: "", owner_name: "", owner_user_id: "", platform: "", shop_name_pattern: "", ship_from_city: "", priority: 0 });

  const load = () => {
    setLoading(true);
    const end = new Date().toISOString();
    const start = new Date(Date.now() - 30 * 86400000).toISOString();
    Promise.all([
      api.getTopViolators({ limit: "20" }),
      api.getKPIs({ start, end }),
      api.getResponsibilityRules(),
    ]).then(([tv, k, r]) => {
      setTopViolators((tv as any).violators || []);
      setKpis(k);
      setRules(Array.isArray(r) ? r : []);
    }).catch(e => handleError(e, "加载归因数据")).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleAddRule = async () => {
    await api.createResponsibilityRule(newRule).catch(e => handleError(e, "创建规则"));
    setShowAddRule(false);
    setNewRule({ dealer_name: "", owner_name: "", owner_user_id: "", platform: "", shop_name_pattern: "", ship_from_city: "", priority: 0 });
    load();
  };

  const handleDeleteRule = async (id: number) => {
    await api.deleteResponsibilityRule(id).catch(e => handleError(e, "删除规则"));
    load();
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>归因 & 经销商管理</h1>

      {/* Attribution Confidence Summary */}
      {kpis && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
          {[
            { label: "近30天违规记录", value: kpis.kpi1_violations_total, color: "#ef4444" },
            { label: "责任规则数", value: rules.length, color: "#6366f1" },
            { label: "工单未分配率", value: ((1 - (kpis.kpi3_workorder_close_rate || 0)) * 100).toFixed(1) + "%", color: "#f97316" },
          ].map(({ label, value, color }) => (
            <div key={label} className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
              <div style={{ fontSize: "2rem", fontWeight: 800, color }}>{value}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Top Violating Shops */}
      <div className="card" style={{ padding: "1.5rem", marginBottom: "2rem" }}>
        <h2 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "1rem" }}>高频违规店铺排行（近30天）</h2>
        {loading ? <div style={{ color: "var(--text-muted)", textAlign: "center" }}>加载中...</div> : topViolators.length === 0 ? (
          <div style={{ color: "var(--text-muted)", textAlign: "center" }}>暂无违规数据</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "0.75rem" }}>
            {topViolators.slice(0, 12).map((v: any, i: number) => (
              <div key={i} className="card" style={{ padding: "0.75rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", background: i < 3 ? "#ef4444" : "#6366f1", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: "0.8rem", flexShrink: 0 }}># {i + 1}</div>
                <div style={{ flex: 1, overflow: "hidden" }}>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.shop_name}</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{v.platform} · {v.violation_count} 次违规 · 平均差额 {v.avg_gap_percent}%</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Responsibility Rules */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: "1rem" }}>
        <h2 style={{ fontWeight: 600, fontSize: "1rem" }}>责任归因规则（店铺/城市 → 经销商 → 责任人）</h2>
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={() => setShowAddRule(true)}>+ 新建规则</button>
      </div>

      {showAddRule && (
        <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem" }}>
          <h3 style={{ fontWeight: 600, marginBottom: "1rem", fontSize: "0.95rem" }}>新建责任规则</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem" }}>
            {[
              { key: "dealer_name", label: "经销商名称 *" },
              { key: "owner_name", label: "责任人姓名 *" },
              { key: "owner_user_id", label: "责任人ID *" },
              { key: "platform", label: "平台（留空=所有）" },
              { key: "shop_name_pattern", label: "店铺名包含关键词" },
              { key: "ship_from_city", label: "发货城市" },
            ].map(({ key, label }) => (
              <div key={key}>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{label}</label>
                <input className="input" style={{ display: "block", width: "100%" }} value={(newRule as any)[key]} onChange={e => setNewRule({ ...newRule, [key]: e.target.value })} />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button className="btn btn-primary" onClick={handleAddRule}>保存规则</button>
            <button className="btn" onClick={() => setShowAddRule(false)}>取消</button>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead><tr><th>平台</th><th>店铺关键词</th><th>发货城市</th><th>经销商</th><th>责任人</th><th>优先级</th><th>操作</th></tr></thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>暂无规则，请新建</td></tr>
            ) : rules.map((r: any) => (
              <tr key={r.id}>
                <td style={{ fontSize: "0.8rem" }}>{r.platform || <span style={{ color: "var(--text-muted)" }}>任意</span>}</td>
                <td style={{ fontSize: "0.8rem" }}>{r.shop_name_pattern || <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                <td style={{ fontSize: "0.8rem" }}>{r.ship_from_city || <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                <td style={{ fontSize: "0.85rem", fontWeight: 600 }}>{r.dealer_name}</td>
                <td style={{ fontSize: "0.85rem" }}>{r.owner_name}</td>
                <td>{r.priority}</td>
                <td><button className="btn btn-sm" style={{ color: "#ef4444" }} onClick={() => handleDeleteRule(r.id)}>停用</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
