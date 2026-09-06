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
  type GeometryState,
  type GeometryView,
} from "@/components/rapid-design/geometry";

import styles from "./MissionDemoPanel.module.css";
import { sharedGeometryFrame, type GeometryFrame } from "@/components/rapid-design/geometry/cameraFraming";
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
  takeoff_mass_kg: { label: "Takeoff mass", unit: "kg", digits: 1 },
  achieved_range_km: { label: "Estimated range", unit: "km", digits: 0 },
  max_lift_to_drag: { label: "Peak L/D", unit: "", digits: 2 },
  fuel_mass_kg: { label: "Fuel mass", unit: "kg", digits: 1 },
};

const VIEW_OPTIONS: ReadonlyArray<{ id: GeometryView; label: string }> = [
  { id: "3d", label: "3D" },
  { id: "top", label: "Top" },
  { id: "side", label: "Side" },
  { id: "front", label: "Front" },
];

const INPUT_LABELS: Record<string, string> = {
  required_range_km: "Target range",
  payload_mass_kg: "Payload",
  cruise_speed_kmh: "Cruise speed",
  cruise_altitude_m: "Cruise altitude",
  max_fuel_mass_kg: "Fuel limit",
  max_takeoff_mass_kg: "Takeoff mass limit",
  target_lift_to_drag: "Target L/D",
};

const TASK_PRESENTATION: Record<string, { label: string; description: string }> = {
  long_endurance_uav: {
    label: "Long endurance",
    description: "Slender wing · V-tail · Rear propeller",
  },
  fast_cruise_recon: {
    label: "Fast reconnaissance",
    description: "Swept wing · T-tail · Nose propeller",
  },
  payload_utility: {
    label: "Cargo utility",
    description: "Wide body · High wing · Twin engines",
  },
};

type TransportState = "idle" | "sse" | "polling";

type MissionDemoPanelProps = {
  apiBaseUrl: string;
  manifest: FamilyManifest | null;
  selectedPresetId: string | null;
  onPresetChange: (presetId: string) => void;
  baselineGeometry: GeometryState | null;
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
  const [draft, setDraft] = useState(() => String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commitDraft = () => {
    const parsed = Number(draft);
    if (draft.trim() === "" || !Number.isFinite(parsed)) {
      setDraft(String(value));
      return;
    }
    const next = clamp(parsed, definition.minimum, definition.maximum);
    setDraft(String(Number(next.toFixed(digits))));
    if (next !== value) onChange(next);
  };

  const parsedDraft = Number(draft);
  const draftIsValid = draft.trim() !== ""
    && Number.isFinite(parsedDraft)
    && parsedDraft >= definition.minimum
    && parsedDraft <= definition.maximum;

  return (
    <div className={styles.inputControl}>
      <div className={styles.inputLabel}>
        <label id={`${id}-label`} htmlFor={`${id}-number`}>
          {INPUT_LABELS[definition.key] ?? definition.label}
        </label>
      </div>
      <div className={styles.inputFields}>
        <input
          id={`${id}-number`}
          type="number"
          inputMode="decimal"
          min={definition.minimum}
          max={definition.maximum}
          step={definition.step}
          value={draft}
          disabled={disabled}
          aria-labelledby={`${id}-label`}
          aria-describedby={`${id}-bounds`}
          aria-invalid={!draftIsValid}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitDraft}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
            if (event.key === "Escape") {
              event.preventDefault();
              setDraft(String(value));
            }
          }}
        />
        <span>{definition.unit || "—"}</span>
      </div>
      <p id={`${id}-bounds`} className={styles.inputBounds}>
        Range {formatNumber(definition.minimum, digits)}–{formatNumber(definition.maximum, digits)} {definition.unit}
      </p>
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
    actual === null ? null : `Actual ${formatNumber(actual, 2)} ${unit}`.trim(),
    typeof constraint.limit === "number"
      ? `Limit ${formatNumber(constraint.limit, 2)} ${unit}`.trim()
      : null,
    typeof constraint.margin === "number"
      ? `Margin ${formatNumber(constraint.margin, 2)} ${unit}`.trim()
      : null,
    typeof constraint.violation === "number" && constraint.violation > 0
      ? `Violation ${formatNumber(constraint.violation, 3)}`
      : null,
  ].filter((item): item is string => Boolean(item));
  return parts.join(" · ") || (constraint.satisfied === false ? "Not met" : "Checked");
}

