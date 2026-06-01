"use client";

import dynamic from "next/dynamic";

const CreatorApp = dynamic(() => import("./CreatorApp"), {
  ssr: false,
  loading: () => (
    <main>
      <h1>Creator Video Compare</h1>
      <p className="subtitle">Loading…</p>
    </main>
  ),
});

export default function Page() {
  return <CreatorApp />;
}
