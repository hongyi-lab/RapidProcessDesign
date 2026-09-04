"use client";

import Link from "next/link";
import {
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CadViewer } from "@/components/cad-viewer/CadViewer";
import { ParametricAircraftPreview } from "@/components/rapid-design/geometry";

import { ConvergenceChart, PolarChart } from "./RapidCharts";
import styles from "./rapid-design.module.css";
import {
  OPTIMIZE_METRICS,
  STAGE_LABELS,
  clamp,
  digitsForStep,
  errorFromResponse,
  familyPreset,
  formatNumber,
  geometryMetricRows,
  groupLabel,
  initialConditionValues,
  initialDesignValues,
  isIntegerParameter,
  parameterGroups,
  parseFamiliesResponse,
  preferredInitialFamily,
  toAnalyzePayload,
  type AnalyzeEnvelope,
  type ConditionValues,
  type DesignValues,
  type FamilyManifest,
  type FamilyParameterDefinition,
  type RapidConfig,
  type RapidJob,
  type RapidResult,
  type WorkspaceTab,
} from "./rapidDesignModel";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8900";

const TEACHER_DECISIONS_URL =
  "https://github.com/hongyi-lab/RapidProcessDesign/blob/main/docs/teacher-decisions-optimization-spec-cn.md";

const WORKSPACE_TABS: ReadonlyArray<{
  id: WorkspaceTab;
  label: string;
  description: string;
}> = [
  { id: "analyze", label: "Analyze", description: "整机几何与低阶分析" },
  { id: "mission", label: "Mission Design", description: "优化规范待确认" },
  { id: "legacy", label: "Legacy Conventional Demo", description: "原有任务优化演示" },
];

type AnalysisRecord = {
  data: AnalyzeEnvelope;
  key: string;
};

type BaselineRecord = {
  data: AnalyzeEnvelope;
  familyId: string;
  conditionKey: string;
};

