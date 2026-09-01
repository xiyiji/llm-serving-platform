"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", title: "Home", sub: "Project overview", icon: "⌂" },
  { href: "/chat", title: "Chat", sub: "Inference playground", icon: "💬" },
  { href: "/admin", title: "Admin Dashboard", sub: "Platform ops console", icon: "⚙" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">✦ LLM Serving Platform</div>
      <h1>Console</h1>
      {ITEMS.map((it) => (
        <Link key={it.href} href={it.href}>
          <div className={`nav-item ${pathname === it.href ? "active" : ""}`}>
            <div>
              <div className="title">{it.icon}&nbsp; {it.title}</div>
              <div className="sub">{it.sub}</div>
            </div>
            <span>›</span>
          </div>
        </Link>
      ))}
    </aside>
  );
}
