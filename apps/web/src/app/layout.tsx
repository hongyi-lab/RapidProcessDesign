import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rapid Process Design",
  description: "Mission-driven aircraft concept design and optimization"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
