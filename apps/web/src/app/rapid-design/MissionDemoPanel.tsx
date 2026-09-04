"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ParametricAircraftPreview,
  type GeometryView,
} from "@/components/rapid-design/geometry";

import styles from "./MissionDemoPanel.module.css";
import {
  STAGE_LABELS,
  clamp,
  demoAnalyzeHandoff,
  demoInputsMismatch,
  demoRunUpdateMatches,
  demoSelectionMismatch,
  demoSharedReferenceSize,
  digitsForStep,
  errorFromResponse,
  formatNumber,
  parseDemoConfig,
  parseDemoJob,
  parseDemoSearchResult,
  topDemoCandidates,
  type DemoAnalyzeHandoff,
  type DemoCandidate,
  type DemoConstraint,
  type DemoJob,
  type DemoMetricCoverage,
  type DemoProfileConfig,
  type DemoSearchResult,
  type FamilyManifest,
  type InputDefinition,
} from "./rapidDesignModel";

const DEMO_FAMILY_ID = "conventional_v2";
const RESULT_RETRY_DELAYS_MS = [350, 650, 1000, 1500];
const POLL_INTERVAL_MS = 850;

const METRIC_LABELS: Record<string, { label: string; unit: string; digits: number }> = {
  takeoff_mass_kg: { label: "起飞质量", unit: "kg", digits: 1 },
  achieved_range_km: { label: "预计航程", unit: "km", digits: 0 },
  max_lift_to_drag: { label: "最大 L/D", unit: "", digits: 2 },
  fuel_mass_kg: { label: "燃油质量", unit: "kg", digits: 1 },
};

const VIEW_OPTIONS: ReadonlyArray<{ id: GeometryView; label: string }> = [
  { id: "3d", label: "3D" },
  { id: "top", label: "顶视" },
  { id: "side", label: "侧视" },
  { id: "front", label: "前视" },
];

type TransportState = "idle" | "sse" | "polling";

type MissionDemoPanelProps = {
  apiBaseUrl: string;
  manifest: FamilyManifest | null;
  selectedPresetId: string | null;
  onAnalyzeCandidate: (handoff: DemoAnalyzeHandoff) => void;
};

function DemoNumericControl({
  definition,
  value,
  disabled,
  onChange,
}: {
  definition: InputDefinition;
  value: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const digits = digitsForStep(definition.step);
  const id = `mission-demo-${definition.key}`;
  const update = (raw: string) => {
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) {
      onChange(clamp(parsed, definition.minimum, definition.maximum));
    }
  };

  return (
    <div className={styles.inputControl}>
      <div className={styles.inputLabel}>
        <label id={`${id}-label`} htmlFor={`${id}-number`}>{definition.label}</label>
        <span>{definition.unit || "—"}</span>
      </div>
      <div className={styles.inputFields}>
        <input
          id={`${id}-range`}
          type="range"
          min={definition.minimum}
          max={definition.maximum}
          step={definition.step}
          value={value}
          disabled={disabled}
          aria-labelledby={`${id}-label`}
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
          aria-labelledby={`${id}-label`}
          onChange={(event) => update(event.target.value)}
        />
      </div>
      <div className={styles.inputBounds}>
        <span>{formatNumber(definition.minimum, digits)}</span>
        <span>{formatNumber(definition.maximum, digits)}</span>
      </div>
    </div>
  );
}

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replaceAll("_", " ");
}

function profileNumber(config: DemoProfileConfig | null, key: string): string {
  const value = config?.optimizer[key];
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "—";
}

