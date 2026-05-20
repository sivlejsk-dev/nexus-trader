import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { NexusVoice } from "@/components/NexusVoice";

export const metadata: Metadata = {
  title: "Nexus Trader — AI Market Research",
  description: "AI-powered stock market research and options trading assistant",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden bg-[#0a0e1a] text-gray-100">
        <Sidebar />
        <main className="flex-1 overflow-auto pt-12 md:pt-0">{children}</main>
        <NexusVoice />
      </body>
    </html>
  );
}
