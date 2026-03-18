"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { api, handleError } from "@/lib/api";
import {
  PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, ResponsiveContainer, Tooltip as RechartsTooltip,
  CartesianGrid
} from "recharts";

const SEVERITY_COLORS: Record<string, string> = {
  P0: "#ef4444", P1: "#f97316", P2: "#eab308",
};
const STATUS_LABELS: Record<string, string> = {
  OPEN: "待处理", IN_PROGRESS: "处理中", WAITING_INFO: "等待信息", RESOLVED: "已解决", REJECTED: "已拒绝",
};
const STATUS_COLORS: Record<string, string> = {
  OPEN: "#ef4444", IN_PROGRESS: "#f97316", WAITING_INFO: "#a855f7", RESOLVED: "#22c55e", REJECTED: "#6b7280",
};

export default function WorkOrdersPage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ status: "", severity: "", platform: "" });
  const [selected, setSelected] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [resolveNote, setResolveNote] = useState("");
  const [actionNote, setActionNote] = useState("");
  const [showResolve, setShowResolve] = useState(false);
  const [allItems, setAllItems] = useState<any[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    const p: Record<string, string> = { page: String(page), page_size: "20" };
    if (filters.status) p.status = filters.status;
    if (filters.severity) p.severity = filters.severity;
    if (filters.platform) p.platform = filters.platform;
    api.getWorkOrders(p).then((r: any) => {
      setItems(r.workorders || []);
      setTotal(r.total || 0);
    }).catch((e) => handleError(e, "加载工单")).finally(() => setLoading(false));
    // Also load all workorders for stats
    api.getWorkOrders({ page_size: "500" }).then((r: any) => setAllItems(r.workorders || [])).catch(() => {});
  }, [page, filters]);

  useEffect(() => { load(); }, [load]);

  // SLA Stats
  const slaStats = useMemo(() => {
    const open = allItems.filter(i => i.status === "OPEN").length;
    const ip = allItems.filter(i => i.status === "IN_PROGRESS").length;
    const resolved = allItems.filter(i => i.status === "RESOLVED").length;
    const overdue = allItems.filter(i => i.sla_overdue).length;
    const onTime = Math.max(0, allItems.length - overdue);
    const slaRate = allItems.length > 0 ? ((onTime / allItems.length) * 100).toFixed(1) : "100";
    return { open, ip, resolved, overdue, onTime, slaRate, total: allItems.length };
  }, [allItems]);

  // Funnel data
  const funnelData = useMemo(() => [
    { name: "待处理", value: slaStats.open, color: STATUS_COLORS.OPEN },
    { name: "处理中", value: slaStats.ip, color: STATUS_COLORS.IN_PROGRESS },
    { name: "已解决", value: slaStats.resolved, color: STATUS_COLORS.RESOLVED },
  ], [slaStats]);

  // SLA ring data
  const slaRingData = useMemo(() => [
    { name: "按时", value: slaStats.onTime, color: "#22c55e" },
    { name: "逾期", value: slaStats.overdue, color: "#ef4444" },
  ].filter(d => d.value > 0), [slaStats]);

  if (slaRingData.length === 0) slaRingData.push({ name: "无数据", value: 1, color: "#334155" });

  const openDetail = (wo: any) => { setSelected(wo); setShowResolve(false); setResolveNote(""); setActionNote(""); };

  const handleAddAction = async () => {
    if (!actionNote.trim() || !selected) return;
    await api.addWorkOrderAction(selected.id, { action_type: "MANUAL_NOTE", note: actionNote, operator: "user" }).catch((e) => handleError(e, "追加备注"));
    const updated = await api.getWorkOrder(selected.id).catch(() => null);
    if (updated) setSelected(updated);
    setActionNote("");
    load();
  };

  const handleResolve = async () => {
    if (!resolveNote.trim() || !selected) return;
    await api.resolveWorkOrder(selected.id, { note: resolveNote, resolution_type: "PRICE_FIXED", operator: "user" }).catch((e) => handleError(e, "关闭工单"));
    setSelected(null);
    load();
  };

  const slaClass = (wo: any) => {
    if (wo.sla_overdue) return { color: "#ef4444", fontWeight: 700 as const };
    return {};
  };

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>工单管理</h1>

      {/* SLA Health Dashboard */}
      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        {/* SLA Ring Gauge */}
        <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", position: "relative", padding: "1rem" }}>
          <ResponsiveContainer width={140} height={140}>
            <PieChart>
              <Pie data={slaRingData} cx="50%" cy="50%" innerRadius={42} outerRadius={60} paddingAngle={3} dataKey="value" stroke="none">
                {slaRingData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div style={{ position: "absolute", textAlign: "center" }}>
            <div style={{ fontSize: "1.3rem", fontWeight: 700, color: Number(slaStats.slaRate) >= 80 ? "#22c55e" : "#ef4444" }}>{slaStats.slaRate}%</div>
            <div style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>SLA达标</div>
          </div>
        </div>

        {/* KPI Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
          {[
            { label: "待处理", value: slaStats.open, color: "#ef4444" },
            { label: "处理中", value: slaStats.ip, color: "#f97316" },
            { label: "已解决", value: slaStats.resolved, color: "#22c55e" },
            { label: "SLA逾期", value: slaStats.overdue, color: "#ef4444" },
          ].map(s => (
            <div key={s.label} className="card" style={{ textAlign: "center", padding: "0.75rem" }}>
              <div style={{ fontSize: "1.5rem", fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Funnel Bar Chart */}
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>工单处理漏斗</div>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={funnelData} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal vertical={false} stroke="#334155" opacity={0.3} />
              <XAxis type="number" hide />
              <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: "#e2e8f0", fontSize: 12 }} width={60} />
              <RechartsTooltip />
              <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={22}>
                {funnelData.map((entry, index) => <Cell key={index} fill={entry.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar" style={{ marginBottom: "1rem" }}>
        {[
          { label: "状态", key: "status", opts: Object.entries(STATUS_LABELS) },
          { label: "级别", key: "severity", opts: [["P0","P0 严重"],["P1","P1 一般"],["P2","P2 轻微"]] },
        ].map(({ label, key, opts }) => (
          <select key={key} className="input" style={{ width: 140 }}
            value={(filters as any)[key]}
            onChange={e => { setFilters({ ...filters, [key]: e.target.value }); setPage(1); }}>
            <option value="">全部{label}</option>
            {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ))}
        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginLeft: "auto" }}>共 {total} 条</span>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr><th>ID</th><th>级别</th><th>状态</th><th>平台</th><th>商品</th><th>违规价</th><th>基准价</th><th>差额%</th><th>责任人</th><th>SLA截止</th><th>操作</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={11} style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>加载中...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={11} style={{ textAlign: "center", padding: "2rem" }}>暂无工单</td></tr>
            ) : items.map((wo: any) => (
              <tr key={wo.id}>
                <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>#{wo.id}</td>
                <td><span className="badge" style={{ background: SEVERITY_COLORS[wo.severity] + "22", color: SEVERITY_COLORS[wo.severity], padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem", fontWeight: 700 }}>{wo.severity}</span></td>
                <td><span style={{ color: STATUS_COLORS[wo.status] || "inherit", fontWeight: 600, fontSize: "0.8rem" }}>{STATUS_LABELS[wo.status] || wo.status}</span></td>
                <td style={{ fontSize: "0.8rem" }}>{wo.platform}</td>
                <td style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.85rem" }} title={wo.product_name}>{wo.product_name}</td>
                <td style={{ color: "#ef4444", fontWeight: 700 }}>¥{wo.violation_price ?? "-"}</td>
                <td>¥{wo.baseline_price ?? "-"}</td>
                <td style={{ color: wo.gap_percent > 0.2 ? "#ef4444" : "inherit" }}>{wo.gap_percent ? (wo.gap_percent * 100).toFixed(1) + "%" : "-"}</td>
                <td style={{ fontSize: "0.8rem" }}>{wo.owner_name || <span style={{ color: "var(--text-muted)" }}>未分配</span>}</td>
                <td style={{ fontSize: "0.75rem", ...slaClass(wo) }}>{wo.sla_due_at ? new Date(wo.sla_due_at).toLocaleString("zh-CN") : "-"}{wo.sla_overdue ? " ⚠️" : ""}</td>
                <td><button className="btn btn-sm" onClick={() => openDetail(wo)}>详情</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", marginTop: "1rem" }}>
        <button className="btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>上一页</button>
        <span style={{ padding: "0.5rem 1rem", color: "var(--text-muted)" }}>第 {page} 页</span>
        <button className="btn" disabled={items.length < 20} onClick={() => setPage(p => p + 1)}>下一页</button>
      </div>

      {/* Detail Drawer */}
      {selected && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", justifyContent: "flex-end" }} onClick={() => setSelected(null)}>
          <div onClick={e => e.stopPropagation()} style={{ width: "min(600px, 100vw)", background: "var(--card-bg)", padding: "2rem", overflowY: "auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>工单 #{selected.id}<span className="badge" style={{ marginLeft: 8, background: SEVERITY_COLORS[selected.severity] + "22", color: SEVERITY_COLORS[selected.severity], padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem" }}>{selected.severity}</span></h2>
              <button className="btn" onClick={() => setSelected(null)}>✕ 关闭</button>
            </div>

            <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.85rem" }}>
              {[["平台", selected.platform], ["状态", STATUS_LABELS[selected.status] || selected.status], ["责任人", selected.owner_name || "未分配"], ["经销商", selected.dealer_name || "-"], ["违规价", `¥${selected.violation_price}`], ["基准价", `¥${selected.baseline_price}`], ["价差", selected.gap_percent ? (selected.gap_percent * 100).toFixed(1) + "%" : "-"], ["升级次数", selected.escalation_level]].map(([k, v]) => (
                <div key={String(k)}><span style={{ color: "var(--text-muted)" }}>{k}：</span><strong>{String(v)}</strong></div>
              ))}
              <div style={{ gridColumn: "span 2" }}><span style={{ color: "var(--text-muted)" }}>商品：</span><strong>{selected.product_name}</strong></div>
              {selected.canonical_url && <div style={{ gridColumn: "span 2", fontSize: "0.75rem", wordBreak: "break-all" }}><a href={selected.canonical_url?.startsWith('http') ? selected.canonical_url : '#'} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>查看原链接</a></div>}
            </div>

            {/* Action Log Timeline */}
            <h3 style={{ fontWeight: 600, marginBottom: 0 }}>操作日志</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: 200, overflowY: "auto" }}>
              {(selected.action_log || []).map((a: any, i: number) => (
                <div key={i} style={{ fontSize: "0.8rem", borderLeft: "3px solid var(--accent)", paddingLeft: "0.75rem" }}>
                  <div style={{ color: "var(--text-muted)" }}>{new Date(a.at).toLocaleString("zh-CN")} · {a.by || "system"}</div>
                  <div><strong>[{a.type}]</strong> {a.note}</div>
                </div>
              ))}
            </div>

            {/* Add note */}
            {selected.status !== "RESOLVED" && !showResolve && (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input className="input" style={{ flex: 1 }} placeholder="追加备注..." value={actionNote} onChange={e => setActionNote(e.target.value)} onKeyDown={e => e.key === "Enter" && handleAddAction()} />
                <button className="btn" onClick={handleAddAction}>提交</button>
                <button className="btn btn-primary" onClick={() => setShowResolve(true)}>关闭工单</button>
              </div>
            )}

            {/* Resolve flow */}
            {showResolve && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <textarea className="input" style={{ resize: "vertical", height: 80 }} placeholder="请描述处置结果..." value={resolveNote} onChange={e => setResolveNote(e.target.value)} />
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button className="btn btn-primary" onClick={handleResolve}>确认关闭</button>
                  <button className="btn" onClick={() => setShowResolve(false)}>取消</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