const SELECTION_REASON_LABELS: Record<string, string> = {
  selected_best_ranked: "Selected by rank",
  selected_diverse: "Selected for a distinct shape",
  selected_feasible_first_objective: "Feasible; selected by score and shape diversity",
  selected_current_score_best_infeasible: "Infeasible; selected by score and shape diversity",
  selected_infeasible_after_feasible: "Ranked after feasible designs; distinct geometry",
  selected_legacy_result: "Older result; selection reason unavailable",
  excluded_candidate_limit: "Outside the requested candidate count",
  excluded_top_k_capacity: "Candidate limit reached",
  excluded_geometry_similarity: "Too similar to a selected candidate",
  excluded_invalid_geometry: "Invalid geometry",
  invalid_evaluation: "Invalid evaluation",
};

function selectionReason(code: string): string {
  return SELECTION_REASON_LABELS[code] ?? code.replaceAll("_", " ");
}

function jobStatusLabel(status: DemoJob["status"]): string {
  const labels: Record<DemoJob["status"], string> = {
    queued: "Waiting",
    running: "Running",
    succeeded: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    interrupted: "Interrupted by restart",
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
      <section className={styles.cruisePanel} aria-label={`Concept ${candidate.rank} Cruise consistency`}>
        <div className={styles.sectionHeading}>
          <h5>Cruise consistency</h5>
          <strong>Unavailable in this saved result</strong>
        </div>
        <p>This older result does not include cruise consistency diagnostics.</p>
      </section>
    );
  }
  const supported = diagnostic.status === "supported";
  const point = diagnostic.matched_working_point;
  return (
    <section
      className={styles.cruisePanel}
      data-supported={supported}
      aria-label={`Concept ${candidate.rank} Cruise consistency`}
    >
      <div className={styles.sectionHeading}>
        <h5>Cruise consistency</h5>
        <strong>{supported ? "SUPPORTED" : "UNSUPPORTED · LIFT_NOT_SUPPORTED"}</strong>
      </div>
      <dl>
        <div>
          <dt>Reference mass</dt>
          <dd>{formatNumber(diagnostic.reference_state.mass_kg, 1)} kg</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            {formatNumber(diagnostic.reference_state.altitude_m, 0)} m · {formatNumber(diagnostic.reference_state.speed_kmh, 0)} km/h
          </dd>
        </div>
        <div>
          <dt>Required CL</dt>
          <dd>{formatNumber(diagnostic.required_cl, 3)}</dd>
        </div>
        <div>
          <dt>Supported CL range</dt>
          <dd>{formatNumber(diagnostic.polar_support.min_cl, 3)} – {formatNumber(diagnostic.polar_support.max_cl, 3)}</dd>
        </div>
        <div>
          <dt>L/D at reference condition</dt>
          <dd>{point ? formatNumber(point.ld, 2) : "Outside model range"}</dd>
        </div>
        <div>
          <dt>Peak L/D used for range estimate</dt>
          <dd>
            {formatNumber(diagnostic.comparison.max_ld, 2)} / {formatNumber(diagnostic.comparison.range_model_ld, 2)}
          </dd>
        </div>
      </dl>
      {!supported && (
        <p>
          The required lift at takeoff mass is outside the sampled polar. No cruise operating point can be matched.
        </p>
      )}
      <p>
        Uses demo takeoff mass. This diagnostic does not affect the score or range estimate, and does not validate trim, stability or propulsion.
      </p>
    </section>
  );
}

