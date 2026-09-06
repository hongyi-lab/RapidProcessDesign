"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { SettingsPanel } from "@/components/settings-panel/SettingsPanel";
import { getLlmSettings } from "@/lib/llmSettings";
import styles from "./AIWorkspaceGate.module.css";

export function AIWorkspaceGate({ children, apiBaseUrl }: { children: ReactNode; apiBaseUrl: string }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    let sequence = 0;
    const check = async () => {
      const request = ++sequence;
      const localKey = Boolean(getLlmSettings().apiKey.trim());
      if (localKey) {
        if (active) setConfigured(true);
        return;
      }
      try {
        const response = await fetch("/api/chat", { cache: "no-store" });
        const status = response.ok ? await response.json() : { configured: false };
        if (active && request === sequence) setConfigured(status.configured === true);
      } catch {
        if (active && request === sequence) setConfigured(false);
      }
    };
    void check();
    window.addEventListener("llm-settings-changed", check);
    window.addEventListener("storage", check);
    window.addEventListener("focus", check);
    return () => {
      active = false;
      window.removeEventListener("llm-settings-changed", check);
      window.removeEventListener("storage", check);
      window.removeEventListener("focus", check);
    };
  }, []);

  if (configured) return children;
  return (
    <main className={styles.page}>
      <header>
        <Link href="/rapid-design">← Back to Design</Link>
        <SettingsPanel apiBaseUrl={apiBaseUrl} />
      </header>
      <section>
        <span className={styles.icon} aria-hidden="true">AI</span>
        <h1>{configured === null ? "Checking your connection…" : "Connect a model to use AI chat"}</h1>
        <p>AI chat is an optional workspace for describing and refining aircraft in natural language. Add a model connection in Settings to get started.</p>
        <Link className={styles.primary} href="/rapid-design">Explore the aircraft demo ↗</Link>
        <small>The Design workspace works without an AI connection.</small>
      </section>
    </main>
  );
}
