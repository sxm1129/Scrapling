"use client";
import { useEffect, useState, useCallback } from "react";
import { api, handleError } from "@/lib/api";

const PLATFORM_LABELS: Record<string, string> = {
  taobao: "淘宝", tmall: "天猫", jd_express: "京东秒送",
  pinduoduo: "拼多多", taobao_flash: "淘宝闪购",
  douyin: "抖音", meituan_flash: "美团闪购", xiaohongshu: "小红书",
  community_group: "社区团购", pupu: "朴朴超市", xiaoxiang: "小象超市", dingdong: "叮咚买菜",
};

const STATUS_COLORS: Record<string, string> = {
  PENDING: "#9e9e9e",
  RUNNING: "#2196f3",
  SUCCESS: "#4caf50",
  FAILED: "#f44336",
  CANCELLED: "#ff9800",
};

const STATUS_LABELS: Record<string, string> = {
  PENDING: "等待中",
  RUNNING: "运行中",
  SUCCESS: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};

export default function CollectionPage() {
  const [status, setStatus] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState({ platform: "", status: "" });
  const [loading, setLoading] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState<string | null>(null);

  const loadStatus = useCallback(() => {
    api.getCollectionStatus().then(setStatus).catch(() => {});
  }, []);

  const loadJobs = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = { page: String(page), page_size: "15" };
    if (filter.platform) params.platform = filter.platform;
    if (filter.status) params.status = filter.status;
    api.getCollectionJobs(params)
      .then((r: any) => { setJobs(r.items || []); setTotal(r.total || 0); })
      .catch((e) => handleError(e, "加载任务"))
      .finally(() => setLoading(false));
  }, [page, filter]);

  useEffect(() => { loadStatus(); loadJobs(); }, [loadStatus, loadJobs]);

  // 自动刷新 (运行中任务时)
  useEffect(() => {
    const hasRunning = status?.running_jobs?.length > 0;
    if (!hasRunning) return;
    const interval = setInterval(() => { loadStatus(); loadJobs(); }, 3000);
    return () => clearInterval(interval);
  }, [status, loadStatus, loadJobs]);

  const handleTriggerFull = async () => {
    setTriggerLoading("full");
    try {
      await api.triggerFullScan();
      setTimeout(() => { loadStatus(); loadJobs(); }, 500);
    } catch (e) { handleError(e, "触发扫描"); }
    setTriggerLoading(null);
  };

  const handleTriggerPlatform = async (platform: string) => {
    setTriggerLoading(platform);
    try {
      await api.triggerPlatformScan(platform);
      setTimeout(() => { loadStatus(); loadJobs(); }, 500);
    } catch (e) { handleError(e, `触发 ${platform} 扫描`); }
    setTriggerLoading(null);
  };

  const handleCancel = async (jobId: number) => {
    try {
      await api.cancelJob(jobId);
      loadStatus(); loadJobs();
    } catch (e) { handleError(e, "取消任务"); }
  };

  const totalPages = Math.ceil(total / 15);

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>采集管理</h1>
        <button className="btn btn-primary" onClick={handleTriggerFull}
          disabled={triggerLoading === "full"}>
          {triggerLoading === "full" ? "⏳ 启动中..." : "🚀 全量扫描"}
        </button>
      </div>

      {/* 运行中任务 */}
      {status?.running_jobs?.length > 0 && (
        <div className="card" style={{ marginBottom: "1.5rem", border: "1px solid #2196f3" }}>
          <h3 style={{ fontWeight: 600, marginBottom: "0.75rem", color: "#2196f3" }}>
            运行中任务
          </h3>
          {status.running_jobs.map((job: any) => (
            <div key={job.id} style={{
              display: "flex", alignItems: "center", gap: "1rem",
              padding: "0.5rem 0", borderBottom: "1px solid var(--border)",
            }}>
              <span style={{ fontSize: "0.875rem", fontWeight: 600 }}>
                #{job.id} {job.job_type === "FULL_SCAN" ? "全量扫描" :
                  job.job_type === "PLATFORM_SCAN" ? `${PLATFORM_LABELS[job.platform] || job.platform}` : "单URL"}
              </span>
              <div style={{ flex: 1, background: "var(--border)", borderRadius: 4, height: 8 }}>
                <div style={{
                  width: `${job.progress}%`, height: "100%",
                  background: "linear-gradient(90deg, #2196f3, #4caf50)",
                  borderRadius: 4, transition: "width 0.3s",
                }} />
              </div>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", minWidth: 60 }}>
                {job.progress}% · {job.success_items} 条
              </span>
              <button className="btn btn-ghost" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem", color: "#f44336" }}
                onClick={() => handleCancel(job.id)}>取消</button>
            </div>
          ))}
        </div>
      )}

      {/* 平台状态卡片 */}
      <h3 style={{ fontWeight: 600, marginBottom: "0.75rem" }}>平台状态</h3>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
        gap: "0.75rem", marginBottom: "1.5rem",
      }}>
        {status?.platforms?.map((p: any) => (
          <div key={p.platform} className="card" style={{ padding: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>
                {PLATFORM_LABELS[p.platform] || p.platform}
              </span>
              {p.last_job && (
                <span style={{
                  fontSize: "0.625rem", padding: "2px 6px", borderRadius: 4,
                  background: (STATUS_COLORS[p.last_job.status] || "#999") + "22",
                  color: STATUS_COLORS[p.last_job.status] || "#999",
                  fontWeight: 600,
                }}>
                  {STATUS_LABELS[p.last_job.status] || p.last_job.status}
                </span>
              )}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
              {p.last_job ? (
                <>{p.last_job.success_items || 0} 条 · {p.last_job.finished_at
                  ? new Date(p.last_job.finished_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
                  : "—"}</>
              ) : "尚未采集"}
            </div>
            <button
              className="btn btn-ghost"
              style={{ width: "100%", fontSize: "0.75rem", padding: "0.25rem" }}
              onClick={() => handleTriggerPlatform(p.platform)}
              disabled={triggerLoading === p.platform}
            >
              {triggerLoading === p.platform ? "..." : "▶ 采集"}
            </button>
          </div>
        ))}
      </div>

      {/* 任务历史 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
        <h3 style={{ fontWeight: 600 }}>任务历史</h3>
        <div className="filter-bar" style={{ gap: "0.5rem" }}>
          <select className="input" style={{ width: 130, fontSize: "0.75rem" }}
            value={filter.platform} onChange={(e) => { setFilter({ ...filter, platform: e.target.value }); setPage(1); }}>
            <option value="">全部平台</option>
            {Object.entries(PLATFORM_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="input" style={{ width: 100, fontSize: "0.75rem" }}
            value={filter.status} onChange={(e) => { setFilter({ ...filter, status: e.target.value }); setPage(1); }}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>共 {total} 条</span>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>类型</th>
              <th>平台</th>
              <th>状态</th>
              <th>进度</th>
              <th>成功/失败</th>
              <th>违规</th>
              <th>触发</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j: any) => (
              <tr key={j.id}>
                <td style={{ color: "var(--text-muted)" }}>#{j.id}</td>
                <td style={{ fontSize: "0.75rem" }}>
                  {j.job_type === "FULL_SCAN" ? "全量" : j.job_type === "PLATFORM_SCAN" ? "平台" : "URL"}
                </td>
                <td>{j.platform ? (PLATFORM_LABELS[j.platform] || j.platform) : "全部"}</td>
                <td>
                  <span style={{
                    fontSize: "0.75rem", padding: "2px 8px", borderRadius: 4,
                    background: (STATUS_COLORS[j.status] || "#999") + "22",
                    color: STATUS_COLORS[j.status] || "#999", fontWeight: 600,
                  }}>
                    {STATUS_LABELS[j.status] || j.status}
                  </span>
                </td>
                <td>
                  <div style={{ width: 60, background: "var(--border)", borderRadius: 3, height: 6 }}>
                    <div style={{
                      width: `${j.progress}%`, height: "100%",
                      background: STATUS_COLORS[j.status] || "#999",
                      borderRadius: 3,
                    }} />
                  </div>
                </td>
                <td style={{ fontSize: "0.75rem" }}>{j.success_items}/{j.fail_items}</td>
                <td style={{ color: j.violations_found > 0 ? "var(--accent-red)" : "var(--text-muted)", fontWeight: j.violations_found > 0 ? 600 : 400 }}>
                  {j.violations_found}
                </td>
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{j.triggered_by}</td>
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {j.created_at ? new Date(j.created_at).toLocaleString("zh-CN", {
                    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit"
                  }) : "—"}
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>暂无采集记录</td></tr>
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
    </div>
  );
}