function CandidateCard({
  candidate,
  view,
  sharedReferenceSize,
  sharedFrame,
  sameScale,
  anyFeasible,
  onAnalyze,
}: {
  candidate: DemoCandidate;
  view: GeometryView;
  sharedReferenceSize: number;
  sharedFrame?: GeometryFrame;
  sameScale: boolean;
  anyFeasible: boolean;
  onAnalyze: (candidate: DemoCandidate) => void;
}) {
  const statusLabel = candidate.feasible
    ? "Meets modeled requirements"
    : !anyFeasible && candidate.rank === 1
      ? "Best ranked; requirements not met"
      : "Requirements not met";

  return (
    <article className={styles.candidateCard} data-feasible={candidate.feasible}>
      <header className={styles.candidateHeader}>
        <div>
          <h4>{candidate.rank === 1 && candidate.feasible ? "Recommended concept" : `Concept ${candidate.rank}`}</h4>
          <span className={styles.feasibility}>{statusLabel}</span>
        </div>
        <button type="button" onClick={() => onAnalyze(candidate)}>Inspect geometry ↗</button>
      </header>

      <div className={styles.previewFrame}>
        <ParametricAircraftPreview
          geometry={candidate.geometry_state}
          view={view}
          scaleMode={sameScale ? "world" : "auto"}
          sharedReferenceSize={sharedReferenceSize}
          sharedFrame={sameScale ? sharedFrame : undefined}
          interactive
          showViewControls={false}
          showScaleControls={false}
        />
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

      <section className={styles.constraintSummary} aria-label={`Concept ${candidate.rank} requirements`}>
        <h5>Requirements</h5>
        {candidate.constraints.length === 0 ? (
          <p>Individual constraints are unavailable.</p>
        ) : (
          <ul>
            {candidate.constraints.slice(0, 5).map((constraint, index) => (
              <li key={`${constraint.key ?? constraint.name ?? index}`} data-pass={constraint.satisfied !== false}>
                <span>{constraintTitle(constraint, index)}</span>
                <strong>{constraint.satisfied === false ? "Not met" : "Met"}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>

      <details className={styles.candidateTechnical}>
        <summary>Technical details</summary>
        <div className={styles.candidateTechnicalBody}>
          <p className={styles.validationNote}>
            {candidate.qualification.geometry_valid ? "Valid geometry." : "Invalid geometry."}
            {" "}Concept estimates only. Engineering validation has not been performed.
          </p>
          <section className={styles.scorePanel} aria-label={`Concept ${candidate.rank} Demo score`}>
            <div className={styles.sectionHeading}>
              <h5>Demo score breakdown</h5>
              <strong>{formatNumber(candidate.score_breakdown.objective, 3)}</strong>
            </div>
            <dl>
              <div><dt>Normalized mass</dt><dd>{formatNumber(candidate.score_breakdown.normalized_takeoff_mass, 3)}</dd></div>
              <div><dt>Penalty weight</dt><dd>{formatNumber(candidate.score_breakdown.constraint_penalty, 3)}</dd></div>
              <div><dt>Total violation</dt><dd>{formatNumber(candidate.score_breakdown.constraint_violation, 3)}</dd></div>
              <div>
                <dt>Penalty contribution</dt>
                <dd>{formatNumber(
                  candidate.score_breakdown.constraint_penalty
                    * candidate.score_breakdown.constraint_violation,
                  3,
                )}</dd>
              </div>
            </dl>
            {candidate.score_breakdown.terms.length > 0 && (
              <details className={styles.scoreTerms}>
                <summary>Score terms</summary>
                <ul>
                  {candidate.score_breakdown.terms.map((term, index) => (
                    <li key={`${term.metric_key ?? term.label ?? "term"}-${index}`}>
                      <span>{term.label ?? term.metric_key ?? `Score term ${index + 1}`}</span>
                      <strong>
                        {typeof term.contribution === "number"
                          ? formatNumber(term.contribution, 4)
                          : "Recorded"}
                      </strong>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <p>This score ranks concepts within this run only.</p>
          </section>

          <section className={styles.constraintPanel} aria-label={`Concept ${candidate.rank} constraints`}>
            <h5>Constraint margins</h5>
            {candidate.constraints.length === 0 ? (
              <p>Individual constraints are unavailable.</p>
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
                  : "Unavailable in this saved result"}
              </span>
              <span title={candidate.selection.explanation ?? undefined}>
                Selection:{selectionReason(candidate.selection.reason_code)}
              </span>
            </div>
            <button type="button" onClick={() => onAnalyze(candidate)}>
              Open in Analyze
            </button>
          </div>
        </div>
      </details>
    </article>
  );
}

export function MissionDemoPanel({
  apiBaseUrl,
  manifest,
  selectedPresetId,
  onPresetChange,
  baselineGeometry,
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
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

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
  const selectedCandidate = useMemo(
    () => topCandidates.find((candidate) => candidate.candidate_id === selectedCandidateId)
      ?? topCandidates[0]
      ?? null,
    [selectedCandidateId, topCandidates],
  );
  const feasibleShown = topCandidates.filter((candidate) => candidate.feasible).length;
  const [sameScale, setSameScale] = useState(false);
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
  const sharedReferenceSize = useMemo(
    () => demoSharedReferenceSize(topCandidates, "world"),
    [topCandidates],
  );
  const sharedFrame = useMemo(
    () => sharedGeometryFrame(topCandidates.map((candidate) => candidate.geometry_state)),
    [topCandidates],
  );

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
        if (!response.ok) throw await errorFromResponse(response, "Could not load search settings");
        return parseDemoConfig(await response.json());
      })
      .then((payload) => {
        setConfig(payload);
        setInputs(Object.fromEntries(payload.inputs.map((input) => [input.key, input.default])));
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setConfig(null);
        setConfigError(reason instanceof Error ? reason.message : "Could not load search settings");
      });
    return () => controller.abort();
  }, [apiBaseUrl, configAttempt]);

  useEffect(() => () => invalidateRun(), [invalidateRun]);

  useEffect(() => {
    setSelectedCandidateId(topCandidates[0]?.candidate_id ?? null);
  }, [result?.job_id, topCandidates]);

  const loadRecentJobs = useCallback(async (): Promise<void> => {
    const requestId = ++recentRequestRef.current;
    setRecentLoading(true);
    setRecentError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/rapid-design/demo/jobs?limit=10`);
      if (!response.ok) throw await errorFromResponse(response, "Could not load saved runs");
      const parsed = parseDemoJobList(await response.json());
      if (requestId !== recentRequestRef.current) return;
      setRecentJobs(parsed.jobs);
      setRecoveryPolicy(parsed.recovery);
    } catch (reason: unknown) {
      if (requestId !== recentRequestRef.current) return;
      setRecentError(reason instanceof Error ? reason.message : "Could not load saved runs");
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
        throw await errorFromResponse(response, "Could not load concepts");
      }
      const parsed = parseDemoSearchResult(await response.json());
      if (
        token !== runTokenRef.current
        || requestId !== resultRequestRef.current
        || parsed.job_id !== jobId
      ) return;
      setResult(parsed);
      if (restoreInputs) {
        setInputs({ ...parsed.inputs });
        onPresetChange(parsed.preset_id);
      }
      setResultError(null);
      void loadRecentJobs();
    } catch (reason: unknown) {
      if (
        (reason as { name?: string }).name === "AbortError"
        || token !== runTokenRef.current
        || requestId !== resultRequestRef.current
      ) return;
      setResultError(reason instanceof Error ? reason.message : "Could not load concepts");
    } finally {
      if (token === runTokenRef.current && requestId === resultRequestRef.current) {
        resultInFlightRef.current = false;
        setResultLoading(false);
      }
    }
  }, [apiBaseUrl, loadRecentJobs, onPresetChange]);

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
      if (!response.ok) throw await errorFromResponse(response, "Could not read run status");
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
        if (latest.status === "failed") setRunError(latest.error ?? "Search failed");
        if (latest.status === "interrupted") {
          setRunError(latest.error ?? "This run was interrupted by a restart. Generate again to start a new run.");
        }
        return;
      }
      pollTimerRef.current = window.setTimeout(() => void poll(jobId, token), POLL_INTERVAL_MS);
    } catch (reason: unknown) {
      if ((reason as { name?: string }).name === "AbortError" || token !== runTokenRef.current) return;
      pollFailuresRef.current += 1;
      if (pollFailuresRef.current >= 3) {
        stopTransport();
        setRunError(reason instanceof Error ? reason.message : "Could not read run status");
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
          setRunError("This run was interrupted by a restart. Generate again to start a new run.");
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
      if (!response.ok) throw await errorFromResponse(response, "Could not start search");
      const created = parseDemoJob(await response.json());
      if (token !== runTokenRef.current) return;
      setJob(created);
      connectEventStream(created, token);
    } catch (reason: unknown) {
      if ((reason as { name?: string }).name === "AbortError" || token !== runTokenRef.current) return;
      setRunError(reason instanceof Error ? reason.message : "Could not start search");
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
      if (!response.ok) throw await errorFromResponse(response, "Could not stop search");
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
      setRunError(reason instanceof Error ? reason.message : "Could not stop search");
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
      if (!response.ok) throw await errorFromResponse(response, "Could not load saved run status");
      const latest = parseDemoJob(await response.json());
      if (token !== runTokenRef.current || latest.id !== summary.id) return;
      setJob(latest);
      if (latest.status === "succeeded") {
        await loadResult(latest.id, token, 0, true, true);
      } else if (latest.status === "interrupted") {
        setRunError(latest.error ?? "This run was interrupted. Generate again to start a new run.");
      } else {
        setRunError(`Saved run status: ${jobStatusLabel(latest.status)}. Only completed results can be reopened.`);
      }
    } catch (reason: unknown) {
      if (token !== runTokenRef.current) return;
      setRunError(reason instanceof Error ? reason.message : "Could not reopen saved run");
    }
  }, [apiBaseUrl, invalidateRun, loadResult, running, submitting]);

  const analyzeCandidate = useCallback((candidate: DemoCandidate) => {
    if (!result) return;
    try {
      onAnalyzeCandidate(demoAnalyzeHandoff(result, candidate));
    } catch (reason: unknown) {
      setRunError(reason instanceof Error ? reason.message : "Could not open this concept in Analyze");
    }
  }, [onAnalyzeCandidate, result]);

  return (
    <section className={styles.panel} aria-labelledby="mission-demo-title">
      <header className={styles.hero}>
        <div>
          <h2 id="mission-demo-title">Design an aircraft</h2>
          <p>
            Set a mission. Explore up to three aircraft concepts.
          </p>
        </div>
      </header>

      {configError && (
        <div className={styles.errorBanner} role="alert">
          <div><strong>Search settings unavailable</strong><span>{configError}</span></div>
          <button type="button" onClick={() => setConfigAttempt((attempt) => attempt + 1)}>Retry</button>
        </div>
      )}

      {!config && !configError && <div className={styles.loading}>Loading search settings…</div>}

      {manifest && manifest.family_id !== DEMO_FAMILY_ID && (
        <div className={styles.unsupported} role="status">
          <strong>{manifest.display_name} is not supported by mission search yet</strong>
          <span>Mission search currently supports conventional aircraft. Use Analyze to explore blended-wing configurations.</span>
        </div>
      )}

      {(selectionMismatch || inputsMismatch) && runFamilyId && runPresetId && (
        <div className={styles.selectionMismatch} role="status">
          <strong>{selectionMismatch ? "Aircraft type changed" : "Mission changed"}</strong>
          <span>
            {selectionMismatch && (
              <>These results belong to <b>{runFamilyId}</b> / <b>{runPresetId}</b>. Generate again to apply your new selection.</>
            )}
            {selectionMismatch && inputsMismatch && " "}
            {inputsMismatch && "These results use your previous inputs. Generate again to apply the changes."}
          </span>
        </div>
      )}

      <div className={styles.workspace}>
        <aside className={styles.inputPane} aria-label="Mission inputs">
          <div className={styles.paneHeading}>
            <h3>Your mission</h3>
          </div>

          <fieldset className={styles.taskTypeGroup} disabled={!manifest || running || submitting}>
            <legend>Aircraft type</legend>
            <div className={styles.taskTypeCards}>
              {manifest?.presets.map((preset) => {
                const presentation = TASK_PRESENTATION[preset.preset_id];
                const active = selectedPresetId === preset.preset_id;
                return (
                  <button
                    key={preset.preset_id}
                    type="button"
                    className={styles.taskTypeCard}
                    aria-pressed={active}
                    onClick={() => onPresetChange(preset.preset_id)}
                  >
                    <strong>{presentation?.label ?? preset.label}</strong>
                    <span>{presentation?.description ?? preset.description}</span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className={styles.basicInputs} disabled={!config || running || submitting}>
            <legend>Requirements</legend>
            {groupedInputs.requirement.map((definition) => (
              <DemoNumericControl
                key={definition.key}
                definition={definition}
                value={inputs[definition.key] ?? definition.default}
                disabled={!config || running || submitting}
                onChange={(value) => setInputs((current) => ({ ...current, [definition.key]: value }))}
              />
            ))}
          </fieldset>

          <details className={styles.advancedConstraints}>
            <summary>Advanced limits</summary>
            <fieldset disabled={!config || running || submitting}>
              <legend>Defaults are ready to use</legend>
              {groupedInputs.constraint.map((definition) => (
                <DemoNumericControl
                  key={definition.key}
                  definition={definition}
                  value={inputs[definition.key] ?? definition.default}
                  disabled={!config || running || submitting}
                  onChange={(value) => setInputs((current) => ({ ...current, [definition.key]: value }))}
                />
              ))}
            </fieldset>
          </details>

          <div className={styles.actions} data-cancellable={running}>
            <button
              type="button"
              className={styles.runButton}
              disabled={!config || !supported || !selectedPresetId || running || submitting}
              onClick={() => void runDemo()}
            >
              {submitting ? "Starting…" : running ? "Generating…" : "Generate aircraft"}
            </button>
            {running && (
              <button
                type="button"
                className={styles.cancelButton}
                disabled={cancelling}
                onClick={() => void cancelDemo()}
              >
                {cancelling ? "Cancelling…" : "Cancel"}
              </button>
            )}
          </div>

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
                <strong id="mission-demo-recovery-title">Saved runs</strong>
                <small>Reopen an earlier result</small>
              </span>
              <b aria-hidden="true">{recoveryOpen ? "−" : "+"}</b>
            </button>
            {recoveryOpen && (
              <div className={styles.recoveryBody}>
                <div className={styles.recoveryPolicy}>
                  <span>{recoveryPolicy?.completed_queryable === false ? "Saved results unavailable" : "Completed results are available"}</span>
                  <span>Interrupted runs must be restarted</span>
                </div>
                {recentLoading && <p>Loading saved runs…</p>}
                {recentError && (
                  <div className={styles.recoveryError} role="alert">
                    <span>{recentError}</span>
                    <button type="button" onClick={() => void loadRecentJobs()}>Retry</button>
                  </div>
                )}
                {!recentLoading && !recentError && recentJobs.length === 0 && (
                  <p>No saved runs yet.</p>
                )}
                {recentJobs.length > 0 && (
                  <ul className={styles.recoveryList}>
                    {recentJobs.map((item) => (
                      <li key={item.id} data-status={item.status}>
                        <div>
                          <strong>{TASK_PRESENTATION[item.preset_id]?.label ?? item.preset_id}</strong>
                          <small title={item.id}>{compactId(item.id)} · {jobStatusLabel(item.status)}</small>
                        </div>
                        {item.status === "succeeded" ? (
                          <button
                            type="button"
                            disabled={resultLoading || running || submitting}
                            onClick={() => void recoverCompletedJob(item)}
                          >
                            Open
                          </button>
                        ) : (
                          <span>{item.status === "interrupted" ? "Restart required" : "Unavailable"}</span>
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
          {job && !result && <div className={styles.runStatus} aria-live="polite">
            <div className={styles.statusHeader}>
              <div>
                <h3>{job ? stageLabel(job.stage) : "Ready to generate"}</h3>
              </div>
              {job && <strong>{Math.round(job.progress * 100)}%</strong>}
            </div>
            <div
              className={styles.progressTrack}
              role="progressbar"
              aria-label="Aircraft generation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round((job?.progress ?? 0) * 100)}
            >
              <span style={{ width: `${Math.round((job?.progress ?? 0) * 100)}%` }} />
            </div>
            <div className={styles.statusMeta}>
              <span>
                {job
                  ? `${jobStatusLabel(job.status)} · ${TASK_PRESENTATION[job.preset_id]?.label ?? job.preset_id}`
                  : "Choose your requirements to begin"}
              </span>
              {transport === "sse" && <span>Live</span>}
              {transport === "polling" && <span>Reconnecting; checking progress</span>}
              {job?.status === "cancelled" && <span>Run cancelled</span>}
              {job?.status === "interrupted" && <span>Interrupted by restart; generate again</span>}
            </div>
          </div>}

          {runError && (
            <div className={styles.errorBanner} role="alert">
              <div><strong>Run interrupted</strong><span>{runError}</span></div>
              {job && (job.status === "queued" || job.status === "running") && (
                <button type="button" onClick={retryStatus}>Reconnect</button>
              )}
              {(!job || (job.status !== "queued" && job.status !== "running")) && (
                <button type="button" disabled={!config || !supported || submitting} onClick={() => void runDemo()}>
                  Try again
                </button>
              )}
            </div>
          )}

          {resultError && (
            <div className={styles.errorBanner} role="alert">
              <div><strong>Search finished, but results could not be loaded</strong><span>{resultError}</span></div>
              {job && (
                <button
                  type="button"
                  disabled={resultLoading}
                  onClick={() => void loadResult(job.id, runTokenRef.current, 0, true)}
                >
                  {resultLoading ? "Loading…" : "Reload results"}
                </button>
              )}
            </div>
          )}

          {!result && !resultLoading && !resultError && (
            <section className={styles.startingConcept} aria-label="Starting aircraft">
              <header>
                <div><h3>{running ? "Exploring concepts…" : "Starting concept"}</h3>
                  <p>{selectedPresetId ? TASK_PRESENTATION[selectedPresetId]?.label : "Aircraft preview"} · Adjust your mission, then generate.</p>
                </div>
                <span>Preview</span>
              </header>
              <div className={styles.previewFrame}>
                <ParametricAircraftPreview geometry={baselineGeometry} showScaleControls={false} />
              </div>
              <p className={styles.validationNote}>Concept estimates for exploration. Engineering validation is not included.</p>
            </section>
          )}
          {resultLoading && <div className={styles.loading}>Loading concepts…</div>}

          {result && (
            <>
              <section
                className={styles.outcomePanel}
                data-status={result.status}
                aria-label="Search results"
                role="status"
                aria-live="polite"
              >
                <div>
                  <strong>
                    {result.status === "no_valid_candidates"
                      ? "No valid concepts found"
                      : result.status === "no_feasible_solution_found"
                        ? "No concepts meet these requirements"
                        : `${topCandidates.length} ${topCandidates.length === 1 ? "concept" : "concepts"} ready to explore`}
                  </strong>
                  <p>
                    {feasibleShown} of {topCandidates.length} {feasibleShown === 1 ? "meets" : "meet"} modeled requirements.
                    {result.selection.outcome === "partial" && " Fewer distinct concepts were available in this run."}
                    {result.status === "no_feasible_solution_found" && " The first concept has the best score but still misses requirements."}
                    {result.status === "no_valid_candidates" && " No valid geometry is available to display."}
                  </p>
                </div>
                <span>Concept estimates</span>
              </section>

              {topCandidates.length > 0 ? (
                <>
                  <section className={styles.candidateChooser} aria-labelledby="candidate-chooser-title">
                    <div className={styles.candidateToolbar}>
                      <div>
                        <span>CONCEPTS</span>
                        <h3 id="candidate-chooser-title">Explore concepts</h3>
                      </div>
                      <div className={styles.viewSwitch} aria-label="Concept view">
                        <button type="button" aria-pressed={sameScale}
                          title={sameScale ? "Fit the selected aircraft to the view" : "Compare candidates at the same physical scale"}
                          onClick={() => setSameScale((current) => !current)}>
                          {sameScale ? "Same scale" : "Fit aircraft"}
                        </button>
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
                    <div className={styles.candidateChoices}>
                      {topCandidates.map((candidate) => (
                        <button
                          key={candidate.candidate_id}
                          type="button"
                          className={styles.candidateChoice}
                          aria-pressed={selectedCandidate?.candidate_id === candidate.candidate_id}
                          onClick={() => setSelectedCandidateId(candidate.candidate_id)}
                        >
                          <span>
                            <strong>{candidate.rank === 1 && candidate.feasible ? "Recommended" : `Concept ${candidate.rank}`}</strong>
                            <small>{candidate.feasible ? "Requirements met" : "Requirements not met"}</small>
                          </span>
                          <span className={styles.choiceMetrics}>
                            <small>{formatNumber(candidate.metrics.achieved_range_km, 0)} km</small>
                            <small>{formatNumber(candidate.metrics.takeoff_mass_kg, 0)} kg</small>
                            <small>L/D {formatNumber(candidate.metrics.max_lift_to_drag, 1)}</small>
                            <small>Fuel {formatNumber(candidate.metrics.fuel_mass_kg, 0)} kg</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>

                  {selectedCandidate && (
                    <div className={styles.selectedCandidate}>
                      <CandidateCard
                        candidate={selectedCandidate}
                        view={view}
                        sharedReferenceSize={sharedReferenceSize}
                        sharedFrame={sharedFrame}
                        sameScale={sameScale}
                        anyFeasible={topCandidates.some((item) => item.feasible)}
                        onAnalyze={analyzeCandidate}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className={styles.noCandidateState} role="status">
                  <strong>No geometry to display</strong>
                  <p>The search finished without valid geometry. See run details for evaluation errors.</p>
                </div>
              )}
            </>
          )}

          <details className={styles.runDetails}>
            <summary>Run details</summary>
            <div className={styles.runDetailsBody}>
              <dl className={styles.profileSummary}>
                <div><dt>Profile</dt><dd>{config ? `${config.profile_id} · v${config.profile_version}` : "Loading"}</dd></div>
                <div><dt>Status</dt><dd>{result?.formal_status ?? config?.formal_status ?? "—"}</dd></div>
                <div><dt>Seed</dt><dd>{result?.search.seed ?? profileNumber(config, "seed")}</dd></div>
                <div><dt>Budget</dt><dd>{config ? `${profileNumber(config, "iterations")} × ${profileNumber(config, "evaluations_per_iteration")}` : "—"}</dd></div>
                {job && <div><dt>Job</dt><dd title={job.id}>{compactId(job.id)}</dd></div>}
              </dl>
              {config?.disclaimer && <p className={styles.disclaimer}>{config.disclaimer}</p>}

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

                  <details className={styles.selectionPanel}>
                    <summary>
                      <span>Selection details</span>
                      <strong>{result.selection.decisions.length} items</strong>
                    </summary>
                    {result.selection.decisions.length === 0 ? (
                      <p>No valid candidate decisions were recorded.</p>
                    ) : (
                      <ul>
                        {result.selection.decisions.map((decision) => (
                          <li key={`${decision.candidate_id}-${decision.ranked_position}`} data-selected={decision.selected}>
                            <span>
                              #{decision.ranked_position} · {compactId(decision.candidate_id)} · {decision.feasible ? "Requirements met" : "Requirements not met"}
                            </span>
                            <strong title={decision.explanation ?? undefined}>
                              {decision.selected ? "Selected" : "Excluded"} · {selectionReason(decision.reason_code)}
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
                        <h3 id="coverage-title">Model coverage</h3>
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
                          <p>{metric.reason || metric.source || "No details available"}</p>
                          <small>{metric.used_in_score ? "Used in score" : "Not used in score"}</small>
                        </details>
                      ))}
                    </div>
                  </section>

                  {(result.warnings.length > 0 || Object.keys(result.provenance).length > 0) && (
                    <footer className={styles.provenance}>
                      <div>
                        <strong>Warnings</strong>
                        {result.warnings.length > 0
                          ? result.warnings.map((warning) => <p key={warning}>{warning}</p>)
                          : <p>No run-level warnings.</p>}
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
          </details>
        </div>
      </div>
    </section>
  );
}
