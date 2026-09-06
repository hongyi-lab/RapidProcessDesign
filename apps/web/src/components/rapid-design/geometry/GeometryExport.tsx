"use client";

import { useRef, useState } from "react";
import type { GeometryState } from "./types";
import type { GeometryExportFormat } from "./aircraftExport";
import styles from "./GeometryExport.module.css";

export function GeometryExport({ geometry, name, disabled = false }: {
  geometry: GeometryState | null;
  name: string;
  disabled?: boolean;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  const working = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const unavailable = disabled || !geometry || geometry.geometry_status !== "valid" || busy;

  async function download(format: GeometryExportFormat) {
    if (unavailable || working.current || !geometry) return;
    working.current = true;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const { createGeometryExport, geometryExportFilename } = await import("./aircraftExport");
      const blob = createGeometryExport(geometry, name, format);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = geometryExportFilename(name, format);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
      setStatus(`${format.toUpperCase()} ready. Units: millimeters.`);
      if (menu.current) menu.current.open = false;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Export failed. Please try again.");
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  return (
    <div className={styles.export}>
      <details ref={menu} onKeyDown={(event) => {
        if (event.key === "Escape" && menu.current) {
          menu.current.open = false;
          menu.current.querySelector("summary")?.focus();
        }
      }}>
        <summary>Export ↓</summary>
        <div className={styles.menu}>
          <button type="button" disabled={unavailable} onClick={() => void download("step")}>Download STEP</button>
          <button type="button" disabled={unavailable} onClick={() => void download("stl")}>Download STL</button>
          <p>For SolidWorks · Millimeters<br />Faceted geometry, no feature history.</p>
          {busy && <p role="status">Preparing file…</p>}
          {error && <p role="alert" className={styles.error}>{error}</p>}
        </div>
      </details>
      <span className={styles.status} role="status">{status}</span>
    </div>
  );
}