function NumericControl({
  definition,
  value,
  scope,
  disabled = false,
  onChange,
}: {
  definition: FamilyParameterDefinition;
  value: number;
  scope: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const id = `${scope}-${definition.key}`;
  const digits = digitsForStep(definition.step);
  const update = (rawValue: string) => {
    const parsed = Number(rawValue);
    const normalized = isIntegerParameter(definition) ? Math.round(parsed) : parsed;
    if (Number.isFinite(normalized)) {
      onChange(clamp(normalized, definition.minimum, definition.maximum));
    }
  };

  return (
    <div className={styles.numericControl}>
      <div className={styles.controlLabelRow}>
        <label id={`${id}-label`} htmlFor={`${id}-number`}>{definition.label}</label>
        <span>{definition.unit || "—"}</span>
      </div>
      <div className={styles.controlInputs}>
        <input
          id={`${id}-range`}
          type="range"
          min={definition.minimum}
          max={definition.maximum}
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
          min={definition.minimum}
          max={definition.maximum}
          step={definition.step}
          value={value}
          disabled={disabled}
          aria-describedby={`${id}-bounds`}
          onChange={(event) => update(event.target.value)}
        />
      </div>
      <div id={`${id}-bounds`} className={styles.controlBounds}>
        <span>{formatNumber(definition.minimum, digits)}</span>
        <span>{formatNumber(definition.maximum, digits)}</span>
      </div>
    </div>
  );
}

export default function RapidDesignPage() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("analyze");
  const [families, setFamilies] = useState<FamilyManifest[]>([]);
  const [familiesLoading, setFamiliesLoading] = useState(true);
  const [familyError, setFamilyError] = useState<string | null>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [design, setDesign] = useState<DesignValues>({});
  const [condition, setCondition] = useState<ConditionValues>({});
  const [analysisRecord, setAnalysisRecord] = useState<AnalysisRecord | null>(null);
  const [baselineRecord, setBaselineRecord] = useState<BaselineRecord | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const analyzeSequenceRef = useRef(0);

  const [config, setConfig] = useState<RapidConfig | null>(null);
  const [inputs, setInputs] = useState<Record<string, number>>({});
  const [job, setJob] = useState<RapidJob | null>(null);
  const [result, setResult] = useState<RapidResult | null>(null);
  const [legacyError, setLegacyError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const selectedManifest = useMemo(
    () => families.find((manifest) => manifest.family_id === selectedFamilyId) ?? null,
    [families, selectedFamilyId],
  );
  const selectedPreset = useMemo(
    () => selectedManifest ? familyPreset(selectedManifest, selectedPresetId) : null,
    [selectedManifest, selectedPresetId],
  );
  const designGroups = useMemo(
    () => parameterGroups(selectedManifest?.design_parameters ?? []),
    [selectedManifest],
  );
  const conditionGroups = useMemo(
    () => parameterGroups(selectedManifest?.condition_parameters ?? []),
    [selectedManifest],
  );
  const analyzeRequestKey = useMemo(
    () => JSON.stringify({ selectedFamilyId, selectedPresetId, design, condition }),
    [condition, design, selectedFamilyId, selectedPresetId],
  );
  const conditionKey = useMemo(() => JSON.stringify(condition), [condition]);

  function selectFamily(manifest: FamilyManifest) {
    const preset = familyPreset(manifest);
    setSelectedFamilyId(manifest.family_id);
    setSelectedPresetId(preset?.preset_id ?? null);
    setDesign(initialDesignValues(manifest, preset?.preset_id));
    setCondition(initialConditionValues(manifest));
    setAnalysisRecord(null);
    setBaselineRecord(null);
    setAnalyzeError(null);
  }

  useEffect(() => {
    const controller = new AbortController();
    setFamiliesLoading(true);
    fetch(`${API_BASE_URL}/api/rapid-design/families`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "无法读取 aircraft family");
        return parseFamiliesResponse(await response.json());
      })
      .then((payload) => {
        const initialFamily = preferredInitialFamily(payload);
        setFamilies(payload);
        if (initialFamily) selectFamily(initialFamily);
        setFamiliesLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setFamiliesLoading(false);
        setFamilyError(reason instanceof Error ? reason.message : "Family manifest 读取失败");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/rapid-design/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "无法读取 Legacy Demo 配置");
        return (await response.json()) as RapidConfig;
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((item) => [item.key, item.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setLegacyError(reason instanceof Error ? reason.message : "Legacy Demo 配置读取失败");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedManifest || !selectedManifest.capabilities.analyze) {
      setAnalyzeLoading(false);
      return;
    }

    const controller = new AbortController();
    const sequence = ++analyzeSequenceRef.current;
    const requestKey = analyzeRequestKey;
    const requestConditionKey = conditionKey;
    const requestFamilyId = selectedManifest.family_id;
    const payload = toAnalyzePayload(
      selectedManifest.family_id,
      selectedPresetId,
      design,
      condition,
    );
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
          return (await response.json()) as AnalyzeEnvelope;
        })
        .then((data) => {
          if (sequence !== analyzeSequenceRef.current) return;
          if (data.family_id !== requestFamilyId) throw new Error("分析结果与当前 family 不一致");
          setAnalysisRecord({ data, key: requestKey });
          setAnalyzeLoading(false);
          setBaselineRecord((current) => current ?? {
            data,
            familyId: requestFamilyId,
            conditionKey: requestConditionKey,
          });
        })
        .catch((reason: unknown) => {
          if ((reason as { name?: string }).name === "AbortError" || sequence !== analyzeSequenceRef.current) return;
          setAnalyzeLoading(false);
          setAnalyzeError(reason instanceof Error ? reason.message : "分析请求失败");
        });
    }, 220);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [analyzeRequestKey, condition, conditionKey, design, selectedManifest, selectedPresetId]);

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
  const displayedAnalysis = currentAnalysis ?? (analyzeLoading ? analysisRecord?.data ?? null : null);
  const comparableBaseline = baselineRecord?.familyId === selectedFamilyId
    && baselineRecord.conditionKey === conditionKey
    ? baselineRecord.data
    : null;
  const metricRows = geometryMetricRows(currentAnalysis?.geometry_metrics ?? {});
  const baselineMetrics = comparableBaseline?.geometry_metrics ?? {};

  function handleFamilyChange(familyId: string) {
    const manifest = families.find((item) => item.family_id === familyId);
    if (manifest) selectFamily(manifest);
  }

  function handlePresetChange(presetId: string) {
    if (!selectedManifest) return;
    const preset = familyPreset(selectedManifest, presetId);
    setSelectedPresetId(preset?.preset_id ?? null);
    setDesign(initialDesignValues(selectedManifest, preset?.preset_id));
    setAnalyzeError(null);
  }

  function resetCurrentPreset() {
    if (!selectedManifest) return;
    setDesign(initialDesignValues(selectedManifest, selectedPresetId));
    setCondition(initialConditionValues(selectedManifest));
    setAnalyzeError(null);
  }

  function updateValue(
    setter: (update: (current: Record<string, number>) => Record<string, number>) => void,
    definition: FamilyParameterDefinition,
    value: number,
  ) {
    setter((current) => ({
      ...current,
      [definition.key]: clamp(value, definition.minimum, definition.maximum),
    }));
  }

  function setCurrentAsBaseline() {
    if (!currentAnalysis) return;
    setBaselineRecord({
      data: currentAnalysis,
      familyId: currentAnalysis.family_id,
      conditionKey,
    });
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = WORKSPACE_TABS.findIndex((tab) => tab.id === activeTab);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? WORKSPACE_TABS.length - 1
        : (currentIndex + (event.key === "ArrowLeft" ? -1 : 1) + WORKSPACE_TABS.length)
          % WORKSPACE_TABS.length;
    const nextTab = WORKSPACE_TABS[nextIndex].id;
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
        setLegacyError(reason instanceof Error ? reason.message : "结果读取失败");
      });
    }) as EventListener);
    source.addEventListener("failed", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
      const payload = JSON.parse(event.data) as RapidJob;
      setLegacyError(payload.error ?? "设计生成失败");
    }) as EventListener);
    source.addEventListener("cancelled", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
    }) as EventListener);
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) setLegacyError("与 Legacy Demo 服务的连接中断");
    };
  }

  async function runLegacyDesign() {
    setLegacyError(null);
    setResult(null);
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs }),
    });
    if (!response.ok) throw await errorFromResponse(response, "无法启动 Legacy Demo 任务");
    const created = (await response.json()) as RapidJob;
    setJob(created);
    observeJob(created);
  }

  async function cancelLegacyDesign() {
    if (!job) return;
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${job.id}/cancel`, {
      method: "POST",
    });
    if (!response.ok) throw await errorFromResponse(response, "无法停止 Legacy Demo 任务");
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
          <p>Overall Aircraft Design Workbench</p>
        </div>
        <div className={styles.topbarMeta}>
          <span>{selectedManifest?.display_name ?? "Loading families"}</span>
          <Link href="/">返回 AeroSpec</Link>
        </div>
      </header>

      <nav className={styles.tabbar} role="tablist" aria-label="Rapid Design 工作模式">
        {WORKSPACE_TABS.map((tab) => (
          <button
            key={tab.id}
            id={`rapid-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`rapid-panel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={activeTab === tab.id ? styles.activeTab : undefined}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={handleTabKeyDown}
          >
            {tab.label}
            <small>{tab.description}</small>
          </button>
        ))}
      </nav>

      {activeTab === "analyze" && (
        <section
          id="rapid-panel-analyze"
          role="tabpanel"
          aria-labelledby="rapid-tab-analyze"
          className={styles.analyzeWorkspace}
        >
          <aside className={styles.analyzeSidebar} aria-label="Aircraft family 分析输入">
            <div className={styles.sidebarIntro}>
              <span>INPUT / FAMILY MANIFEST</span>
              <h2>构型与工况</h2>
              <p>参数范围和默认值由当前 family manifest 提供；修改后自动重新分析。</p>
            </div>

            <div className={styles.familySelectors}>
              <label htmlFor="rapid-family-select">
                <span>Aircraft family</span>
                <select
                  id="rapid-family-select"
                  value={selectedFamilyId}
                  disabled={familiesLoading || families.length === 0}
                  onChange={(event) => handleFamilyChange(event.target.value)}
                >
                  {families.map((manifest) => (
                    <option key={manifest.family_id} value={manifest.family_id}>
                      {manifest.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="rapid-preset-select">
                <span>Geometry preset</span>
                <select
                  id="rapid-preset-select"
                  value={selectedPresetId ?? ""}
                  disabled={!selectedManifest || selectedManifest.presets.length === 0}
                  onChange={(event) => handlePresetChange(event.target.value)}
                >
                  {selectedManifest?.presets.map((preset) => (
                    <option key={preset.preset_id} value={preset.preset_id}>{preset.label}</option>
                  ))}
                </select>
              </label>
              <p>{selectedPreset?.description ?? selectedManifest?.description ?? "正在读取 family manifest…"}</p>
              {selectedManifest && (
                <div className={styles.capabilityList} aria-label="Family capabilities">
                  <span data-enabled={selectedManifest.capabilities.geometry}>Geometry</span>
                  <span data-enabled={selectedManifest.capabilities.analyze}>Analyze</span>
                  <span data-enabled={selectedManifest.capabilities.optimize}>Optimize</span>
                </div>
              )}
              <button
                type="button"
                className={styles.resetButton}
                disabled={!selectedManifest || analyzeLoading}
                onClick={resetCurrentPreset}
              >
                重置当前 preset
              </button>
            </div>

            {familiesLoading && <div className={styles.sidebarLoading}>正在读取 aircraft families…</div>}
            {familyError && <div className={styles.sidebarError} role="alert">{familyError}</div>}

            {designGroups.map(({ group, definitions }) => (
              <fieldset className={styles.controlGroup} key={group}>
                <legend>{groupLabel(group)}</legend>
                {definitions.map((definition) => (
                  <NumericControl
                    key={definition.key}
                    definition={definition}
                    value={design[definition.key] ?? definition.default}
                    scope={`${selectedFamilyId}-design`}
                    onChange={(value) => updateValue(setDesign, definition, value)}
                  />
                ))}
              </fieldset>
            ))}

            {conditionGroups.map(({ group, definitions }) => (
              <fieldset className={styles.controlGroup} key={group}>
                <legend>{groupLabel(group)}</legend>
                {definitions.map((definition) => (
                  <NumericControl
                    key={definition.key}
                    definition={definition}
                    value={condition[definition.key] ?? definition.default}
                    scope={`${selectedFamilyId}-condition`}
                    onChange={(value) => updateValue(setCondition, definition, value)}
                  />
                ))}
              </fieldset>
            ))}
          </aside>

          <div className={styles.analysisMain}>
            <section className={styles.previewPanel}>
              <header className={styles.panelHeader}>
                <div>
                  <span>CANONICAL GEOMETRY STATE</span>
                  <h2>{selectedManifest?.display_name ?? "参数化整机构型"}</h2>
                </div>
                <div className={styles.previewActions}>
                  <div className={styles.legend} aria-label="构型图例">
                    <span><i className={styles.currentSwatch} />Current</span>
                    <span><i className={styles.baselineSwatch} />Baseline</span>
                  </div>
                  <button
                    type="button"
                    className={styles.baselineButton}
                    disabled={analyzeLoading || !currentAnalysis}
                    onClick={setCurrentAsBaseline}
                  >
                    设为 Baseline
                  </button>
                </div>
              </header>
              <ParametricAircraftPreview
                geometry={displayedAnalysis?.geometry_state ?? null}
                baselineGeometry={baselineRecord?.familyId === selectedFamilyId
                  ? baselineRecord.data.geometry_state
                  : null}
                className={styles.aircraftPreview}
              />
            </section>

            <div className={styles.analysisStatus} aria-live="polite">
              <span className={analyzeError ? styles.statusError : analyzeLoading ? styles.statusWorking : styles.statusReady} />
              {familiesLoading
                ? "正在载入 family manifest…"
                : analyzeLoading
                  ? "正在更新几何与分析…"
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
              {metricRows.length > 0 ? (
                <div className={styles.geometryMetrics}>
                  {metricRows.map((metric) => (
                    <article key={metric.key}>
                      <span>{metric.label}</span>
                      <strong>{formatNumber(metric.value, metric.digits)}</strong>
                      <small>
                        {metric.unit || "—"}
                        {Number.isFinite(baselineMetrics[metric.key])
                          && ` · 基准 ${formatNumber(baselineMetrics[metric.key], metric.digits)}`}
                      </small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.emptyCopy}>等待当前 family 的几何指标。</p>
              )}
            </section>

            <section className={styles.polarPanel} aria-labelledby="polar-title">
              <header className={styles.sectionHeader}>
                <div>
                  <span>AERODYNAMICS</span>
                  <h2 id="polar-title">概念级气动极曲线</h2>
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
                  alpha={currentAnalysis?.analysis.polar.alpha_deg ?? []}
                  values={currentAnalysis?.analysis.polar.cl ?? []}
                  baselineAlpha={comparableBaseline?.analysis.polar.alpha_deg}
                  baselineValues={comparableBaseline?.analysis.polar.cl}
                />
                <PolarChart
                  title="Drag coefficient, CD"
                  unit="CD"
                  alpha={currentAnalysis?.analysis.polar.alpha_deg ?? []}
                  values={currentAnalysis?.analysis.polar.cd ?? []}
                  baselineAlpha={comparableBaseline?.analysis.polar.alpha_deg}
                  baselineValues={comparableBaseline?.analysis.polar.cd}
                />
                <PolarChart
                  title="Lift-to-drag ratio, L/D"
                  unit="L/D"
                  alpha={currentAnalysis?.analysis.polar.alpha_deg ?? []}
                  values={currentAnalysis?.analysis.polar.ld ?? []}
                  baselineAlpha={comparableBaseline?.analysis.polar.alpha_deg}
                  baselineValues={comparableBaseline?.analysis.polar.ld}
                />
              </div>
            </section>

            <section className={styles.modelStrip} aria-label="模型与适用域信息">
              <div>
                <span>Family</span>
                <strong>{selectedManifest?.family_id ?? "—"}</strong>
                <small>v{selectedManifest?.version ?? "—"}</small>
              </div>
              <div>
                <span>Model</span>
                <strong>{currentAnalysis?.provenance.model_id ?? selectedManifest?.analysis.model_id ?? "—"}</strong>
                <small>{currentAnalysis?.provenance.model_version ?? selectedManifest?.analysis.description ?? "—"}</small>
              </div>
              <div>
                <span>Fidelity</span>
                <strong>{currentAnalysis?.fidelity ?? selectedManifest?.analysis.fidelity ?? "—"}</strong>
                <small>仅用于概念级方案比较</small>
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
            </section>

            {(currentAnalysis?.warnings.length ?? 0) > 0 && (
              <section className={styles.warningList} aria-label="分析提示">
                {currentAnalysis?.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </section>
            )}
          </div>
        </section>
      )}

      {activeTab === "mission" && (
        <section
          id="rapid-panel-mission"
          role="tabpanel"
          aria-labelledby="rapid-tab-mission"
          className={styles.missionWorkspace}
        >
          <article className={styles.missionPanel}>
            <span className={styles.pendingCode}>optimization_spec_pending</span>
            <h2>Mission Design 优化规范待老师确认</h2>
            <p>
              新 family-neutral 优化入口已预留，但本轮不会自行决定目标函数、设计变量、约束权重、
              population、iterations 或不确定性方法。
            </p>
            <dl>
              <div><dt>当前 family</dt><dd>{selectedManifest?.display_name ?? "尚未选择"}</dd></div>
              <div><dt>Family 状态</dt><dd>{selectedManifest?.optimization_status ?? "pending_teacher_decision"}</dd></div>
              <div><dt>接口行为</dt><dd>不发起优化任务，不使用临时数值代替工程决策</dd></div>
            </dl>
            <a href={TEACHER_DECISIONS_URL} target="_blank" rel="noreferrer">
              查看老师决策清单 ↗
            </a>
          </article>
        </section>
      )}

      {activeTab === "legacy" && (
        <section
          id="rapid-panel-legacy"
          role="tabpanel"
          aria-labelledby="rapid-tab-legacy"
          className={styles.optimizeWorkspace}
        >
          <aside className={styles.optimizeSidebar} aria-label="Legacy Conventional Demo 输入">
            <div className={styles.sidebarIntro}>
              <span>LEGACY / CONVENTIONAL_V1</span>
              <h2>原有任务与约束</h2>
              <p>这是独立保留的旧常规构型演示，不会优化 Analyze 中当前选择的 family 或 preset。</p>
            </div>
            {!config && !legacyError && <div className={styles.sidebarLoading}>正在读取 Legacy Demo 配置…</div>}
            {(["requirement", "constraint"] as const).map((group) => (
              <fieldset className={styles.controlGroup} key={group}>
                <legend>{group === "requirement" ? "任务需求" : "设计约束"}</legend>
                {groupedInputs[group].map((item) => (
                  <NumericControl
                    key={item.key}
                    definition={{ ...item, group }}
                    value={inputs[item.key] ?? item.default}
                    scope={`legacy-${group}`}
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
                onClick={() => void runLegacyDesign().catch((reason: unknown) => {
                  setLegacyError(reason instanceof Error ? reason.message : "启动失败");
                })}
              >
                {running ? "Legacy Demo 运行中…" : "运行 Legacy Demo"}
              </button>
              {running && (
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={() => void cancelLegacyDesign().catch((reason: unknown) => {
                    setLegacyError(reason instanceof Error ? reason.message : "停止失败");
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
                <span>LEGACY CONVENTIONAL RESULT</span>
                <h2>{result ? "旧流程最优可行构型" : "原有常规固定翼演示"}</h2>
              </div>
              <div className={`${styles.statusBadge} ${result?.feasible ? styles.statusPass : ""}`} aria-live="polite">
                <i />
                {result
                  ? result.feasible ? "全部约束满足" : "未找到可行点"
                  : running ? STAGE_LABELS[job?.stage ?? "queued"] ?? job?.stage
                    : job?.status === "cancelled" ? "任务已停止" : "尚未计算"}
              </div>
            </header>

            <div className={styles.legacyNotice}>
              此结果来自既有 conventional demo pipeline，与当前 Analyze family 无数据关联。
            </div>
            {legacyError && <div className={styles.errorBanner} role="alert">{legacyError}</div>}
            {running && (
              <div
                className={styles.progressTrack}
                aria-label="Legacy Demo 进度"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round((job?.progress ?? 0) * 100)}
                role="progressbar"
              >
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
                  )) ?? <p className={styles.emptyCopy}>运行后逐项显示旧流程约束余量。</p>}
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

          <aside className={styles.resultSidebar} aria-label="Legacy Demo 设计变量">
            <div className={styles.resultHeading}>
              <span>LEGACY OUTPUT</span>
              <h2>旧设计变量</h2>
              <p>下列数值属于原有常规构型优化器，不代表当前 family 的设计空间。</p>
            </div>
            <div className={styles.variableList}>
              {config?.design_variables.map((variable) => (
                <div key={variable.key}>
                  <span>{variable.label}</span>
                  <strong>{formatNumber(result?.design[variable.key], 3)}</strong>
                  <small>{variable.unit}</small>
                </div>
              )) ?? <p className={styles.emptyCopy}>等待 Legacy Demo 配置。</p>}
            </div>
            <section className={styles.provenancePanel}>
              <span>Legacy 气动模型</span>
              <h3>{result?.model_provenance.name ?? "NeuralFoil"}</h3>
              <p>{result ? `v${result.model_provenance.version} · ${result.model_provenance.license}` : "原有公开代理模型"}</p>
              {result?.model_provenance.paper_url && (
                <a href={result.model_provenance.paper_url} target="_blank" rel="noreferrer">查看论文 ↗</a>
              )}
            </section>
            <div className={styles.scopeNote}>
              <strong>Legacy 概念级结果</strong>
              <p>仅用于回归与演示，不替代 CFD、结构校核、稳定性分析或适航验证。</p>
            </div>
          </aside>
        </section>
      )}
    </main>
  );
}
