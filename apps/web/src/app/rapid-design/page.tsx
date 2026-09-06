"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CadViewer } from "@/components/cad-viewer/CadViewer";
import {
  ParametricAircraftPreview,
  geometryNominalSize,
  modelScaleForMode,
  type GeometryScaleMode,
  type GeometryState,
} from "@/components/rapid-design/geometry";

import { ConvergenceChart, PolarChart } from "./RapidCharts";
import { GeometryValidationPanel } from "./GeometryValidationPanel";
import { MissionDemoPanel } from "./MissionDemoPanel";
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
  type DemoAnalyzeHandoff,
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
  "https://github.com/hongyi-lab/RapidProcessDesign/blob/codex/round8-simple-design-flow/docs/teacher-decisions-optimization-spec-cn.md";

const FAMILY_NAMES: Record<string, string> = {
  conventional_v2: "Conventional aircraft",
  bwb_v1: "Blended wing body",
};

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
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("mission");
  const [studiesOpen, setStudiesOpen] = useState(false);
  const [families, setFamilies] = useState<FamilyManifest[]>([]);
  const [familiesLoading, setFamiliesLoading] = useState(true);
  const [familyError, setFamilyError] = useState<string | null>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [design, setDesign] = useState<DesignValues>({});
  const [condition, setCondition] = useState<ConditionValues>({});
  const [analysisRecord, setAnalysisRecord] = useState<AnalysisRecord | null>(null);
  const [baselineRecord, setBaselineRecord] = useState<BaselineRecord | null>(null);
  const [primaryScaleMode, setPrimaryScaleMode] = useState<GeometryScaleMode>("auto");
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [analyzeRunNonce, setAnalyzeRunNonce] = useState(0);
  const analyzeSequenceRef = useRef(0);
  const advancedMenuRef = useRef<HTMLDetailsElement>(null);
  const [missionPresetId, setMissionPresetId] = useState<string | null>(null);
  const [missionBaselineGeometry, setMissionBaselineGeometry] = useState<GeometryState | null>(null);

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
  const missionManifest = useMemo(
    () => families.find((manifest) => manifest.family_id === "conventional_v2") ?? null,
    [families],
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
    setPrimaryScaleMode("auto");
  }

  useEffect(() => {
    const controller = new AbortController();
    setFamiliesLoading(true);
    fetch(`${API_BASE_URL}/api/rapid-design/families`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "Could not load aircraft configurations");
        return parseFamiliesResponse(await response.json());
      })
      .then((payload) => {
        const initialFamily = preferredInitialFamily(payload);
        const demoFamily = payload.find((manifest) => manifest.family_id === "conventional_v2") ?? null;
        setFamilies(payload);
        if (initialFamily) selectFamily(initialFamily);
        setMissionPresetId(
          demoFamily?.default_preset_id ?? demoFamily?.presets[0]?.preset_id ?? null,
        );
        setFamiliesLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setFamiliesLoading(false);
        setFamilyError(reason instanceof Error ? reason.message : "Could not load aircraft settings");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (activeTab !== "legacy") return;
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/rapid-design/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "Could not load the legacy demo");
        return (await response.json()) as RapidConfig;
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((item) => [item.key, item.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setLegacyError(reason instanceof Error ? reason.message : "Could not load the legacy demo settings");
        }
      });
    return () => controller.abort();
  }, [activeTab]);

  useEffect(() => {
    if (!missionManifest || !missionPresetId) {
      setMissionBaselineGeometry(null);
      return;
    }
    setMissionBaselineGeometry(null);
    const controller = new AbortController();
    const payload = toAnalyzePayload(
      missionManifest.family_id,
      missionPresetId,
      initialDesignValues(missionManifest, missionPresetId),
      initialConditionValues(missionManifest),
    );
    fetch(`${API_BASE_URL}/api/rapid-design/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "Could not load the starting aircraft");
        return (await response.json()) as AnalyzeEnvelope;
      })
      .then((data) => {
        if (data.family_id === missionManifest.family_id && data.preset_id === missionPresetId) {
          setMissionBaselineGeometry(data.geometry_state);
        }
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setMissionBaselineGeometry(null);
        }
      });
    return () => controller.abort();
  }, [missionManifest, missionPresetId]);

  useEffect(() => {
    if (activeTab !== "analyze" || !selectedManifest || !selectedManifest.capabilities.analyze) {
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
          if (!response.ok) throw await errorFromResponse(response, "Analysis failed. Please try again.");
          return (await response.json()) as AnalyzeEnvelope;
        })
        .then((data) => {
          if (sequence !== analyzeSequenceRef.current) return;
          if (data.family_id !== requestFamilyId) throw new Error("Analysis does not match the selected configuration");
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
          setAnalyzeError(reason instanceof Error ? reason.message : "Analysis failed. Please try again.");
        });
    }, 220);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [activeTab, analyzeRequestKey, analyzeRunNonce, condition, conditionKey, design, selectedManifest, selectedPresetId]);

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
  const displayedBaselineGeometry = baselineRecord?.familyId === selectedFamilyId
    ? baselineRecord.data.geometry_state
    : null;
  const metricRows = geometryMetricRows(currentAnalysis?.geometry_metrics ?? {});
  const baselineMetrics = comparableBaseline?.geometry_metrics ?? {};
  const primaryReferenceSize = useMemo(() => {
    if (primaryScaleMode === "auto") return undefined;
    const states = [
      displayedAnalysis?.geometry_state,
      displayedBaselineGeometry,
    ].filter((state): state is NonNullable<typeof state> => Boolean(state));
    if (states.length === 0) return undefined;
    return Math.max(...states.map((state) => (
      geometryNominalSize(state) * modelScaleForMode(state, primaryScaleMode)
    )));
  }, [displayedAnalysis, displayedBaselineGeometry, primaryScaleMode]);

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

  function handleMissionPresetChange(presetId: string) {
    if (!missionManifest?.presets.some((preset) => preset.preset_id === presetId)) return;
    setMissionPresetId(presetId);
  }

  function resetCurrentPreset() {
    if (!selectedManifest) return;
    setDesign(initialDesignValues(selectedManifest, selectedPresetId));
    setCondition(initialConditionValues(selectedManifest));
    setAnalyzeError(null);
  }

  function inspectDemoCandidate(handoff: DemoAnalyzeHandoff) {
    const manifest = families.find((item) => item.family_id === handoff.familyId);
    if (!manifest || !manifest.capabilities.analyze) {
      throw new Error(`Analysis is unavailable for configuration ${handoff.familyId}`);
    }
    if (!manifest.presets.some((preset) => preset.preset_id === handoff.presetId)) {
      throw new Error(`Analysis is unavailable for preset ${handoff.presetId}`);
    }
    setSelectedFamilyId(handoff.familyId);
    setSelectedPresetId(handoff.presetId);
    setDesign({ ...handoff.design });
    setCondition({ ...handoff.condition });
    setAnalysisRecord(null);
    setBaselineRecord(null);
    setAnalyzeError(null);
    setPrimaryScaleMode("auto");
    setAnalyzeRunNonce((nonce) => nonce + 1);
    setActiveTab("analyze");
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

  async function loadResult(jobId: string) {
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${jobId}/result`);
    if (!response.ok) throw await errorFromResponse(response, "Results are not ready yet");
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
        setLegacyError(reason instanceof Error ? reason.message : "Could not load results");
      });
    }) as EventListener);
    source.addEventListener("failed", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
      const payload = JSON.parse(event.data) as RapidJob;
      setLegacyError(payload.error ?? "Aircraft generation failed");
    }) as EventListener);
    source.addEventListener("cancelled", ((event: MessageEvent<string>) => {
      update(event);
      source.close();
    }) as EventListener);
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) setLegacyError("Connection to the legacy demo was interrupted");
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
    if (!response.ok) throw await errorFromResponse(response, "Could not start the legacy demo");
    const created = (await response.json()) as RapidJob;
    setJob(created);
    observeJob(created);
  }

  async function cancelLegacyDesign() {
    if (!job) return;
    const response = await fetch(`${API_BASE_URL}/api/rapid-design/jobs/${job.id}/cancel`, {
      method: "POST",
    });
    if (!response.ok) throw await errorFromResponse(response, "Could not stop the legacy demo");
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
          <p>Aircraft concept studio</p>
        </div>
        <div className={styles.topbarMeta}>
          <span>
            {activeTab === "mission"
              ? "Design"
              : activeTab === "analyze" ? "Analysis" : "Legacy demo"}
          </span>
          <span>Local workspace</span>
        </div>
      </header>

      <nav className={styles.simpleNav} aria-label="Main navigation">
        <button
          type="button"
          className={styles.designHomeButton}
          data-active={activeTab === "mission"}
          aria-current={activeTab === "mission" ? "page" : undefined}
          onClick={() => setActiveTab("mission")}
        >
          <strong>Design</strong>
        </button>
        <button type="button" className={styles.designHomeButton}
          data-active={activeTab === "analyze"}
          aria-current={activeTab === "analyze" ? "page" : undefined}
          onClick={() => setActiveTab("analyze")}>Analyze</button>
        <details ref={advancedMenuRef} className={styles.advancedMenu}>
          <summary>More tools</summary>
          <div>
            <Link href="/aerospec"><strong>AI workspace</strong><small>Requires a model connection</small></Link>
            <button
              type="button"
              data-active={activeTab === "legacy"}
              onClick={() => {
                setActiveTab("legacy");
                if (advancedMenuRef.current) advancedMenuRef.current.open = false;
              }}
            >
              <strong>Legacy demo</strong>
              <small>Original optimization workflow</small>
            </button>
          </div>
        </details>
      </nav>

      {activeTab === "analyze" && (
        <section
          id="rapid-panel-analyze"
          aria-label="Aircraft analysis"
          className={styles.analyzeWorkspace}
        >
          <aside className={styles.analyzeSidebar} aria-label="Aircraft analysis inputs">
            <button type="button" className={styles.backToDesign} onClick={() => setActiveTab("mission")}>
              Back to design
            </button>
            <div className={styles.sidebarIntro}>
              <span>INPUT / FAMILY MANIFEST</span>
              <h2>Geometry & flight conditions</h2>
              <p>Adjust a parameter to update the model and analysis.</p>
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
                      {FAMILY_NAMES[manifest.family_id] ?? manifest.display_name}
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
              <p>{selectedFamilyId === "bwb_v1"
                ? "A continuous body and wing. Adjust chord, sweep and span to explore the shape."
                : selectedPreset?.description ?? selectedManifest?.description ?? "Loading aircraft settings…"}</p>
              <button
                type="button"
                className={styles.resetButton}
                disabled={!selectedManifest || analyzeLoading}
                onClick={resetCurrentPreset}
              >
                Reset parameters
              </button>
            </div>

            {familiesLoading && <div className={styles.sidebarLoading}>Loading configurations…</div>}
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
                  <h2>{FAMILY_NAMES[selectedFamilyId] ?? selectedManifest?.display_name ?? "Aircraft geometry"}</h2>
                </div>
                <div className={styles.previewActions}>
                  <div className={styles.legend} aria-label="Geometry legend">
                    <span><i className={styles.currentSwatch} />Current</span>
                    <span><i className={styles.baselineSwatch} />Baseline</span>
                  </div>
                  <button
                    type="button"
                    className={styles.baselineButton}
                    disabled={analyzeLoading || !currentAnalysis}
                    onClick={setCurrentAsBaseline}
                  >
                    Save baseline
                  </button>
                </div>
              </header>
              <ParametricAircraftPreview
                geometry={displayedAnalysis?.geometry_state ?? null}
                baselineGeometry={displayedBaselineGeometry}
                className={styles.aircraftPreview}
                scaleMode={primaryScaleMode}
                sharedReferenceSize={primaryReferenceSize}
                onScaleModeChange={setPrimaryScaleMode}
              />
            </section>

            {selectedManifest?.family_id === "conventional_v2" ? (
              <details className={styles.teacherDetails} onToggle={(event) => setStudiesOpen(event.currentTarget.open)}>
                <summary>Configuration comparison & parameter studies</summary>
              {studiesOpen && <GeometryValidationPanel
                apiBaseUrl={API_BASE_URL}
                manifest={selectedManifest}
                selectedPresetId={selectedPresetId}
              />}
              </details>
            ) : null}

            <div className={styles.analysisStatus} aria-live="polite">
              <span className={analyzeError ? styles.statusError : analyzeLoading ? styles.statusWorking : styles.statusReady} />
              {familiesLoading
                ? "Loading configurations…"
                : analyzeLoading
                  ? "Updating geometry and analysis…"
                  : analyzeError
                    ? "Analysis incomplete"
                    : `Analysis updated · ${currentAnalysis?.design_hash.slice(0, 8) ?? "—"}`}
            </div>
            {analyzeError && <div className={styles.errorBanner} role="alert">{analyzeError}</div>}

            <section className={styles.metricsPanel} aria-labelledby="geometry-metrics-title">
              <header className={styles.sectionHeader}>
                <div>
                  <span>GEOMETRY METRICS</span>
                  <h2 id="geometry-metrics-title">Dimensions</h2>
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
                          && ` · Baseline ${formatNumber(baselineMetrics[metric.key], metric.digits)}`}
                      </small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.emptyCopy}>Dimensions will appear after analysis.</p>
              )}
            </section>

            <section className={styles.polarPanel} aria-labelledby="polar-title">
              <header className={styles.sectionHeader}>
                <div>
                  <span>AERODYNAMICS</span>
                  <h2 id="polar-title">Aerodynamic estimates</h2>
                </div>
                <div className={styles.legend} aria-label="Chart legend">
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

            <details className={styles.teacherDetails}>
              <summary>Analysis model & limitations</summary>
            <section className={styles.modelStrip} aria-label="Model details">
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
                <small>Concept estimates only</small>
              </div>
              <div data-domain={currentAnalysis?.domain_status.status ?? "checking"}>
                <span>Domain</span>
                <strong>{currentAnalysis?.domain_status.status ?? "checking"}</strong>
                <small>
                  {currentAnalysis
                    ? `${currentAnalysis.domain_status.checks.filter((check) => check.status === "pass").length}/${currentAnalysis.domain_status.checks.length} checks pass`
                    : "Waiting for analysis"}
                </small>
              </div>
            </section>
            </details>

            {(currentAnalysis?.warnings.length ?? 0) > 0 && (
              <section className={styles.warningList} aria-label="Analysis notes">
                {currentAnalysis?.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </section>
            )}
          </div>
        </section>
      )}

      <section
        id="rapid-panel-mission"
        aria-label="Aircraft design"
        className={styles.missionWorkspace}
        hidden={activeTab !== "mission"}
        aria-hidden={activeTab !== "mission"}
      >
          {familyError && (
            <div className={styles.missionStartupError} role="alert">
              <div>
                <strong>Could not load aircraft settings</strong>
                <p>{familyError}</p>
              </div>
              <button type="button" onClick={() => window.location.reload()}>
                Reload
              </button>
            </div>
          )}
          <MissionDemoPanel
            apiBaseUrl={API_BASE_URL}
            manifest={missionManifest}
            selectedPresetId={missionPresetId}
            onPresetChange={handleMissionPresetChange}
            baselineGeometry={missionBaselineGeometry}
            onAnalyzeCandidate={inspectDemoCandidate}
          />
          <details className={styles.teacherDetails}>
            <summary>
              <span>About this demo</span>
              <small>Model scope and limitations</small>
            </summary>
            <article className={styles.missionPanel}>
              <span className={styles.pendingCode}>optimization_spec_pending</span>
              <h2>A concept exploration tool</h2>
              <p>
                This demo uses repeatable search settings and preliminary models. Formal optimization objectives, constraints and validation criteria are still under review.
              </p>
              <dl>
                <div><dt>Demo search</dt><dd>Repeatable runs with saved results</dd></div>
                <div><dt>Formal optimization</dt><dd>{missionManifest?.optimization_status ?? "pending_teacher_decision"}</dd></div>
                <div><dt>Engineering validation</dt><dd>Not performed; concepts are preliminary</dd></div>
              </dl>
              <a href={TEACHER_DECISIONS_URL} target="_blank" rel="noreferrer">
                Read the model specification ↗
              </a>
            </article>
          </details>
      </section>

      {activeTab === "legacy" && (
        <section
          id="rapid-panel-legacy"
          aria-label="Legacy demo"
          className={styles.optimizeWorkspace}
        >
          <aside className={styles.optimizeSidebar} aria-label="Legacy demo inputs">
            <button type="button" className={styles.backToDesign} onClick={() => setActiveTab("mission")}>
              Back to design
            </button>
            <div className={styles.sidebarIntro}>
              <span>LEGACY / CONVENTIONAL_V1</span>
              <h2>Mission & constraints</h2>
              <p>The original conventional-aircraft optimizer runs independently of the Design and Analyze workspaces.</p>
            </div>
            {!config && !legacyError && <div className={styles.sidebarLoading}>Loading legacy settings…</div>}
            {(["requirement", "constraint"] as const).map((group) => (
              <fieldset className={styles.controlGroup} key={group}>
                <legend>{group === "requirement" ? "Mission requirements" : "Design constraints"}</legend>
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
                  setLegacyError(reason instanceof Error ? reason.message : "Could not start");
                })}
              >
                {running ? "Running legacy demo…" : "Run legacy demo"}
              </button>
              {running && (
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={() => void cancelLegacyDesign().catch((reason: unknown) => {
                    setLegacyError(reason instanceof Error ? reason.message : "Could not stop");
                  })}
                >
                  Stop run
                </button>
              )}
            </div>
          </aside>

          <div className={styles.optimizeMain}>
            <header className={styles.optimizeHeading}>
              <div>
                <span>LEGACY CONVENTIONAL RESULT</span>
                <h2>{result ? "Best feasible legacy concept" : "Conventional aircraft demo"}</h2>
              </div>
              <div className={`${styles.statusBadge} ${result?.feasible ? styles.statusPass : ""}`} aria-live="polite">
                <i />
                {result
                  ? result.feasible ? "Requirements met" : "No feasible design found"
                  : running ? STAGE_LABELS[job?.stage ?? "queued"] ?? job?.stage
                    : job?.status === "cancelled" ? "Run stopped" : "Ready to run"}
              </div>
            </header>

            <div className={styles.legacyNotice}>
              Results belong to the original optimizer and are independent of the current analysis.
            </div>
            {legacyError && <div className={styles.errorBanner} role="alert">{legacyError}</div>}
            {running && (
              <div
                className={styles.progressTrack}
                aria-label="Legacy demo progress"
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
                  <h3>Requirements</h3>
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
                  )) ?? <p className={styles.emptyCopy}>Constraint margins will appear after a run.</p>}
                </div>
              </section>
              <section className={styles.dataPanel}>
                <header>
                  <h3>Mass convergence</h3>
                  <small>{result?.convergence.length ?? 0} iterations</small>
                </header>
                <ConvergenceChart points={result?.convergence ?? []} />
              </section>
            </div>
          </div>

          <aside className={styles.resultSidebar} aria-label="Legacy design variables">
            <div className={styles.resultHeading}>
              <span>LEGACY OUTPUT</span>
              <h2>Design variables</h2>
              <p>Variables from the original conventional-aircraft optimizer.</p>
            </div>
            <div className={styles.variableList}>
              {config?.design_variables.map((variable) => (
                <div key={variable.key}>
                  <span>{variable.label}</span>
                  <strong>{formatNumber(result?.design[variable.key], 3)}</strong>
                  <small>{variable.unit}</small>
                </div>
              )) ?? <p className={styles.emptyCopy}>Waiting for legacy settings.</p>}
            </div>
            <section className={styles.provenancePanel}>
              <span>Aerodynamic model</span>
              <h3>{result?.model_provenance.name ?? "NeuralFoil"}</h3>
              <p>{result ? `v${result.model_provenance.version} · ${result.model_provenance.license}` : "Public surrogate model"}</p>
              {result?.model_provenance.paper_url && (
                <a href={result.model_provenance.paper_url} target="_blank" rel="noreferrer">Read paper ↗</a>
              )}
            </section>
            <div className={styles.scopeNote}>
              <strong>Preliminary estimates</strong>
              <p>For concept exploration. CFD, structural and stability validation are not included.</p>
            </div>
          </aside>
        </section>
      )}
    </main>
  );
}
