"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import "./globals.css";

const APP_VERSION = "V1.0.1";

const NAV_ITEMS = [
  { href: "/", label: "看板", icon: "📊" },
  { href: "/collection", label: "采集管理", icon: "🔄" },
  { href: "/offers", label: "采集数据", icon: "📦" },
  { href: "/violations", label: "违规管理", icon: "🚨" },
  { href: "/violations/analysis", label: "违规分析", icon: "📈" },
  { href: "/workorders", label: "工单管理", icon: "📋" },
  { href: "/attribution", label: "归因管理", icon: "🗺️" },
  { href: "/whitelist", label: "白名单", icon: "✅" },
  { href: "/whitelist/audit", label: "白名单审计", icon: "🔒" },
  { href: "/reports", label: "报表中心", icon: "📑" },
  { href: "/baselines", label: "基准价", icon: "💰" },
  { href: "/keywords", label: "关键词", icon: "🔍" },
  { href: "/cookies", label: "Cookie", icon: "🍪" },
  { href: "/export", label: "数据导出", icon: "📥" },
];

const BREADCRUMB_MAP: Record<string, string> = {
  "/": "看板",
  "/collection": "采集管理",
  "/offers": "采集数据",
  "/violations": "违规管理",
  "/violations/analysis": "违规分析",
  "/workorders": "工单管理",
  "/attribution": "归因管理",
  "/whitelist": "白名单",
  "/whitelist/audit": "白名单审计",
  "/reports": "报表中心",
  "/baselines": "基准价",
  "/keywords": "关键词",
  "/cookies": "Cookie 管理",
  "/export": "数据导出",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("admin_token") || "";
    setToken(t);
    const c = localStorage.getItem("sidebar_collapsed") === "true";
    setCollapsed(c);
  }, []);

  const handleSaveToken = () => {
    localStorage.setItem("admin_token", token);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar_collapsed", String(next));
  };

  // Build breadcrumb segments
  const breadcrumbs = (() => {
    if (pathname === "/") return [{ label: "看板", href: "/" }];
    const segments = pathname.split("/").filter(Boolean);
    const crumbs = [{ label: "首页", href: "/" }];
    let built = "";
    for (const seg of segments) {
      built += `/${seg}`;
      const label = BREADCRUMB_MAP[built] || seg;
      crumbs.push({ label, href: built });
    }
    return crumbs;
  })();

  return (
    <html lang="zh-CN">
      <head>
        <title>KaShi 控价监测</title>
        <meta name="description" content="线上价格监测与控价管理系统" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          {/* Sidebar */}
          <aside
            className={`sidebar${collapsed ? " sidebar-collapsed" : ""}`}
            style={{
              width: collapsed ? 60 : 220,
              padding: collapsed ? "1rem 0.5rem" : "1rem 0.75rem",
              flexShrink: 0,
              display: "flex",
              flexDirection: "column",
              transition: "width 0.25s ease, padding 0.25s ease",
            }}
          >
            {/* Logo & Toggle */}
            <div style={{
              padding: collapsed ? "0.5rem 0 1rem" : "0.5rem 1rem 1.5rem",
              borderBottom: "1px solid var(--border)",
              marginBottom: "1rem",
              display: "flex",
              alignItems: collapsed ? "center" : "flex-start",
              justifyContent: collapsed ? "center" : "space-between",
              flexDirection: collapsed ? "column" : "row",
              gap: collapsed ? 8 : 0,
            }}>
              {!collapsed && (
                <div>
                  <h1 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                    ⚡ KaShi
                  </h1>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>
                    控价监测系统
                  </p>
                </div>
              )}
              <button
                onClick={toggleSidebar}
                style={{
                  background: "none", border: "1px solid var(--border)", borderRadius: 6,
                  color: "var(--text-muted)", cursor: "pointer", padding: "4px 6px",
                  fontSize: "0.875rem", lineHeight: 1, transition: "all 0.2s",
                }}
                title={collapsed ? "展开侧边栏" : "收起侧边栏"}
              >
                {collapsed ? "▶" : "◀"}
              </button>
            </div>

            {/* Nav Links */}
            <nav style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={pathname === item.href ? "active" : ""}
                  title={collapsed ? item.label : undefined}
                >
                  <span>{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              ))}
            </nav>

            {/* Auth Token & Version */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem", marginTop: "auto", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {!collapsed && (
                <div className="sidebar-footer-content">
                  <label style={{ fontSize: "0.625rem", color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                    管理密码
                  </label>
                  <div style={{ display: "flex", gap: 4 }}>
                    <input
                      type="password"
                      className="input"
                      style={{ flex: 1, fontSize: "0.75rem", padding: "4px 8px" }}
                      placeholder="输入密码"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSaveToken()}
                    />
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: "0.625rem", padding: "4px 8px", color: saved ? "#4caf50" : undefined }}
                      onClick={handleSaveToken}
                    >
                      {saved ? "✓" : "保存"}
                    </button>
                  </div>
                </div>
              )}
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textAlign: "center", fontWeight: 500 }}>
                {APP_VERSION}
              </div>
            </div>
          </aside>

          {/* Main Content */}
          <main style={{ flex: 1, padding: "1.5rem 2rem", overflow: "auto" }}>
            {/* Breadcrumb */}
            {pathname !== "/" && (
              <nav style={{ marginBottom: "1rem", fontSize: "0.8rem", display: "flex", alignItems: "center", gap: 6 }}>
                {breadcrumbs.map((crumb, i) => (
                  <span key={crumb.href} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {i > 0 && <span style={{ color: "var(--text-muted)" }}>/</span>}
                    {i === breadcrumbs.length - 1 ? (
                      <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{crumb.label}</span>
                    ) : (
                      <Link href={crumb.href} style={{ color: "var(--text-muted)", textDecoration: "none" }}>
                        {crumb.label}
                      </Link>
                    )}
                  </span>
                ))}
              </nav>
            )}
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
