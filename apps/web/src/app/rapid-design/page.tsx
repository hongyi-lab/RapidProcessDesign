"use client";

import Link from "next/link";
import {
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  BwbThreePreview,
  DEFAULT_BWB_DESIGN,
  type BwbDesignVariables,
} from "@/components/rapid-design/BwbThreePreview";
import { CadViewer } from "@/components/cad-viewer/CadViewer";

import { ConvergenceChart, PolarChart } from "./RapidCharts";
import styles from "./rapid-design.module.css";
import {
  CONDITION_FIELDS,
  DEFAULT_CONDITION,
  GEOMETRY_METRICS,
  OPTIMIZE_METRICS,
  PLANFORM_FIELDS,
  SECTION_FIELDS,
  STAGE_LABELS,
  clamp,
  conditionFieldBounds,
  designFieldBounds,
  errorFromResponse,
  formatNumber,
  toAnalyzePayload,
  type AnalyzeCondition,
  type AnalyzeResponse,
  type NumericDefinition,
  type RapidConfig,
  type RapidJob,
  type RapidResult,
  type WorkspaceTab,
} from "./rapidDesignModel";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8900";

function NumericControl<Key extends string>({
  definition,
  value,
  minimum = definition.minimum,
  maximum = definition.maximum,
  scope,
  disabled = false,
  onChange,
}: {
  definition: NumericDefinition<Key>;
  value: number;
  minimum?: number;
  maximum?: number;
  scope: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const id = `${scope}-${definition.key}`;
  const update = (rawValue: string) => {
    const parsed = Number(rawValue);
    const normalized = definition.key === "alphaSamples" ? Math.round(parsed) : parsed;
    if (Number.isFinite(normalized)) onChange(clamp(normalized, minimum, maximum));
  };
  return (
    <div className={styles.numericControl}>
      <div className={styles.controlLabelRow}>
        <label id={`${id}-label`} htmlFor={`${id}-number`}>{definition.label}</label>
        <span>{definition.unit}</span>
      </div>
      <div className={styles.controlInputs}>
        <input
          id={`${id}-range`}
          type="range"
          min={minimum}
          max={maximum}
          step={definition.step}
          value={value}
          disabled={disabled}
          aria-labelledby={`${id}-label`}
          aria-describedby={`${id}-bounds`}
          onChange={(event) => update(event.target.value)}
        />
        <input
          id={`${id}-number`}
          type="number"
          min={minimum}
          max={maximum}
          step={definition.step}
          value={value}
          disabled={disabled}
          aria-describedby={`${id}-bounds`}
          onChange={(event) => update(event.target.value)}
        />
      </div>
      <div id={`${id}-bounds`} className={styles.controlBounds}>
        <span>{formatNumber(minimum, definition.digits)}</span>
        <span>{formatNumber(maximum, definition.digits)}</span>
      </div>
    </div>
  );
}

export default function RapidDesignPage() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("analyze");
  const [design, setDesign] = useState<BwbDesignVariables>(() => ({ ...DEFAULT_BWB_DESIGN }));
  const [baselineDesign, setBaselineDesign] = useState<BwbDesignVariables>(() => ({ ...DEFAULT_BWB_DESIGN }));
  const [condition, setCondition] = useState<AnalyzeCondition>(DEFAULT_CONDITION);
  const [analysisRecord, setAnalysisRecord] = useState<{ data: AnalyzeResponse; key: string } | null>(null);
  const [baselineAnalysis, setBaselineAnalysis] = useState<{ data: AnalyzeResponse; conditionKey: string } | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(true);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const analyzeSequenceRef = useRef(0);

  const [config, setConfig] = useState<RapidConfig | null>(null);
  const [inputs, setInputs] = useState<Record<string, number>>({});
  const [job, setJob] = useState<RapidJob | null>(null);
  const [result, setResult] = useState<RapidResult | null>(null);
  const [optimizeError, setOptimizeError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const analyzeRequestKey = useMemo(
    () => JSON.stringify({ design, condition }),
    [condition, design],
  );
  const conditionKey = useMemo(() => JSON.stringify(condition), [condition]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/rapid-design/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "无法读取 Rapid Design 配置");
        return (await response.json()) as RapidConfig;
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((item) => [item.key, item.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setOptimizeError(reason instanceof Error ? reason.message : "配置读取失败");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const sequence = ++analyzeSequenceRef.current;
    const payload = toAnalyzePayload(design, condition);
    const requestKey = analyzeRequestKey;
    const requestConditionKey = conditionKey;
    setAnalyzeLoading(true);
    setAnalyzeError(null);
    const timer = window.setTimeout(() => {
      fetch(`${API_BASE_URL}/api/rapid-design/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) throw await errorFromResponse(response, "分析请求失败");
          return (await response.json()) as AnalyzeResponse;
        })
        .then((data) => {
          if (sequence !== analyzeSequenceRef.current) return;
          setAnalysisRecord({ data, key: requestKey });
          setAnalyzeLoading(false);
          if (JSON.stringify(design) === JSON.stringify(DEFAULT_BWB_DESIGN)) {
            setBaselineAnalysis((current) => current ?? { data, conditionKey: requestConditionKey });
          }
        })
        .catch((reason: unknown) => {
          if ((reason as { name?: string }).name === "AbortError" || sequence !== analyzeSequenceRef.current) return;
          setAnalyzeLoading(false);
          setAnalyzeError(reason instanceof Error ? reason.message : "分析请求失败");
        });
    }, 200);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [analyzeRequestKey, condition, conditionKey, design]);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  const running = job?.status === "queued" || job?.status === "running";
  const groupedInputs = useMemo(() => {
    if (!config) return { requirement: [], constraint: [] };
    return {
      requirement: config.inputs.filter((item) => item.kind === "requirement"),
      constraint: config.inputs.filter((item) => item.kind === "constraint"),
    };
  }, [config]);

  const currentAnalysis = analysisRecord?.key === analyzeRequestKey
    ? analysisRecord.data
    : null;
  const comparableBaseline = baselineAnalysis?.conditionKey === conditionKey
    ? baselineAnalysis.data
    : null;

  function updateDesign(key: keyof BwbDesignVariables, value: number) {
    const definition = [...PLANFORM_FIELDS, ...SECTION_FIELDS].find((field) => field.key === key);
    if (!definition) return;
    setDesign((current) => {
      const bounds = designFieldBounds(definition, current);
      return { ...current, [key]: clamp(value, bounds.minimum, bounds.maximum) };
    });
  }

  function updateCondition(key: keyof AnalyzeCondition, value: number) {
    const definition = CONDITION_FIELDS.find((field) => field.key === key);
    if (!definition) return;
    setCondition((current) => {
      const bounds = conditionFieldBounds(definition, current);
      return { ...current, [key]: clamp(value, bounds.minimum, bounds.maximum) };
    });
  }

  function setCurrentAsBaseline() {
    setBaselineDesign({ ...design });
    if (analysisRecord?.key === analyzeRequestKey) {
      setBaselineAnalysis({ data: analysisRecord.data, conditionKey });
    } else {
      setBaselineAnalysis(null);
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextTab = event.key === "ArrowLeft" || event.key === "Home" ? "analyze" : "optimize";
    setActiveTab(nextTab);
    window.requestAnimationFrame(() => document.getElementById(`rapid-tab-${nextTab}`)?.focus());
  }

  async function loadResult(jobId: string) {
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${jobId}/result`);
    if (!response.ok) throw await errorFromResponse(response, "结果文件尚未生成");
    setResult((await response.json()) as RapidResult);
  }

  function observeJob(created: RapidJob) {
    eventSourceRef.current?.close();
    const source = new EventSource(`${API_BASE_URL}/api/rapid-design/jobs/${created.id}/events`);
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
        setOptimizeError(reason instanceof Error ? reason.message : "结果读取失败");
      });
    }) as EventListener);
    source.addEventListener("failed", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
      const payload = JSON.parse(event.data) as RapidJob;
      setOptimizeError(payload.error ?? "设计生成失败");
    }) as EventListener);
    source.addEventListener("cancelled", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
    }) as EventListener);
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) return;
      setOptimizeError("与计算服务的连接中断");
    };
  }

  async function runDesign() {
    setOptimizeError(null);
    setResult(null);
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs }),
    });
    if (!response.ok) throw await errorFromResponse(response, "无法启动设计任务");
    const created = (await response.json()) as RapidJob;
    setJob(created);
    observeJob(created);
  }

  async function cancelDesign() {
    if (!job) return;
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${job.id}/cancel`, {
      method: "POST",
    });
    if (!response.ok) throw await errorFromResponse(response, "无法停止设计任务");
    setJob((await response.json()) as RapidJob);
  }

  const runtimeStatus = running
    ? {
        status: "running" as const,
        currentStageLabel: STAGE_LABELS[job?.stage ?? "queued"] ?? job?.stage,
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
        <div className={styles.brandMark} aria-hidden="true">RP</div>
        <div className={styles.brandCopy}>
          <h1>Rapid Process Design</h1>
          <p>Blended-wing-body concept workspace</p>
        </div>
        <div className={styles.topbarMeta}>
          <span>bwb_v1</span>
          <Link href="/">返回 AeroSpec</Link>
        </div>
      </header>

      <nav className={styles.tabbar} role="tablist" aria-label="Rapid Design 工作模式">
        {(["analyze", "optimize"] as const).map((tab) => (
          <button
            key={tab}
            id={`rapid-tab-${tab}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            aria-controls={`rapid-panel-${tab}`}
            tabIndex={activeTab === tab ? 0 : -1}
            className={activeTab === tab ? styles.activeTab : undefined}
            onClick={() => setActiveTab(tab)}
            onKeyDown={handleTabKeyDown}
          >
            {tab === "analyze" ? "Analyze" : "Optimize"}
            <small>{tab === "analyze" ? "即时气动分析" : "常规构型任务优化"}</small>
          </button>
        ))}
      </nav>

      {activeTab === "analyze" ? (
        <section
          id="rapid-panel-analyze"
          role="tabpanel"
          aria-labelledby="rapid-tab-analyze"
          className={styles.analyzeWorkspace}
        >
          <aside className={styles.analyzeSidebar} aria-label="BWB 分析输入">
            <div className={styles.sidebarIntro}>
              <span>INPUT / BWB_V1</span>
              <h2>几何与工况</h2>
              <p>修改任一数值后，系统会在 200 ms 内重新计算。数值框可用于精确输入。</p>
            </div>

            <fieldset className={styles.controlGroup}>
              <legend>平面形参数</legend>
              {PLANFORM_FIELDS.map((field) => {
                const bounds = designFieldBounds(field, design);
                return (
                  <NumericControl
                    key={field.key}
                    definition={field}
                    value={design[field.key]}
                    minimum={bounds.minimum}
                    maximum={bounds.maximum}
                    scope="bwb-planform"
                    onChange={(value) => updateDesign(field.key, value)}
                  />
                );
              })}
              <p className={styles.relationshipNote}>弦长顺序锁定为 c2 &gt; c3 &gt; c4。</p>
            </fieldset>

            <fieldset className={styles.controlGroup}>
              <legend>剖面与扭转</legend>
              {SECTION_FIELDS.map((field) => (
                <NumericControl
                  key={field.key}
                  definition={field}
                  value={design[field.key]}
                  scope="bwb-section"
                  onChange={(value) => updateDesign(field.key, value)}
                />
              ))}
            </fieldset>

            <fieldset className={styles.controlGroup}>
              <legend>分析工况</legend>
              {CONDITION_FIELDS.map((field) => {
                const bounds = conditionFieldBounds(field, condition);
                return (
                  <NumericControl
                    key={field.key}
                    definition={field}
                    value={condition[field.key]}
                    minimum={bounds.minimum}
                    maximum={bounds.maximum}
                    scope="bwb-condition"
                    onChange={(value) => updateCondition(field.key, value)}
                  />
                );
              })}
            </fieldset>
          </aside>

          <div className={styles.analysisMain}>
            <section className={styles.previewPanel}>
              <header className={styles.panelHeader}>
                <div>
                  <span>GEOMETRY</span>
                  <h2>BWB 参数化构型</h2>
                </div>
                <div className={styles.previewActions}>
                  <div className={styles.legend} aria-label="构型图例">
                    <span><i className={styles.currentSwatch} />Current</span>
                    <span><i className={styles.baselineSwatch} />Baseline</span>
                  </div>
                  <button
                    type="button"
                    className={styles.baselineButton}
                    disabled={analyzeLoading || analysisRecord?.key !== analyzeRequestKey}
                    onClick={setCurrentAsBaseline}
                  >
                    设为 Baseline
                  </button>
                </div>
              </header>
              <BwbThreePreview
                design={design}
                baselineDesign={baselineDesign}
                className={styles.bwbPreview}
              />
            </section>

            <div className={styles.analysisStatus} aria-live="polite">
              <span className={analyzeLoading ? styles.statusWorking : styles.statusReady} />
              {analyzeLoading
                ? "正在更新分析…"
                : analyzeError
                  ? "分析未完成"
                  : `分析已更新 · ${currentAnalysis?.design_hash.slice(0, 8) ?? "—"}`}
            </div>
            {analyzeError && <div className={styles.errorBanner} role="alert">{analyzeError}</div>}

            <section className={styles.metricsPanel} aria-labelledby="geometry-metrics-title">
              <header className={styles.sectionHeader}>
                <div>
                  <span>GEOMETRY METRICS</span>
                  <h2 id="geometry-metrics-title">派生几何量</h2>
                </div>
                <small>Current / Baseline</small>
              </header>
              <div className={styles.geometryMetrics}>
                {GEOMETRY_METRICS.map(([key, label, unit, digits]) => (
                  <article key={key}>
                    <span>{label}</span>
                    <strong>{formatNumber(currentAnalysis?.geometry[key], digits)}</strong>
                    <small>
                      {unit || "—"}
                      {comparableBaseline && ` · 基准 ${formatNumber(comparableBaseline.geometry[key], digits)}`}
                    </small>
                  </article>
                ))}
              </div>
            </section>

            <section className={styles.polarPanel} aria-labelledby="polar-title">
              <header className={styles.sectionHeader}>
                <div>
                  <span>AERODYNAMICS</span>
                  <h2 id="polar-title">低阶气动极曲线</h2>
                </div>
                <div className={styles.legend} aria-label="曲线图例">
                  <span><i className={styles.currentSwatch} />Current</span>
                  <span><i className={styles.baselineSwatch} />Baseline</span>
                </div>
              </header>
              <div className={styles.chartGrid}>
                <PolarChart
                  title="Lift coefficient, CL"
                  unit="CL"
                  alpha={currentAnalysis?.polar.alpha_deg ?? []}
                  values={currentAnalysis?.polar.cl ?? []}
                  baselineAlpha={comparableBaseline?.polar.alpha_deg}
                  baselineValues={comparableBaseline?.polar.cl}
                />
                <PolarChart
                  title="Drag coefficient, CD"
                  unit="CD"
                  alpha={currentAnalysis?.polar.alpha_deg ?? []}
                  values={currentAnalysis?.polar.cd ?? []}
                  baselineAlpha={comparableBaseline?.polar.alpha_deg}
                  baselineValues={comparableBaseline?.polar.cd}
                />
                <PolarChart
                  title="Lift-to-drag ratio, L/D"
                  unit="L/D"
                  alpha={currentAnalysis?.polar.alpha_deg ?? []}
                  values={currentAnalysis?.polar.ld ?? []}
                  baselineAlpha={comparableBaseline?.polar.alpha_deg}
                  baselineValues={comparableBaseline?.polar.ld}
                />
              </div>
            </section>

            <section className={styles.modelStrip} aria-label="模型与适用域信息">
              <div>
                <span>Model</span>
                <strong>{currentAnalysis?.provenance.model_id ?? "clean-room low-order model"}</strong>
                <small>{currentAnalysis?.provenance.model_version ?? "—"}</small>
              </div>
              <div>
                <span>Fidelity</span>
                <strong>{currentAnalysis?.fidelity ?? "conceptual_low_order"}</strong>
                <small>{currentAnalysis?.provenance.scope ?? "概念级方案比较"}</small>
              </div>
              <div data-domain={currentAnalysis?.domain_status.status ?? "checking"}>
                <span>Domain</span>
                <strong>{currentAnalysis?.domain_status.status ?? "checking"}</strong>
                <small>
                  {currentAnalysis
                    ? `${currentAnalysis.domain_status.checks.filter((check) => check.status === "pass").length}/${currentAnalysis.domain_status.checks.length} checks pass`
                    : "等待分析"}
                </small>
              </div>
              <div>
                <span>Max sampled L/D</span>
                <strong>{formatNumber(currentAnalysis?.summary.max_ld, 2)}</strong>
                <small>@ {formatNumber(currentAnalysis?.summary.alpha_at_max_ld_deg, 1)} deg</small>
              </div>
            </section>

            {(currentAnalysis?.warnings.length ?? 0) > 0 && (
              <section className={styles.warningList} aria-label="分析提示">
                {currentAnalysis?.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </section>
            )}
          </div>
        </section>
      ) : (
        <section
          id="rapid-panel-optimize"
          role="tabpanel"
          aria-labelledby="rapid-tab-optimize"
          className={styles.optimizeWorkspace}
        >
          <aside className={styles.optimizeSidebar} aria-label="优化任务输入">
            <div className={styles.sidebarIntro}>
              <span>INPUT / CONVENTIONAL</span>
              <h2>常规构型任务与约束</h2>
              <p>保留现有固定翼任务优化流程；BWB 优化将在后续版本迁移接入。</p>
            </div>
            {!config && !optimizeError && <div className={styles.sidebarLoading}>正在读取参数…</div>}
            {(["requirement", "constraint"] as const).map((group) => (
              <fieldset className={styles.controlGroup} key={group}>
                <legend>{group === "requirement" ? "任务需求" : "设计约束"}</legend>
                {groupedInputs[group].map((item) => (
                  <NumericControl
                    key={item.key}
                    definition={{ ...item, digits: item.step < 1 ? 1 : 0 }}
                    value={inputs[item.key] ?? item.default}
                    scope={`optimize-${group}`}
                    disabled={running}
                    onChange={(value) => setInputs((current) => ({ ...current, [item.key]: value }))}
                  />
                ))}
              </fieldset>
            ))}
            <div className={styles.optimizeActions}>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={!config || running}
                onClick={() => void runDesign().catch((reason: unknown) => {
                  setOptimizeError(reason instanceof Error ? reason.message : "启动失败");
                })}
              >
                {running ? "正在优化…" : "开始优化"}
              </button>
              {running && (
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={() => void cancelDesign().catch((reason: unknown) => {
                    setOptimizeError(reason instanceof Error ? reason.message : "停止失败");
                  })}
                >
                  停止任务
                </button>
              )}
            </div>
          </aside>

          <div className={styles.optimizeMain}>
            <header className={styles.optimizeHeading}>
              <div>
                <span>CONVENTIONAL DESIGN RESULT</span>
                <h2>{result ? "当前最优可行构型" : "现有常规固定翼概念方案"}</h2>
              </div>
              <div className={`${styles.statusBadge} ${result?.feasible ? styles.statusPass : ""}`} aria-live="polite">
                <i />
                {result
                  ? result.feasible ? "全部约束满足" : "未找到可行点"
                  : running ? STAGE_LABELS[job?.stage ?? "queued"] ?? job?.stage
                    : job?.status === "cancelled" ? "任务已停止" : "尚未计算"}
              </div>
            </header>

            {optimizeError && <div className={styles.errorBanner} role="alert">{optimizeError}</div>}
            {running && (
              <div className={styles.progressTrack} aria-label="优化进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((job?.progress ?? 0) * 100)} role="progressbar">
                <span style={{ width: `${Math.round((job?.progress ?? 0) * 100)}%` }} />
              </div>
            )}

            <div className={styles.viewerWrap}>
              <CadViewer spec={result?.aircraft_spec ?? null} runtimeStatus={runtimeStatus} />
            </div>

            <div className={styles.optimizeMetricGrid}>
              {OPTIMIZE_METRICS.map(([key, label, unit]) => (
                <article key={key}>
                  <span>{label}</span>
                  <strong>{formatNumber(result?.metrics[key])}</strong>
                  <small>{unit || "—"}</small>
                </article>
              ))}
            </div>

            <div className={styles.optimizeBottomGrid}>
              <section className={styles.dataPanel}>
                <header>
                  <h3>约束检查</h3>
                  <small>{result ? `${result.constraints.filter((item) => item.satisfied).length}/${result.constraints.length}` : "—"}</small>
                </header>
                <div className={styles.constraintTable}>
                  {result?.constraints.map((constraint) => (
                    <div key={constraint.name}>
                      <b className={constraint.satisfied ? styles.pass : styles.fail}>{constraint.satisfied ? "✓" : "!"}</b>
                      <span>{constraint.label}</span>
                      <em>{formatNumber(constraint.value, 2)} {constraint.unit}</em>
                      <small>{constraint.relation} {formatNumber(constraint.limit, 2)}</small>
                    </div>
                  )) ?? <p className={styles.emptyCopy}>优化完成后逐项显示约束余量。</p>}
                </div>
              </section>
              <section className={styles.dataPanel}>
                <header>
                  <h3>质量收敛</h3>
                  <small>{result?.convergence.length ?? 0} 轮</small>
                </header>
                <ConvergenceChart points={result?.convergence ?? []} />
              </section>
            </div>
          </div>

          <aside className={styles.resultSidebar} aria-label="优化设计变量">
            <div className={styles.resultHeading}>
              <span>OUTPUT</span>
              <h2>设计变量</h2>
              <p>下列数值由现有常规构型优化器决定，并非 BWB 几何参数。</p>
            </div>
            <div className={styles.variableList}>
              {config?.design_variables.map((variable) => (
                <div key={variable.key}>
                  <span>{variable.label}</span>
                  <strong>{formatNumber(result?.design[variable.key], 3)}</strong>
                  <small>{variable.unit}</small>
                </div>
              )) ?? <p className={styles.emptyCopy}>等待配置。</p>}
            </div>
            <section className={styles.provenancePanel}>
              <span>气动模型</span>
              <h3>{result?.model_provenance.name ?? "NeuralFoil"}</h3>
              <p>{result ? `v${result.model_provenance.version} · ${result.model_provenance.license}` : "公开代理模型"}</p>
              {result?.model_provenance.paper_url && (
                <a href={result.model_provenance.paper_url} target="_blank" rel="noreferrer">查看论文 ↗</a>
              )}
            </section>
            <div className={styles.scopeNote}>
              <strong>概念级结果</strong>
              <p>用于需求探索与方案比较，不替代 CFD、结构校核、稳定性分析或适航验证。</p>
            </div>
          </aside>
        </section>
      )}
    </main>
  );
}
