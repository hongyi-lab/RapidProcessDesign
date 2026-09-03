"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { CadViewer } from "@/components/cad-viewer/CadViewer";
import type { AircraftPreviewSpec } from "@/components/cad-viewer/previewGeometry";

import styles from "./rapid-design.module.css";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8900";

type InputDefinition = {
  key: string;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  step: number;
  default: number;
  kind: "requirement" | "constraint";
};

type DesignVariable = {
  key: string;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
};

type RapidConfig = {
  title: string;
  description: string;
  inputs: InputDefinition[];
  design_variables: DesignVariable[];
  aerodynamics: { backend: string; model_size: string };
};

type RapidJob = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  error: string | null;
};

type ConstraintResult = {
  name: string;
  label: string;
  value: number;
  limit: number;
  margin: number;
  unit: string;
  relation: string;
  satisfied: boolean;
};

type ConvergencePoint = {
  iteration: number;
  takeoff_mass_kg: number;
  feasible: boolean;
};

type RapidResult = {
  status: "feasible" | "no_feasible_solution_found";
  feasible: boolean;
  design: Record<string, number>;
  metrics: Record<string, number>;
  constraints: ConstraintResult[];
  aircraft_spec: AircraftPreviewSpec;
  convergence: ConvergencePoint[];
  model_provenance: {
    name: string;
    version: string;
    model_size?: string;
    license: string;
    paper?: string;
    paper_url?: string;
    repository_url?: string;
  };
  warnings: string[];
};

const STAGE_LABELS: Record<string, string> = {
  queued: "等待计算",
  initializing_surrogate: "载入代理模型",
  optimizing: "搜索可行设计",
  completed: "计算完成",
  cancelling: "正在停止",
  cancelled: "已停止",
  failed: "计算失败",
};

const METRIC_CARDS = [
  ["takeoff_mass_kg", "起飞质量", "kg"],
  ["achieved_range_km", "预计航程", "km"],
  ["lift_to_drag", "巡航 L/D", ""],
  ["fuel_mass_kg", "燃油质量", "kg"],
] as const;

