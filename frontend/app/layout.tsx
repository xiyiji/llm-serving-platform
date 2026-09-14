import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Serving Platform Console",
  description: "Gateway, routing, batching, caching and ops console for LLM inference. Built by Mengyun Wang.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Sidebar />
          <main className="content">
            {children}
            <footer className="footer">
              Built by <a href="https://github.com/xiyiji" target="_blank" rel="noreferrer">Mengyun Wang</a> &middot;{" "}
              <a href="https://github.com/xiyiji/llm-serving-platform" target="_blank" rel="noreferrer">source</a> &middot;{" "}
              GPU engine: <a href="https://github.com/xiyiji/InferenceGateway" target="_blank" rel="noreferrer">InferenceGateway</a>
            </footer>
          </main>
        </div>
      </body>
    </html>
  );
}