function compactId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-5)}` : value;
}

function constraintTitle(constraint: DemoConstraint, index: number): string {
  return constraint.label ?? constraint.name ?? constraint.key ?? `Constraint ${index + 1}`;
}

function constraintValue(constraint: DemoConstraint): string {
  if (typeof constraint.margin === "number") {
    return `margin ${formatNumber(constraint.margin, 2)} ${constraint.unit ?? ""}`.trim();
  }
  if (typeof constraint.violation === "number") {
    return `violation ${formatNumber(constraint.violation, 2)} ${constraint.unit ?? ""}`.trim();
  }
  if (typeof constraint.value === "number") {
    return `${formatNumber(constraint.value, 2)} ${constraint.unit ?? ""}`.trim();
  }
  return constraint.satisfied === false ? "未满足" : "已检查";
}

function coverageCounts(coverage: DemoMetricCoverage | null) {
  return (["connected", "partial", "not_connected"] as const).map((status) => ({
    status,
    count: coverage?.metrics.filter((metric) => metric.status === status).length ?? 0,
  }));
}

function CandidateCard({
  candidate,
  view,
  sharedReferenceSize,
  anyFeasible,
  onAnalyze,
}: {
  candidate: DemoCandidate;
  view: GeometryView;
  sharedReferenceSize: number;
  anyFeasible: boolean;
  onAnalyze: (candidate: DemoCandidate) => void;
}) {
  const statusLabel = candidate.feasible
    ? "可行 Demo 候选"
    : !anyFeasible && candidate.rank === 1
      ? "最小违约候选"
      : "约束未满足";

  return (
    <article className={styles.candidateCard} data-feasible={candidate.feasible}>
      <header className={styles.candidateHeader}>
        <div>
          <span className={styles.rank}>#{candidate.rank}</span>
          <h4>候选 {compactId(candidate.candidate_id)}</h4>
        </div>
        <span className={styles.feasibility}>{statusLabel}</span>
      </header>

      <div className={styles.previewFrame}>
        <ParametricAircraftPreview
          geometry={candidate.geometry_state}
          view={view}
          scaleMode="world"
          sharedReferenceSize={sharedReferenceSize}
          interactive={false}
          showViewControls={false}
          showScaleControls={false}
        />
        <span className={styles.scaleStamp}>共享米制尺度 · 只读</span>
      </div>

      <dl className={styles.metricGrid}>
        {Object.entries(METRIC_LABELS).map(([key, presentation]) => (
          <div key={key}>
            <dt>{presentation.label}</dt>
            <dd>
              {formatNumber(candidate.metrics[key], presentation.digits)}
              {presentation.unit && <small>{presentation.unit}</small>}
            </dd>
          </div>
        ))}
      </dl>

      <section className={styles.scorePanel} aria-label={`候选 ${candidate.rank} Demo score`}>
        <div className={styles.sectionHeading}>
          <h5>Demo score breakdown</h5>
          <strong>{formatNumber(candidate.score_breakdown.objective, 3)}</strong>
        </div>
        <dl>
          <div><dt>归一化质量</dt><dd>{formatNumber(candidate.score_breakdown.normalized_takeoff_mass, 3)}</dd></div>
          <div><dt>违约权重</dt><dd>{formatNumber(candidate.score_breakdown.constraint_penalty, 3)}</dd></div>
          <div><dt>总违约量</dt><dd>{formatNumber(candidate.score_breakdown.constraint_violation, 3)}</dd></div>
          <div>
            <dt>实际违约贡献</dt>
            <dd>{formatNumber(
              candidate.score_breakdown.constraint_penalty
                * candidate.score_breakdown.constraint_violation,
              3,
            )}</dd>
          </div>
        </dl>
        <p>此分数仅用于本次 Demo 排序，不是 Analyze 输出。</p>
      </section>

      <section className={styles.constraintPanel} aria-label={`候选 ${candidate.rank} constraints`}>
        <h5>约束检查</h5>
        {candidate.constraints.length === 0 ? (
          <p>后端未返回逐项约束。</p>
        ) : (
          <ul>
            {candidate.constraints.slice(0, 5).map((constraint, index) => (
              <li key={`${constraint.key ?? constraint.name ?? index}`} data-pass={constraint.satisfied !== false}>
                <span>{constraintTitle(constraint, index)}</span>
                <strong>{constraintValue(constraint)}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>

      {(candidate.domain_status || candidate.warnings.length > 0) && (
        <div className={styles.candidateNotes}>
          {candidate.domain_status && (
            <p><strong>Analyze domain:</strong> {candidate.domain_status.status}</p>
          )}
          {candidate.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <div className={styles.candidateFooter}>
        <span title={candidate.design_hash}>design {compactId(candidate.design_hash)}</span>
        <button type="button" onClick={() => onAnalyze(candidate)}>
          在 Analyze 中检查
        </button>
      </div>
    </article>
  );
}

export function MissionDemoPanel({
  apiBaseUrl,
  manifest,
  selectedPresetId,
  onAnalyzeCandidate,
}: MissionDemoPanelProps) {
  const [config, setConfig] = useState<DemoProfileConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configAttempt, setConfigAttempt] = useState(0);
  const [inputs, setInputs] = useState<Record<string, number>>({});
  const [job, setJob] = useState<DemoJob | null>(null);
  const [result, setResult] = useState<DemoSearchResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [resultLoading, setResultLoading] = useState(false);
  const [transport, setTransport] = useState<TransportState>("idle");
  const [view, setView] = useState<GeometryView>("3d");

  const eventSourceRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const resultTimerRef = useRef<number | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const resultControllerRef = useRef<AbortController | null>(null);
  const runTokenRef = useRef(0);
  const resultInFlightRef = useRef(false);
  const resultRequestRef = useRef(0);
  const pollFailuresRef = useRef(0);
  const submitInFlightRef = useRef(false);
  const cancelInFlightRef = useRef(false);

  const supported = Boolean(
    manifest
    && manifest.family_id === DEMO_FAMILY_ID
    && config?.supported_family_ids.includes(manifest.family_id),
  );
  const running = job?.status === "queued" || job?.status === "running";
  const groupedInputs = useMemo(() => ({
    requirement: config?.inputs.filter((item) => item.kind === "requirement") ?? [],
    constraint: config?.inputs.filter((item) => item.kind === "constraint") ?? [],
  }), [config]);
  const topCandidates = useMemo(
    () => topDemoCandidates(result?.candidates ?? [], 3),
    [result],
  );
  const sharedReferenceSize = useMemo(
    () => demoSharedReferenceSize(topCandidates, "world"),
    [topCandidates],
  );
  const metricCoverage = result?.metric_coverage ?? config?.metric_coverage ?? null;
  const runFamilyId = result?.family_id ?? job?.family_id ?? null;
  const runPresetId = result?.preset_id ?? job?.preset_id ?? null;
  const selectionMismatch = demoSelectionMismatch(
    manifest?.family_id,
    selectedPresetId,
    runFamilyId,
    runPresetId,
  );
  const inputsMismatch = demoInputsMismatch(inputs, result?.inputs);

  const stopTransport = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    setTransport("idle");
  }, []);

  const invalidateRun = useCallback(() => {
    runTokenRef.current += 1;
    stopTransport();
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    resultControllerRef.current?.abort();
    resultControllerRef.current = null;
    resultRequestRef.current += 1;
    if (resultTimerRef.current !== null) window.clearTimeout(resultTimerRef.current);
    resultTimerRef.current = null;
    resultInFlightRef.current = false;
    cancelInFlightRef.current = false;
  }, [stopTransport]);

  useEffect(() => {
    const controller = new AbortController();
    setConfigError(null);
    fetch(`${apiBaseUrl}/api/rapid-design/demo/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw await errorFromResponse(response, "无法读取 Mission Demo 配置");
        return parseDemoConfig(await response.json());
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((input) => [input.key, input.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setConfig(null);
        setConfigError(reason instanceof Error ? reason.message : "Mission Demo 配置读取失败");
      });
    return () => controller.abort();
  }, [apiBaseUrl, configAttempt]);

  useEffect(() => () => invalidateRun(), [invalidateRun]);

  const loadResult = useCallback(async (
    jobId: string,
    token: number,
    retryIndex = 0,
    manual = false,
  ): Promise<void> => {
    if (token !== runTokenRef.current || (resultInFlightRef.current && !manual)) return;
    resultControllerRef.current?.abort();
    const controller = new AbortController();
    const requestId = ++resultRequestRef.current;
    resultControllerRef.current = controller;
    resultInFlightRef.current = true;
    setResultLoading(true);
    setResultError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/rapid-design/demo/jobs/${encodeURIComponent(jobId)}/result`,
        { signal: controller.signal },
      );
      if (!response.ok) {
        if ((response.status === 404 || response.status === 409) && retryIndex < RESULT_RETRY_DELAYS_MS.length) {
          resultInFlightRef.current = false;
          if (token !== runTokenRef.current) return;
          resultTimerRef.current = window.setTimeout(() => {
            void loadResult(jobId, token, retryIndex + 1);
          }, RESULT_RETRY_DELAYS_MS[retryIndex]);
          return;
        }
        throw await errorFromResponse(response, "候选结果读取失败");
      }
      const parsed = parseDemoSearchResult(await response.json());
      if (
        token !== runTokenRef.current
        || requestId !== resultRequestRef.current
        || parsed.job_id !== jobId
      ) return;
      setResult(parsed);
      setResultError(null);
    } catch (reason: unknown) {
      if (
        (reason as { name?: string }).name === "AbortError"
        || token !== runTokenRef.current
        || requestId !== resultRequestRef.current
      ) return;
      setResultError(reason instanceof Error ? reason.message : "候选结果读取失败");
    } finally {
      if (token === runTokenRef.current && requestId === resultRequestRef.current) {
        resultInFlightRef.current = false;
        setResultLoading(false);
      }
    }
  }, [apiBaseUrl]);

  const pollJob = useCallback(async function poll(
    jobId: string,
    token: number,
  ): Promise<void> {
    if (token !== runTokenRef.current) return;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/rapid-design/demo/jobs/${encodeURIComponent(jobId)}`,
        { signal: controller.signal },
      );
      if (!response.ok) throw await errorFromResponse(response, "Demo job 状态读取失败");
      const latest = parseDemoJob(await response.json());
      if (token !== runTokenRef.current || latest.id !== jobId) return;
      pollFailuresRef.current = 0;
      setJob(latest);
      if (latest.status === "succeeded") {
        cancelInFlightRef.current = false;
        setCancelling(false);
        stopTransport();
        void loadResult(jobId, token);
        return;
      }
      if (latest.status === "failed" || latest.status === "cancelled") {
        cancelInFlightRef.current = false;
        setCancelling(false);
        stopTransport();
        if (latest.status === "failed") setRunError(latest.error ?? "Demo 搜索失败");
        return;
      }
      pollTimerRef.current = window.setTimeout(() => void poll(jobId, token), POLL_INTERVAL_MS);
    } catch (reason: unknown) {
      if ((reason as { name?: string }).name === "AbortError" || token !== runTokenRef.current) return;
      pollFailuresRef.current += 1;
      if (pollFailuresRef.current >= 3) {
        stopTransport();
        setRunError(reason instanceof Error ? reason.message : "Demo job 状态读取失败");
      } else {
        pollTimerRef.current = window.setTimeout(() => void poll(jobId, token), POLL_INTERVAL_MS);
      }
    }
  }, [apiBaseUrl, loadResult, stopTransport]);

  const connectEventStream = useCallback((created: DemoJob, token: number) => {
    stopTransport();
    setTransport("sse");
    const source = new EventSource(
      `${apiBaseUrl}/api/rapid-design/demo/jobs/${encodeURIComponent(created.id)}/events`,
    );
    eventSourceRef.current = source;

    const handleEvent = (event: MessageEvent<string>) => {
      if (token !== runTokenRef.current) return;
      try {
        const payload = JSON.parse(event.data) as Record<string, unknown>;
        if (!demoRunUpdateMatches(runTokenRef.current, token, created.id, payload.job_id)) return;
        const status = typeof payload.status === "string" ? payload.status : created.status;
        const progress = typeof payload.progress === "number" ? clamp(payload.progress, 0, 1) : created.progress;
        const stage = typeof payload.stage === "string" ? payload.stage : created.stage;
        setJob((current) => current?.id === created.id
          ? { ...current, status: status as DemoJob["status"], progress, stage }
          : current);
        if (status === "succeeded" || payload.type === "completed") {
          cancelInFlightRef.current = false;
          setCancelling(false);
          stopTransport();
          void loadResult(created.id, token);
        } else if (status === "failed" || payload.type === "failed") {
          cancelInFlightRef.current = false;
          setCancelling(false);
          stopTransport();
          setTransport("polling");
          void pollJob(created.id, token);
        } else if (status === "cancelled" || payload.type === "cancelled") {
          cancelInFlightRef.current = false;
          setCancelling(false);
          stopTransport();
        }
      } catch {
        // A malformed event must not corrupt the active run. GET polling remains authoritative.
      }
    };

    (["queued", "progress", "completed", "cancelled", "failed"] as const).forEach((name) => {
      source.addEventListener(name, handleEvent as EventListener);
    });
    source.onerror = () => {
      if (token !== runTokenRef.current || eventSourceRef.current !== source) return;
      source.close();
      eventSourceRef.current = null;
      setTransport("polling");
      pollFailuresRef.current = 0;
      void pollJob(created.id, token);
    };
  }, [apiBaseUrl, loadResult, pollJob, stopTransport]);

  const runDemo = useCallback(async () => {
    if (
      !config
      || !manifest
      || !selectedPresetId
      || !supported
      || submitting
      || running
      || submitInFlightRef.current
    ) return;
    invalidateRun();
    const token = runTokenRef.current;
    submitInFlightRef.current = true;
    setSubmitting(true);
    setCancelling(false);
    setJob(null);
    setResult(null);
    setRunError(null);
    setResultError(null);
    try {
      const controller = new AbortController();
      requestControllerRef.current = controller;
      const response = await fetch(`${apiBaseUrl}/api/rapid-design/demo/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          mode: "demo",
          family_id: DEMO_FAMILY_ID,
          preset_id: selectedPresetId,
          inputs,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response, "无法启动 Mission Demo");
      const created = parseDemoJob(await response.json());
      if (token !== runTokenRef.current) return;
      setJob(created);
      connectEventStream(created, token);
    } catch (reason: unknown) {
      if ((reason as { name?: string }).name === "AbortError" || token !== runTokenRef.current) return;
      setRunError(reason instanceof Error ? reason.message : "Mission Demo 启动失败");
    } finally {
      if (token === runTokenRef.current) setSubmitting(false);
      submitInFlightRef.current = false;
    }
  }, [apiBaseUrl, config, connectEventStream, inputs, invalidateRun, manifest, running, selectedPresetId, submitting, supported]);

  const cancelDemo = useCallback(async () => {
    if (!job || !running || cancelling || cancelInFlightRef.current) return;
    const token = runTokenRef.current;
    const jobId = job.id;
    cancelInFlightRef.current = true;
    setCancelling(true);
    setRunError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/rapid-design/demo/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: "POST" },
      );
      if (!response.ok) throw await errorFromResponse(response, "无法停止 Mission Demo");
      const latest = parseDemoJob(await response.json());
      if (token !== runTokenRef.current || latest.id !== jobId) return;
      setJob(latest);
      if (latest.status === "cancelled") {
        cancelInFlightRef.current = false;
        setCancelling(false);
        stopTransport();
      }
    } catch (reason: unknown) {
      if (token !== runTokenRef.current) return;
      cancelInFlightRef.current = false;
      setCancelling(false);
      setRunError(reason instanceof Error ? reason.message : "停止 Mission Demo 失败");
    }
  }, [apiBaseUrl, cancelling, job, running, stopTransport]);

  const retryStatus = useCallback(() => {
    if (!job) return;
    stopTransport();
    setRunError(null);
    setTransport("polling");
    pollFailuresRef.current = 0;
    void pollJob(job.id, runTokenRef.current);
  }, [job, pollJob, stopTransport]);

  const analyzeCandidate = useCallback((candidate: DemoCandidate) => {
    if (!result) return;
    try {
      onAnalyzeCandidate(demoAnalyzeHandoff(result, candidate));
    } catch (reason: unknown) {
      setRunError(reason instanceof Error ? reason.message : "候选交接失败");
    }
  }, [onAnalyzeCandidate, result]);

  return (
    <section className={styles.panel} aria-labelledby="mission-demo-title">
      <header className={styles.hero}>
        <div>
          <div className={styles.badges} aria-label="Mission Demo status">
            <span>DEMO</span>
            <span>NOT FORMAL</span>
            <span>UNAPPROVED</span>
          </div>
          <h2 id="mission-demo-title">Mission 输入 → 可解释候选搜索</h2>
          <p>
            使用固定、可复现的演示 profile 搜索 3 个候选。目标、权重、边界与任务模型仍未获老师批准。
          </p>
        </div>
        <dl className={styles.profileSummary}>
          <div><dt>Profile</dt><dd>{config ? `${config.profile_id} · v${config.profile_version}` : "读取中"}</dd></div>
          <div><dt>Status</dt><dd>{result?.formal_status ?? config?.formal_status ?? "—"}</dd></div>
          <div><dt>Seed</dt><dd>{profileNumber(config, "seed")}</dd></div>
          <div><dt>预算</dt><dd>{config ? `${profileNumber(config, "iterations")} × ${profileNumber(config, "evaluations_per_iteration")}` : "—"}</dd></div>
        </dl>
      </header>

      {config?.disclaimer && <p className={styles.disclaimer}>{config.disclaimer}</p>}

      {configError && (
        <div className={styles.errorBanner} role="alert">
          <div><strong>Demo profile 读取失败</strong><span>{configError}</span></div>
          <button type="button" onClick={() => setConfigAttempt((attempt) => attempt + 1)}>重试</button>
        </div>
      )}

      {!config && !configError && <div className={styles.loading}>正在读取 versioned Demo profile…</div>}

      {manifest && manifest.family_id !== DEMO_FAMILY_ID && (
        <div className={styles.unsupported} role="status">
          <strong>{manifest.display_name} 尚未接入 Mission Demo</strong>
          <span>当前唯一可运行 family 是 conventional_v2；不会将 BWB 偷换成常规布局。</span>
        </div>
      )}

      {(selectionMismatch || inputsMismatch) && runFamilyId && runPresetId && (
        <div className={styles.selectionMismatch} role="status">
          <strong>{selectionMismatch ? "当前选择已改变" : "任务输入已改变"}</strong>
          <span>
            {selectionMismatch && (
              <>下方任务与结果仍属于 <b>{runFamilyId}</b> / <b>{runPresetId}</b>；只有下一次运行才会使用当前选择。</>
            )}
            {selectionMismatch && inputsMismatch && " "}
            {inputsMismatch && "任务输入已改变，下方结果仍属于上次运行，新运行后更新。"}
          </span>
        </div>
      )}

      <div className={styles.workspace}>
        <aside className={styles.inputPane} aria-label="Mission Demo 输入">
          <div className={styles.paneHeading}>
            <span>01 · INPUTS</span>
            <h3>任务需求与约束</h3>
            <p>新运行会清空旧候选；运行中输入锁定。</p>
          </div>

          {(["requirement", "constraint"] as const).map((group) => (
            <fieldset key={group} disabled={!config || running || submitting}>
              <legend>{group === "requirement" ? "任务输入" : "上限与目标"}</legend>
              {groupedInputs[group].map((definition) => (
                <DemoNumericControl
                  key={definition.key}
                  definition={definition}
                  value={inputs[definition.key] ?? definition.default}
                  disabled={!config || running || submitting}
                  onChange={(value) => setInputs((current) => ({ ...current, [definition.key]: value }))}
                />
              ))}
            </fieldset>
          ))}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.runButton}
              disabled={!config || !supported || !selectedPresetId || running || submitting}
              onClick={() => void runDemo()}
            >
              {submitting ? "正在创建 Demo…" : running ? "Demo 运行中" : "运行 Mission Demo"}
            </button>
            <button
              type="button"
              className={styles.cancelButton}
              disabled={!running || cancelling}
              onClick={() => void cancelDemo()}
            >
              {cancelling ? "正在停止…" : "取消"}
            </button>
          </div>
          <p className={styles.familyLine}>
            下一次运行选择 · Family <strong>{manifest?.family_id ?? "—"}</strong> · Preset <strong>{selectedPresetId ?? "—"}</strong>
          </p>
        </aside>

        <div className={styles.resultsPane}>
          <div className={styles.runStatus} aria-live="polite">
            <div className={styles.statusHeader}>
              <div>
                <span>02 · SEARCH</span>
                <h3>{job ? stageLabel(job.stage) : "等待运行"}</h3>
              </div>
              {job && <strong>{Math.round(job.progress * 100)}%</strong>}
            </div>
            <div className={styles.progressTrack} aria-hidden="true">
              <span style={{ width: `${Math.round((job?.progress ?? 0) * 100)}%` }} />
            </div>
            <div className={styles.statusMeta}>
              <span>
                {job
                  ? `${job.status} · ${job.family_id}/${job.preset_id} · ${compactId(job.id)}`
                  : "尚未创建 job"}
              </span>
              {transport === "sse" && <span>SSE 实时进度</span>}
              {transport === "polling" && <span>连接中断 · 已切换轮询</span>}
              {job?.status === "cancelled" && <span>本次 Demo 已取消</span>}
            </div>
          </div>

          {runError && (
            <div className={styles.errorBanner} role="alert">
              <div><strong>运行状态异常</strong><span>{runError}</span></div>
              {job && (job.status === "queued" || job.status === "running") && (
                <button type="button" onClick={retryStatus}>重新连接</button>
              )}
              {(!job || (job.status !== "queued" && job.status !== "running")) && (
                <button type="button" disabled={!config || !supported || submitting} onClick={() => void runDemo()}>
                  重试运行
                </button>
              )}
            </div>
          )}

          {resultError && (
            <div className={styles.errorBanner} role="alert">
              <div><strong>搜索已结束，但候选读取失败</strong><span>{resultError}</span></div>
              {job && (
                <button
                  type="button"
                  disabled={resultLoading}
                  onClick={() => void loadResult(job.id, runTokenRef.current, 0, true)}
                >
                  {resultLoading ? "读取中…" : "重试结果"}
                </button>
              )}
            </div>
          )}

          {!result && !resultLoading && !resultError && (
            <div className={styles.emptyState}>
              <span>TOP 3</span>
              <h3>{running ? "正在探索设计空间" : "运行后在此比较候选"}</h3>
              <p>候选将使用同一相机尺度展示，以便直接比较真实尺寸；预览不响应拖拽。</p>
            </div>
          )}
          {resultLoading && <div className={styles.loading}>正在校验并读取 Top 3 候选…</div>}

          {result && (
            <>
              <section className={styles.resultSummary} aria-label="Demo result summary">
                <div>
                  <span>PROFILE</span>
                  <strong>{result.profile.id} · v{result.profile.version}</strong>
                </div>
                <div>
                  <span>RUN TARGET</span>
                  <strong>{result.family_id}</strong>
                  <small>{result.preset_id}</small>
                </div>
                <div>
                  <span>SEED</span>
                  <strong>{result.search.seed}</strong>
                </div>
                <div>
                  <span>EVALUATIONS</span>
                  <strong>{result.search.evaluations}</strong>
                  <small>{result.search.invalid} invalid</small>
                </div>
                <div>
                  <span>RANKING</span>
                  <strong>{result.ranking_rule.primary}</strong>
                  <small>{result.ranking_rule.feasible_first ? "feasible first" : "objective only"}</small>
                </div>
              </section>

              <section className={styles.coveragePanel} aria-labelledby="coverage-title">
                <div className={styles.coverageHeading}>
                  <div>
                    <span>MODEL COVERAGE</span>
                    <h3 id="coverage-title">指标连接状态</h3>
                  </div>
                  <div className={styles.coverageCounts}>
                    {coverageCounts(metricCoverage).map(({ status, count }) => (
                      <span key={status} data-status={status}>{status} · {count}</span>
                    ))}
                  </div>
                </div>
                <div className={styles.coverageList}>
                  {metricCoverage?.metrics.map((metric) => (
                    <details key={metric.key} data-status={metric.status}>
                      <summary>
                        <span>{metric.label}</span>
                        <strong>{metric.status}</strong>
                      </summary>
                      <p>{metric.reason || metric.source || "未提供说明"}</p>
                      <small>{metric.used_in_score ? "参与 Demo score" : "不参与 Demo score"}</small>
                    </details>
                  ))}
                </div>
              </section>

              <div className={styles.candidateToolbar}>
                <div>
                  <span>03 · TOP {topCandidates.length}</span>
                  <h3>按后端 rank 展示</h3>
                </div>
                <div className={styles.viewSwitch} aria-label="候选预览视角">
                  {VIEW_OPTIONS.map((option) => (
                    <button
                      type="button"
                      key={option.id}
                      aria-pressed={view === option.id}
                      onClick={() => setView(option.id)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.candidateGrid}>
                {topCandidates.map((candidate) => (
                  <CandidateCard
                    key={candidate.candidate_id}
                    candidate={candidate}
                    view={view}
                    sharedReferenceSize={sharedReferenceSize}
                    anyFeasible={topCandidates.some((item) => item.feasible)}
                    onAnalyze={analyzeCandidate}
                  />
                ))}
              </div>

              {(result.warnings.length > 0 || Object.keys(result.provenance).length > 0) && (
                <footer className={styles.provenance}>
                  <div>
                    <strong>Warnings</strong>
                    {result.warnings.length > 0
                      ? result.warnings.map((warning) => <p key={warning}>{warning}</p>)
                      : <p>无结果级 warning。</p>}
                  </div>
                  <div>
                    <strong>Provenance</strong>
                    <p>{Object.entries(result.provenance).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</p>
                  </div>
                </footer>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