function formatNumber(value: number | undefined, digits = 1): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function ConvergenceChart({ points }: { points: ConvergencePoint[] }) {
  if (points.length < 2) {
    return <div className={styles.chartEmpty}>开始优化后显示质量收敛过程</div>;
  }
  const width = 520;
  const height = 116;
  const padding = 12;
  const values = points.map((point) => point.takeoff_mass_kg);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = Math.max(1, maximum - minimum);
  const polyline = points
    .map((point, index) => {
      const x = padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2);
      const y = padding + ((maximum - point.takeoff_mass_kg) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="起飞质量收敛曲线">
        <defs>
          <linearGradient id="rapid-chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#53d9b1" stopOpacity="0.28" />
            <stop offset="1" stopColor="#53d9b1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline points={`${padding},${height - padding} ${polyline} ${width - padding},${height - padding}`} fill="url(#rapid-chart-fill)" stroke="none" />
        <polyline points={polyline} fill="none" stroke="#53d9b1" strokeWidth="2.5" strokeLinejoin="round" />
      </svg>
      <span>{formatNumber(maximum)} kg</span>
      <strong>{formatNumber(values.at(-1))} kg</strong>
    </div>
  );
}

export default function RapidDesignPage() {
  const [config, setConfig] = useState<RapidConfig | null>(null);
  const [inputs, setInputs] = useState<Record<string, number>>({});
  const [job, setJob] = useState<RapidJob | null>(null);
  const [result, setResult] = useState<RapidResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/rapid-design/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("无法读取 Rapid Design 配置");
        return (await response.json()) as RapidConfig;
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((item) => [item.key, item.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : "配置读取失败");
        }
      });
    return () => {
      controller.abort();
      eventSourceRef.current?.close();
    };
  }, []);

  const running = job?.status === "queued" || job?.status === "running";
  const groupedInputs = useMemo(() => {
    if (!config) return { requirement: [], constraint: [] };
    return {
      requirement: config.inputs.filter((item) => item.kind === "requirement"),
      constraint: config.inputs.filter((item) => item.kind === "constraint"),
    };
  }, [config]);

  async function loadResult(jobId: string) {
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${jobId}/result`);
    if (!response.ok) throw new Error("结果文件尚未生成");
    setResult((await response.json()) as RapidResult);
  }

  function observeJob(created: RapidJob) {
    eventSourceRef.current?.close();
    const source = new EventSource(
      `${API_BASE_URL}/api/rapid-design/jobs/${created.id}/events`,
    );
    eventSourceRef.current = source;
    const update = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as RapidJob;
      setJob((current) => (current ? { ...current, ...payload } : created));
    };
    source.addEventListener("queued", update as EventListener);
    source.addEventListener("progress", update as EventListener);
    source.addEventListener("completed", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
      void loadResult(created.id).catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "结果读取失败");
      });
    }) as EventListener);
    source.addEventListener("failed", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
      const payload = JSON.parse(event.data) as RapidJob;
      setError(payload.error ?? "设计生成失败");
    }) as EventListener);
    source.addEventListener("cancelled", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
    }) as EventListener);
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) return;
      setError("与计算服务的连接中断");
    };
  }

  async function runDesign() {
    setError(null);
    setResult(null);
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(body?.detail ?? "无法启动设计任务");
    }
    const created = (await response.json()) as RapidJob;
    setJob(created);
    observeJob(created);
  }

  async function cancelDesign() {
    if (!job) return;
    await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${job.id}/cancel`, {
      method: "POST",
    });
  }

  const runtimeStatus = running
    ? {
        status: "running" as const,
        currentStageLabel: STAGE_LABELS[job?.stage ?? "queued"],
        progress: (job?.progress ?? 0) * 100,
      }
    : job?.status === "failed"
      ? { status: "failed" as const, error: job.error }
      : result
        ? { status: "completed" as const }
        : { status: "idle" as const };

  return (
    <main className={styles.app}>
      <header className={styles.topbar}>
        <div className={styles.brandMark}>RP</div>
        <div>
          <h1>Rapid Process Design</h1>
          <p>任务驱动的固定翼概念设计</p>
        </div>
        <div className={styles.topbarMeta}>
          <span className={styles.modelDot} />
          NeuralFoil {config?.aerodynamics.model_size ?? "—"}
          <Link href="/">返回 AeroSpec</Link>
        </div>
      </header>

      <section className={styles.workspace}>
        <aside className={styles.inputsPanel}>
          <div className={styles.sectionIntro}>
            <span>01 / 输入</span>
            <h2>定义任务与边界</h2>
            <p>拖动参数后重新生成，优化器会搜索满足全部约束的机体方案。</p>
          </div>
          {!config && !error && <div className={styles.loading}>正在读取参数…</div>}
          {(["requirement", "constraint"] as const).map((group) => (
            <div className={styles.inputGroup} key={group}>
              <div className={styles.groupTitle}>
                {group === "requirement" ? "任务需求" : "设计约束"}
                <span>{groupedInputs[group].length}</span>
              </div>
              {groupedInputs[group].map((item) => (
                <label className={styles.inputField} key={item.key}>
                  <span className={styles.inputLabel}>
                    {item.label}
                    <small>{item.unit}</small>
                  </span>
                  <div className={styles.inputControl}>
                    <input
                      type="range"
                      min={item.minimum}
                      max={item.maximum}
                      step={item.step}
                      value={inputs[item.key] ?? item.default}
                      disabled={running}
                      onChange={(event) =>
                        setInputs((current) => ({
                          ...current,
                          [item.key]: Number(event.target.value),
                        }))
                      }
                    />
                    <input
                      type="number"
                      min={item.minimum}
                      max={item.maximum}
                      step={item.step}
                      value={inputs[item.key] ?? item.default}
                      disabled={running}
                      onChange={(event) =>
                        setInputs((current) => ({
                          ...current,
                          [item.key]: Number(event.target.value),
                        }))
                      }
                    />
                  </div>
                  <span className={styles.rangeBounds}>
                    <i>{item.minimum}</i>
                    <i>{item.maximum}</i>
                  </span>
                </label>
              ))}
            </div>
          ))}
          <div className={styles.actions}>
            <button
              className={styles.runButton}
              disabled={!config || running}
              onClick={() => void runDesign().catch((reason: unknown) => {
                setError(reason instanceof Error ? reason.message : "启动失败");
              })}
            >
              {running ? "正在生成…" : "生成设计"}
            </button>
            {running && (
              <button className={styles.cancelButton} onClick={() => void cancelDesign()}>
                停止
              </button>
            )}
          </div>
        </aside>

        <section className={styles.designArea}>
          <div className={styles.designHeading}>
            <div>
              <span>02 / 方案</span>
              <h2>{result ? "当前最优可行构型" : "等待任务输入"}</h2>
            </div>
            <div className={`${styles.statusBadge} ${result?.feasible ? styles.ok : ""}`}>
              <span />
              {result
                ? result.feasible
                  ? "全部约束满足"
                  : "未找到可行点"
                : running
                  ? STAGE_LABELS[job?.stage ?? "queued"]
                  : "尚未计算"}
            </div>
          </div>

          {error && <div className={styles.errorBanner}>{error}</div>}
          <div className={styles.viewerWrap}>
            <CadViewer
              spec={result?.aircraft_spec ?? null}
              runtimeStatus={runtimeStatus}
            />
          </div>

          <div className={styles.metricGrid}>
            {METRIC_CARDS.map(([key, label, unit]) => (
              <article key={key}>
                <span>{label}</span>
                <strong>{formatNumber(result?.metrics[key])}</strong>
                <small>{unit}</small>
              </article>
            ))}
          </div>

          <div className={styles.bottomGrid}>
            <section className={styles.dataCard}>
              <header>
                <span>约束检查</span>
                <small>{result ? `${result.constraints.filter((item) => item.satisfied).length}/${result.constraints.length}` : "—"}</small>
              </header>
              <div className={styles.constraintTable}>
                {result?.constraints.map((constraint) => (
                  <div key={constraint.name}>
                    <b className={constraint.satisfied ? styles.pass : styles.fail}>
                      {constraint.satisfied ? "✓" : "!"}
                    </b>
                    <span>{constraint.label}</span>
                    <em>{formatNumber(constraint.value, 2)} {constraint.unit}</em>
                    <small>{constraint.relation} {formatNumber(constraint.limit, 2)}</small>
                  </div>
                )) ?? <p className={styles.emptyCopy}>生成后逐项显示约束余量</p>}
              </div>
            </section>

            <section className={styles.dataCard}>
              <header>
                <span>质量收敛</span>
                <small>{result?.convergence.length ?? 0} 轮</small>
              </header>
              <ConvergenceChart points={result?.convergence ?? []} />
            </section>
          </div>
        </section>

        <aside className={styles.resultsPanel}>
          <div className={styles.sectionIntro}>
            <span>03 / 输出</span>
            <h2>设计变量</h2>
            <p>这些量由优化器决定，不是左侧输入的复制。</p>
          </div>
          <div className={styles.variableList}>
            {config?.design_variables.map((variable) => (
              <div key={variable.key}>
                <span>{variable.label}</span>
                <strong>{formatNumber(result?.design[variable.key], 3)}</strong>
                <small>{variable.unit}</small>
              </div>
            ))}
          </div>
          <section className={styles.provenanceCard}>
            <span>公开模型来源</span>
            <h3>{result?.model_provenance.name ?? "NeuralFoil"}</h3>
            <p>
              {result
                ? `v${result.model_provenance.version} · ${result.model_provenance.license}`
                : "论文配套开源气动代理模型"}
            </p>
            {result?.model_provenance.paper_url && (
              <a href={result.model_provenance.paper_url} target="_blank" rel="noreferrer">
                查看论文 ↗
              </a>
            )}
          </section>
          <div className={styles.scopeNote}>
            <strong>概念级结果</strong>
            <p>适合需求探索和方案比较，不替代 CFD、结构校核、稳定性分析或适航验证。</p>
          </div>
        </aside>
      </section>
    </main>
  );
}
