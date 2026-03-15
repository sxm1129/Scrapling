"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import "./globals.css";

const NAV_ITEMS = [
  { href: "/", label: "看板", icon: "📊" },
  { href: "/collection", label: "采集管理", icon: "🔄" },
  { href: "/offers", label: "采集数据", icon: "📦" },
  { href: "/violations", label: "违规管理", icon: "🚨" },
  { href: "/baselines", label: "基准价", icon: "💰" },
  { href: "/keywords", label: "关键词", icon: "🔍" },
  { href: "/whitelist", label: "白名单", icon: "✅" },
  { href: "/cookies", label: "Cookie", icon: "🍪" },
  { href: "/export", label: "数据导出", icon: "📥" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("admin_token") || "";
    setToken(t);
  }, []);

  const handleSaveToken = () => {
    localStorage.setItem("admin_token", token);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <html lang="zh-CN">
      <head>
        <title>Antigravity 价格监测</title>
        <meta name="description" content="线上价格监测与控价管理系统" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          {/* Sidebar */}
          <aside className="sidebar" style={{ width: 220, padding: "1rem 0.75rem", flexShrink: 0, display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "0.5rem 1rem 1.5rem", borderBottom: "1px solid var(--border)", marginBottom: "1rem" }}>
              <h1 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                ⚡ Antigravity
              </h1>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>
                价格监测系统
              </p>
            </div>
            <nav style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={pathname === item.href ? "active" : ""}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>

            {/* Auth Token */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem", marginTop: "auto" }}>
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
          </aside>

          {/* Main Content */}
          <main style={{ flex: 1, padding: "1.5rem 2rem", overflow: "auto" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

