import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";

export const metadata: Metadata = {
  title: "CropLens — Agricultural Dataset Intelligence",
  description:
    "Interactive agricultural dataset intelligence platform for NIErnaya Phase 2. Rigorous data validation, duplicate detection, and cross-dataset analysis.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-croplens-bg text-zinc-100 antialiased">
        <Sidebar />
        <div className="flex min-h-screen flex-col md:pl-[248px]">
          <Header />
          <main className="flex-1 pb-20 md:pb-12">{children}</main>
        </div>
      </body>
    </html>
  );
}

