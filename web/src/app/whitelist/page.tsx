"use client";
import { useEffect, useState, useMemo } from "react";
import { api, handleError } from "@/lib/api";
import ResizableTable from "@/components/ResizableTable";

const REJECT_REASONS = [
  "价格未恢复",
  "资质过期",
  "未提供报备单",
  "其他",
];

export default function WhitelistPage() {
  const [items, setItems] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "" });
  
  // Batch selection
  const [selected, setSelected] = useState<Set<number>>(new Set());
  
  // Revoke modal
  const [showRevoke, setShowRevoke] = useState(false);
  const [revokeReason, setRevokeReason] = useState("");

  const load = () => api.getWhitelist().then((r: any) => {
    setItems(r.items || []);
    setSelected(new Set());
  }).catch(e => handleError(e, "加载白名单"));
  
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.match_pattern) return;
    try {
      await api.createWhitelist({
        ...form,
        platform: form.platform || undefined,
        reason: form.reason || undefined,
        approved_by: form.approved_by || undefined,
      });
      setForm({ rule_type: "SHOP", match_pattern: "", platform: "", reason: "", approved_by: "" });
      setShowAdd(false);
      load();
    } catch (e) { handleError(e, "添加白名单"); }
  };

  const activeItemsCount = useMemo(() => items.filter(i => i.status === 'ACTIVE').length, [items]);
  
  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      // Only select ACTIVE ones for revoke, or wait, you can approve REVOKED ones too. Let's select all.
      setSelected(new Set(items.map(i => i.id)));
    } else {
      setSelected(new Set());
    }
  };

  const handleSelect = (id: number, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    setSelected(next);
  };

  const handleBatchApprove = async () => {
    if (selected.size === 0) return;
    if (!confirm(`确定要重新生效 ${selected.size} 条规则吗？`)) return;
    try {
      await api.batchApproveWhitelist(Array.from(selected));
      load();
    } catch (e) {
      handleError(e, "批量审批");
    }
  };

  const handleBatchRevokeConfirm = async () => {
    if (selected.size === 0) return;
    try {
      await api.batchRevokeWhitelist(Array.from(selected), revokeReason || undefined);
      setShowRevoke(false);
      setRevokeReason("");
      load();
    } catch (e) {
      handleError(e, "批量撤销");
    }
  };

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>白名单管理</h1>
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: 4 }}>配置对指定店铺/URL/商品的免罚规则</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ 添加规则</button>
      </div>

      {/* Batch Actions Toolbar */}
      {selected.size > 0 && (
        <div className="card" style={{ marginBottom: "1rem", padding: "0.75rem 1rem", display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(59, 130, 246, 0.1)", border: "1px solid var(--accent-blue)" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
            已选择 <span style={{ color: "var(--accent-blue)" }}>{selected.size}</span> 项
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="btn btn-sm" style={{ background: "var(--accent-green)", color: "white", border: "none" }} onClick={handleBatchApprove}>
              生效 (Approve)
            </button>
            <button className="btn btn-sm btn-danger" onClick={() => setShowRevoke(true)}>
              撤销 (Revoke)
            </button>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <ResizableTable id="whitelist_table" stickyFirstCol={true}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 40, textAlign: "center" }}>
                  <input 
                    type="checkbox" 
                    checked={items.length > 0 && selected.size === items.length}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>类型</th><th>匹配模式</th><th>平台</th><th>原因</th><th>审批人</th><th>状态</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w: any) => (
                <tr key={w.id} style={{ background: selected.has(w.id) ? "var(--bg-card-hover)" : "transparent" }}>
                  <td style={{ textAlign: "center" }}>
                    <input 
                      type="checkbox" 
                      checked={selected.has(w.id)}
                      onChange={(e) => handleSelect(w.id, e.target.checked)}
                    />
                  </td>
                  <td><span className="badge badge-active">{w.rule_type}</span></td>
                  <td style={{ fontFamily: "monospace" }}>{w.match_pattern}</td>
                  <td>{w.platform || "全部"}</td>
                  <td style={{ color: "var(--text-muted)" }}>{w.reason || "-"}</td>
                  <td style={{ color: "var(--text-muted)" }}>{w.approved_by || "-"}</td>
                  <td>
                    <span className={`badge ${w.status === "ACTIVE" ? "badge-active" : "badge-expired"}`}>
                      {w.status}
                    </span>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无白名单规则</td></tr>
              )}
            </tbody>
          </table>
        </ResizableTable>
      </div>

      {/* Revoke Modal */}
      {showRevoke && (
        <div className="modal-overlay" onClick={() => setShowRevoke(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>批量撤销白名单</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
              确定要撤销选中的 {selected.size} 条规则吗？撤销后，相关商品将恢复违规监测。
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4, display: "block" }}>撤销原因模板</label>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                  {REJECT_REASONS.map(r => (
                    <span 
                      key={r} 
                      onClick={() => setRevokeReason(r)}
                      style={{ 
                        fontSize: "0.75rem", padding: "2px 8px", borderRadius: 4, cursor: "pointer",
                        background: revokeReason === r ? "var(--accent-blue)" : "var(--bg-secondary)",
                        color: revokeReason === r ? "#fff" : "var(--text-muted)",
                        border: "1px solid var(--border)"
                      }}
                    >
                      {r}
                    </span>
                  ))}
                </div>
                <input 
                  className="input" 
                  placeholder="可手动输入其他原因..." 
                  value={revokeReason}
                  onChange={e => setRevokeReason(e.target.value)} 
                />
              </div>
              
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
                <button className="btn btn-ghost" onClick={() => setShowRevoke(false)}>取消</button>
                <button className="btn btn-danger" onClick={handleBatchRevokeConfirm}>确认撤销</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Modal */}
      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 style={{ fontWeight: 600, marginBottom: "1rem" }}>添加白名单规则</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>规则类型</label>
                <select className="input" value={form.rule_type}
                  onChange={e => setForm({ ...form, rule_type: e.target.value })}>
                  <option value="SHOP">店铺</option>
                  <option value="SKU">SKU</option>
                  <option value="URL">链接</option>
                  <option value="PROJECT">项目</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>匹配模式 *</label>
                <input className="input" placeholder="店铺名/商品关键词/URL片段" value={form.match_pattern}
                  onChange={e => setForm({ ...form, match_pattern: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>限定平台</label>
                <select className="input" value={form.platform}
                  onChange={e => setForm({ ...form, platform: e.target.value })}>
                  <option value="">全部平台</option>
                  <option value="taobao">淘宝</option><option value="tmall">天猫</option>
                  <option value="jd_express">京东秒送</option><option value="pinduoduo">拼多多</option>
                  <option value="taobao_flash">淘宝闪购</option><option value="douyin">抖音</option>
                  <option value="meituan_flash">美团闪购</option><option value="xiaohongshu">小红书</option>
                  <option value="community_group">社区团购</option><option value="pupu">朴朴超市</option>
                  <option value="xiaoxiang">小象超市</option><option value="dingdong">叮咚买菜</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>原因</label>
                <input className="input" placeholder="已报备项目价等" value={form.reason}
                  onChange={e => setForm({ ...form, reason: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>审批人</label>
                <input className="input" placeholder="审批人姓名" value={form.approved_by}
                  onChange={e => setForm({ ...form, approved_by: e.target.value })} />
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
