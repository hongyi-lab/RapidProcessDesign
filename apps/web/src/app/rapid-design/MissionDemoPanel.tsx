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
  parseDemoJobList,
  parseDemoSearchResult,
  topDemoCandidates,
  type DemoAnalyzeHandoff,
  type DemoCandidate,
  type DemoConstraint,
  type DemoJob,
  type DemoJobList,
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
  const unit = constraint.unit ?? "";
  const actual = typeof constraint.actual === "number"
    ? constraint.actual
    : typeof constraint.value === "number" ? constraint.value : null;
  const parts = [
    actual === null ? null : `实际 ${formatNumber(actual, 2)} ${unit}`.trim(),
    typeof constraint.limit === "number"
      ? `阈值 ${formatNumber(constraint.limit, 2)} ${unit}`.trim()
      : null,
    typeof constraint.margin === "number"
      ? `余量 ${formatNumber(constraint.margin, 2)} ${unit}`.trim()
      : null,
    typeof constraint.violation === "number" && constraint.violation > 0
      ? `违约 ${formatNumber(constraint.violation, 3)}`
      : null,
  ].filter((item): item is string => Boolean(item));
  return parts.join(" · ") || (constraint.satisfied === false ? "未满足" : "已检查");
}

const SELECTION_REASON_LABELS: Record<string, string> = {
  selected_best_ranked: "按当前排序入选",
  selected_diverse: "满足几何差异阈值后入选",
  selected_feasible_first_objective: "满足约束，按 objective 与几何差异入选",
  selected_current_score_best_infeasible: "无可行解时，按当前 objective 与几何差异入选",
  selected_infeasible_after_feasible: "排在可行候选之后，并通过几何差异阈值",
  selected_legacy_result: "旧版结果（未记录选择原因）",
  excluded_candidate_limit: "超出 Top-K 数量",
  excluded_top_k_capacity: "Top-K 名额已满",
  excluded_geometry_similarity: "与已选候选几何过近",
  excluded_invalid_geometry: "几何无效",
  invalid_evaluation: "评价无效",
};

function selectionReason(code: string): string {
  return SELECTION_REASON_LABELS[code] ?? code.replaceAll("_", " ");
}

function jobStatusLabel(status: DemoJob["status"]): string {
  const labels: Record<DemoJob["status"], string> = {
    queued: "等待",
    running: "运行中",
    succeeded: "已完成",
    failed: "异常失败",
    cancelled: "已取消",
    interrupted: "重启时中断",
  };
  return labels[status];
}

function coverageCounts(coverage: DemoMetricCoverage | null) {
  return (["connected", "partial", "not_connected"] as const).map((status) => ({
    status,
    count: coverage?.metrics.filter((metric) => metric.status === status).length ?? 0,
  }));
}

