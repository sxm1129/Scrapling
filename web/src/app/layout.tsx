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
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  
  // Search state
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("admin_token") || "";
    setToken(t);
    const c = localStorage.getItem("sidebar_collapsed") === "true";
    setCollapsed(c);
    const th = localStorage.getItem("kashi_theme") as "dark" | "light" | null;
    if (th) setTheme(th);

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
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

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("kashi_theme", next);
  };

  const doSearch = async (q: string) => {
    setSearchQuery(q);
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      // We will create this API endpoint GET /api/v1/search?q=...
      // For now, if api.ts doesn't have it, we use fetch directly or add it later.
      const t = localStorage.getItem("admin_token") || "";
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, {
        headers: { Authorization: `Bearer ${t}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.items || []);
      }
    } catch (e) {
      console.error(e);
    }
    setSearchLoading(false);
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
    <html lang="zh-CN" data-theme={theme}>
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
              <div style={{ display: "flex", gap: "4px", flexDirection: collapsed ? "column" : "row" }}>
                <button
                  onClick={toggleTheme}
                  style={{
                    background: "none", border: "1px solid var(--border)", borderRadius: 6,
                    color: "var(--text-muted)", cursor: "pointer", padding: "4px 6px",
                    fontSize: "0.875rem", lineHeight: 1, transition: "all 0.2s",
                  }}
                  title={theme === "dark" ? "切换亮色模式" : "切换暗色模式"}
                >
                  {theme === "dark" ? "☀️" : "🌙"}
                </button>
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
            </div>

            {/* Quick Search Trigger */}
            {!collapsed && (
              <div
                onClick={() => setSearchOpen(true)}
                style={{
                  background: "var(--bg-secondary)", border: "1px solid var(--border)",
                  borderRadius: "6px", padding: "6px 10px", marginBottom: "1rem",
                  cursor: "text", display: "flex", justifyContent: "space-between",
                  alignItems: "center", color: "var(--text-muted)", fontSize: "0.75rem"
                }}
              >
                <span>🔍 搜索...</span>
                <span style={{ background: "var(--border)", padding: "2px 4px", borderRadius: 4, fontSize: "0.6rem" }}>⌘K</span>
              </div>
            )}
            {collapsed && (
              <button
                onClick={() => setSearchOpen(true)}
                title="搜索 (CMD+K)"
                style={{
                  background: "none", border: "none", color: "var(--text-muted)",
                  cursor: "pointer", fontSize: "1.2rem", padding: "0.5rem", marginBottom: "0.5rem"
                }}
              >
                🔍
              </button>
            )}

            {/* Nav Links */}
            <nav style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, overflowY: "auto", overflowX: "hidden" }}>
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

        {/* Global Search Modal */}
        {searchOpen && (
          <div className="modal-overlay" onMouseDown={() => setSearchOpen(false)}>
            <div 
              className="card" 
              style={{ width: "min(600px, 90vw)", marginTop: "10vh", alignSelf: "flex-start", padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}
              onMouseDown={e => e.stopPropagation()}
            >
              <div style={{ display: "flex", alignItems: "center", padding: "1rem", borderBottom: "1px solid var(--border)" }}>
                <span style={{ fontSize: "1.2rem", marginRight: "0.5rem" }}>🔍</span>
                <input 
                  autoFocus
                  placeholder="搜索商品、店铺、工单号或违规链接..."
                  value={searchQuery}
                  onChange={e => doSearch(e.target.value)}
                  style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--text-primary)", fontSize: "1rem" }}
                />
                <button 
                  onClick={() => setSearchOpen(false)}
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px", fontSize: "0.7rem", color: "var(--text-muted)", cursor: "pointer" }}
                >
                  ESC
                </button>
              </div>

              <div style={{ maxHeight: "400px", overflowY: "auto" }}>
                {!searchQuery && (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                    输入关键字以检索全局数据...
                  </div>
                )}
                {searchQuery && searchLoading && (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                    搜索中...
                  </div>
                )}
                {searchQuery && !searchLoading && searchResults.length === 0 && (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                    没有找到匹配的结果
                  </div>
                )}
                {searchResults.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    {searchResults.map((res: any, idx) => (
                      <Link 
                        key={idx} 
                        href={res.url || "#"} 
                        onClick={() => setSearchOpen(false)}
                        style={{ 
                          padding: "0.75rem 1rem", borderBottom: "1px solid var(--border)", 
                          textDecoration: "none", color: "var(--text-primary)",
                          display: "flex", flexDirection: "column", gap: 4
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{res.title}</span>
                          <span className="badge" style={{ fontSize: "0.7rem" }}>{res.type}</span>
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {res.description}
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </body>
    </html>
  );
}
