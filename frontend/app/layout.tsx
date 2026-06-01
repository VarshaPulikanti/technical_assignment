import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Creator Video RAG",
  description: "Compare YouTube vs Instagram engagement with RAG chat",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