function CruiseConsistencyPanel({ candidate }: { candidate: DemoCandidate }) {
  const diagnostic = candidate.cruise_consistency;
  if (!diagnostic) {
    return (
      <section className={styles.cruisePanel} aria-label={`候选 ${candidate.rank} 巡航一致性诊断`}>
        <div className={styles.sectionHeading}>
          <h5>巡航一致性诊断</h5>
          <strong>旧结果未记录</strong>
        </div>
        <p>此恢复结果早于 Round 7，不能据此判断参考巡航状态是否落在 polar 支持区间。</p>
      </section>
    );
  }
  const supported = diagnostic.status === "supported";
  const point = diagnostic.matched_working_point;
  return (
    <section
      className={styles.cruisePanel}
      data-supported={supported}
      aria-label={`候选 ${candidate.rank} 巡航一致性诊断`}
    >
      <div className={styles.sectionHeading}>
        <h5>巡航一致性诊断</h5>
        <strong>{supported ? "SUPPORTED" : "UNSUPPORTED · LIFT_NOT_SUPPORTED"}</strong>
      </div>
      <dl>
        <div>
          <dt>参考质量</dt>
          <dd>{formatNumber(diagnostic.reference_state.mass_kg, 1)} kg</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>
            {formatNumber(diagnostic.reference_state.altitude_m, 0)} m · {formatNumber(diagnostic.reference_state.speed_kmh, 0)} km/h
          </dd>
        </div>
        <div>
          <dt>所需 CL</dt>
          <dd>{formatNumber(diagnostic.required_cl, 3)}</dd>
        </div>
        <div>
          <dt>polar CL 区间</dt>
          <dd>{formatNumber(diagnostic.polar_support.min_cl, 3)} – {formatNumber(diagnostic.polar_support.max_cl, 3)}</dd>
        </div>
        <div>
          <dt>参考状态 L/D</dt>
          <dd>{point ? formatNumber(point.ld, 2) : "不支持，未外推"}</dd>
        </div>
        <div>
          <dt>max L/D / 航程所用 L/D</dt>
          <dd>
            {formatNumber(diagnostic.comparison.max_ld, 2)} / {formatNumber(diagnostic.comparison.range_model_ld, 2)}
          </dd>
        </div>
      </dl>
      {!supported && (
        <p>
          当前起飞质量参考状态需要的升力超出已有 polar 支持区间；没有外推，也没有退回 max L/D 冒充匹配工作点。
        </p>
      )}
      <p>
        参考质量口径：Mission Demo 起飞质量。本诊断不进入 score 或现有航程估算，也不是配平、稳定性或推进匹配验证。
      </p>
    </section>
  );
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
    ? "满足当前 Demo 已接入约束"
    : !anyFeasible && candidate.rank === 1
      ? "当前评分最优的未满足约束候选"
      : "未满足当前 Demo 已接入约束";

  return (
    <article className={styles.candidateCard} data-feasible={candidate.feasible}>
      <header className={styles.candidateHeader}>
        <div>
          <span className={styles.rank}>#{candidate.rank}</span>
          <h4>候选 {compactId(candidate.candidate_id)}</h4>
        </div>
        <span className={styles.feasibility}>{statusLabel}</span>
      </header>

      <div className={styles.qualificationRow} aria-label={`候选 ${candidate.rank} 资格说明`}>
        <span data-pass={candidate.qualification.geometry_valid}>
          {candidate.qualification.geometry_valid ? "几何有效" : "几何无效"}
        </span>
        <span data-pass={candidate.qualification.demo_constraints_satisfied}>
          {candidate.qualification.demo_constraints_satisfied
            ? "满足 Demo 已接入约束"
            : "未满足 Demo 已接入约束"}
        </span>
        <span data-pass="false">工程验证未执行（不能称已通过）</span>
      </div>

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
        {candidate.score_breakdown.terms.length > 0 && (
          <details className={styles.scoreTerms}>
            <summary>查看后端评分项</summary>
            <ul>
              {candidate.score_breakdown.terms.map((term, index) => (
                <li key={`${term.metric_key ?? term.label ?? "term"}-${index}`}>
                  <span>{term.label ?? term.metric_key ?? `评分项 ${index + 1}`}</span>
                  <strong>
                    {typeof term.contribution === "number"
                      ? formatNumber(term.contribution, 4)
                      : "已记录"}
                  </strong>
                </li>
              ))}
            </ul>
          </details>
        )}
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

      <CruiseConsistencyPanel candidate={candidate} />

      {(candidate.domain_status || candidate.warnings.length > 0) && (
        <div className={styles.candidateNotes}>
          {candidate.domain_status && (
            <p><strong>Analyze domain:</strong> {candidate.domain_status.status}</p>
          )}
          {candidate.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <div className={styles.candidateFooter}>
        <div>
          <span title={candidate.design_hash}>design hash {compactId(candidate.design_hash)}</span>
          <span title={candidate.geometry_fingerprint ?? undefined}>
            geometry {candidate.geometry_fingerprint
              ? compactId(candidate.geometry_fingerprint)
              : "旧结果未记录"}
          </span>
          <span title={candidate.selection.explanation ?? undefined}>
            选择：{selectionReason(candidate.selection.reason_code)}
          </span>
        </div>
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
  const [recentJobs, setRecentJobs] = useState<DemoJob[]>([]);
  const [recoveryPolicy, setRecoveryPolicy] = useState<DemoJobList["recovery"] | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [recoveryOpen, setRecoveryOpen] = useState(false);

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
  const recentRequestRef = useRef(0);

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

  const loadRecentJobs = useCallback(async (): Promise<void> => {
    const requestId = ++recentRequestRef.current;
    setRecentLoading(true);
    setRecentError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/rapid-design/demo/jobs?limit=10`);
      if (!response.ok) throw await errorFromResponse(response, "无法读取可恢复任务");
      const parsed = parseDemoJobList(await response.json());
      if (requestId !== recentRequestRef.current) return;
      setRecentJobs(parsed.jobs);
      setRecoveryPolicy(parsed.recovery);
    } catch (reason: unknown) {
      if (requestId !== recentRequestRef.current) return;
      setRecentError(reason instanceof Error ? reason.message : "可恢复任务读取失败");
    } finally {
      if (requestId === recentRequestRef.current) setRecentLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void loadRecentJobs();
    return () => {
      recentRequestRef.current += 1;
    };
  }, [loadRecentJobs]);

  const loadResult = useCallback(async (
    jobId: string,
    token: number,
    retryIndex = 0,
    manual = false,
    restoreInputs = false,
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
      if (restoreInputs) setInputs({ ...parsed.inputs });
      setResultError(null);
      void loadRecentJobs();
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
  }, [apiBaseUrl, loadRecentJobs]);

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
      if (
        latest.status === "failed"
        || latest.status === "cancelled"
        || latest.status === "interrupted"
      ) {
        cancelInFlightRef.current = false;
        setCancelling(false);
        stopTransport();
        if (latest.status === "failed") setRunError(latest.error ?? "Demo 搜索失败");
        if (latest.status === "interrupted") {
          setRunError(latest.error ?? "服务重启时任务尚未完成；本轮不支持断点续跑，请重新运行。");
        }
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
        } else if (status === "interrupted" || payload.type === "interrupted") {
          cancelInFlightRef.current = false;
          setCancelling(false);
          stopTransport();
          setRunError("服务重启时任务尚未完成；本轮不支持断点续跑，请重新运行。");
        }
      } catch {
        // A malformed event must not corrupt the active run. GET polling remains authoritative.
      }
    };

    (["queued", "progress", "completed", "cancelled", "failed", "interrupted"] as const).forEach((name) => {
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

  const recoverCompletedJob = useCallback(async (summary: DemoJob): Promise<void> => {
    if (summary.status !== "succeeded" || running || submitting) return;
    invalidateRun();
    const token = runTokenRef.current;
    setJob(null);
    setResult(null);
    setRunError(null);
    setResultError(null);
    setRecoveryOpen(true);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/rapid-design/demo/jobs/${encodeURIComponent(summary.id)}`,
      );
      if (!response.ok) throw await errorFromResponse(response, "无法查询旧任务状态");
      const latest = parseDemoJob(await response.json());
      if (token !== runTokenRef.current || latest.id !== summary.id) return;
      setJob(latest);
      if (latest.status === "succeeded") {
        await loadResult(latest.id, token, 0, true, true);
      } else if (latest.status === "interrupted") {
        setRunError(latest.error ?? "该任务在服务重启时中断，不支持断点续跑。");
      } else {
        setRunError(`旧任务当前状态为 ${jobStatusLabel(latest.status)}，仅已完成结果可恢复。`);
      }
    } catch (reason: unknown) {
      if (token !== runTokenRef.current) return;
      setRunError(reason instanceof Error ? reason.message : "旧任务恢复失败");
    }
  }, [apiBaseUrl, invalidateRun, loadResult, running, submitting]);

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
            使用固定、可复现的演示 profile 搜索至多 3 个候选；不足 3 个时保留已有有效结果。目标、权重、边界与任务模型仍未获老师批准。
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

          <section className={styles.recoveryPanel} aria-labelledby="mission-demo-recovery-title">
            <button
              type="button"
              className={styles.recoveryToggle}
              aria-expanded={recoveryOpen}
              onClick={() => {
                setRecoveryOpen((open) => !open);
                if (!recoveryOpen) void loadRecentJobs();
              }}
            >
              <span>
                <strong id="mission-demo-recovery-title">恢复已完成任务</strong>
                <small>刷新或服务重启后仍可查询已保存结果</small>
              </span>
              <b aria-hidden="true">{recoveryOpen ? "−" : "+"}</b>
            </button>
            {recoveryOpen && (
              <div className={styles.recoveryBody}>
                <div className={styles.recoveryPolicy}>
                  <span>{recoveryPolicy?.completed_queryable === false ? "已完成结果不可查询" : "已完成结果可查询"}</span>
                  <span>未完成任务不支持断点续跑</span>
                </div>
                {recentLoading && <p>正在读取旧任务…</p>}
                {recentError && (
                  <div className={styles.recoveryError} role="alert">
                    <span>{recentError}</span>
                    <button type="button" onClick={() => void loadRecentJobs()}>重试</button>
                  </div>
                )}
                {!recentLoading && !recentError && recentJobs.length === 0 && (
                  <p>尚无已保存任务。</p>
                )}
                {recentJobs.length > 0 && (
                  <ul className={styles.recoveryList}>
                    {recentJobs.map((item) => (
                      <li key={item.id} data-status={item.status}>
                        <div>
                          <strong>{item.preset_id}</strong>
                          <small title={item.id}>{compactId(item.id)} · {jobStatusLabel(item.status)}</small>
                        </div>
                        {item.status === "succeeded" ? (
                          <button
                            type="button"
                            disabled={resultLoading || running || submitting}
                            onClick={() => void recoverCompletedJob(item)}
                          >
                            查询结果
                          </button>
                        ) : (
                          <span>{item.status === "interrupted" ? "需重新运行" : "不可恢复"}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>
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
              {job?.status === "interrupted" && <span>服务重启时中断 · 不支持断点续跑</span>}
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
              <span>CANDIDATE RESULTS</span>
              <h3>{running ? "正在探索设计空间" : "运行后在此比较候选"}</h3>
              <p>候选将使用同一相机尺度展示，以便直接比较真实尺寸；预览不响应拖拽。</p>
            </div>
          )}
          {resultLoading && <div className={styles.loading}>正在校验并读取候选结果…</div>}

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
                  <small>
                    {result.search.valid} valid · {result.search.invalid} invalid
                    {result.search.elapsed_ms !== null && ` · ${formatNumber(result.search.elapsed_ms, 0)} ms`}
                  </small>
                </div>
                <div>
                  <span>RANKING</span>
                  <strong>{result.ranking_rule.primary}</strong>
                  <small>{result.ranking_rule.feasible_first ? "feasible first" : "objective only"}</small>
                </div>
              </section>

              <section
                className={styles.outcomePanel}
                data-status={result.status}
                aria-label="候选搜索结果解释"
              >
                <div>
                  <strong>
                    {result.status === "no_valid_candidates"
                      ? "没有有效候选评价"
                      : result.status === "no_feasible_solution_found"
                        ? "没有候选满足当前 Demo 已接入约束"
                        : `${result.selection.feasible_valid_count} 个候选满足当前 Demo 已接入约束`}
                  </strong>
                  <p>
                    返回 {result.selection.returned_count} / {result.selection.requested_count} 个候选；
                    {result.selection.infeasible_valid_count} 个有效候选未满足当前 Demo 约束。
                    {result.selection.outcome === "partial" && " 已保留不足 Top-K 的现有结果，没有将整次任务判为异常。"}
                    {result.status === "no_feasible_solution_found" && " 排名仍遵循 feasible-first 后按 objective；第一名仅表示当前评分最优，并不表示违约量最小。"}
                    {result.status === "no_valid_candidates" && " 这与“有有效候选但无可行解”及程序异常是不同结果。"}
                  </p>
                </div>
                <span>工程验证：未执行</span>
              </section>

              <details className={styles.selectionPanel}>
                <summary>
                  <span>选择与排除记录</span>
                  <strong>{result.selection.decisions.length} 条</strong>
                </summary>
                {result.selection.decisions.length === 0 ? (
                  <p>没有可记录的有效候选决策。</p>
                ) : (
                  <ul>
                    {result.selection.decisions.map((decision) => (
                      <li key={`${decision.candidate_id}-${decision.ranked_position}`} data-selected={decision.selected}>
                        <span>
                          #{decision.ranked_position} · {compactId(decision.candidate_id)} · {decision.feasible ? "满足 Demo 约束" : "未满足 Demo 约束"}
                        </span>
                        <strong title={decision.explanation ?? undefined}>
                          {decision.selected ? "入选" : "排除"} · {selectionReason(decision.reason_code)}
                        </strong>
                      </li>
                    ))}
                  </ul>
                )}
              </details>

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

              {topCandidates.length > 0 ? (
                <>
                  <div className={styles.candidateToolbar}>
                    <div>
                      <span>03 · RETURNED {topCandidates.length}</span>
                      <h3>按后端 rank 逐项展示</h3>
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

                  <div className={styles.candidateGrid} data-count={topCandidates.length}>
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
                </>
              ) : (
                <div className={styles.noCandidateState} role="status">
                  <strong>没有可展示或交给 Analyze 的几何</strong>
                  <p>搜索已正常结束，但所有评价都未形成几何有效候选。请检查逐案例记录；这不是“无可行解”的同义词。</p>
                </div>
              )}

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
