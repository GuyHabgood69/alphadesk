import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaDesk — Multi-Agent Trading Terminal",
  description:
    "Autonomous paper-trading terminal powered by AI agents, risk guardrails, and vector memory.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
