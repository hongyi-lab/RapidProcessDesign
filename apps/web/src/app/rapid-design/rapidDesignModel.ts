import type {
  GeometryScaleMode,
  GeometryState,
} from "@/components/rapid-design/geometry";
import {
  geometryNominalSize,
  modelScaleForMode,
} from "../../components/rapid-design/geometry/cameraFraming.ts";

export type WorkspaceTab = "analyze" | "mission" | "legacy";

export type FamilyParameterDefinition = {
  key: string;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  step: number;
  default: number;
  group: string;
};

export type FamilyPreset = {
  preset_id: string;
  label: string;
  description: string;
  design: Record<string, number>;
  archetype_id?: string | null;
  reference_basis?: Record<string, string | number> | null;
};

export type FamilyManifest = {
  family_id: string;
  display_name: string;
  description: string;
  version: string;
  default_preset_id: string | null;
  presets: FamilyPreset[];
  design_parameters: FamilyParameterDefinition[];
  condition_parameters: FamilyParameterDefinition[];
  capabilities: {
    geometry: boolean;
    analyze: boolean;
    optimize: boolean;
  };
  analysis: {
    model_id: string;
    fidelity: string;
    description: string;
  };
  optimization_status: string;
};

export type FamiliesResponse = {
  families: FamilyManifest[];
};

export type DesignValues = Record<string, number>;
export type ConditionValues = Record<string, number>;

export type InputDefinition = {
  key: string;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  step: number;
  default: number;
  kind: "requirement" | "constraint";
};

export type DesignVariable = {
  key: string;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
};

export type RapidConfig = {
  title: string;
  description: string;
  inputs: InputDefinition[];
  design_variables: DesignVariable[];
  aerodynamics: { backend: string; model_size: string };
};

export type RapidJob = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  error: string | null;
};

export type ConstraintResult = {
  name: string;
  label: string;
  value: number;
  limit: number;
  margin: number;
  unit: string;
  relation: string;
  satisfied: boolean;
};

export type ConvergencePoint = {
  iteration: number;
  takeoff_mass_kg: number;
  feasible: boolean;
};

export type RapidResult = {
  status: "feasible" | "no_feasible_solution_found";
  feasible: boolean;
  design: Record<string, number>;
  metrics: Record<string, number>;
  constraints: ConstraintResult[];
  aircraft_spec: import("@/components/cad-viewer/previewGeometry").AircraftPreviewSpec;
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

export type DemoCoverageStatus = "connected" | "partial" | "not_connected";

export type DemoMetricCoverageItem = {
  key: string;
  label: string;
  unit: string;
  status: DemoCoverageStatus;
  source?: string | null;
  reason?: string | null;
  used_in_score: boolean;
};

export type DemoMetricCoverage = {
  metrics: DemoMetricCoverageItem[];
};

export type DemoVariableDefinition = DesignVariable & {
  step: number;
  input_upper_bound?: string | null;
};

export type DemoProfileConfig = {
  schema_version: string;
  profile_id: string;
  profile_version: string;
  mode: "demo_only";
  formal_status: string;
  title: string;
  description: string;
  disclaimer: string;
  supported_family_ids: string[];
  candidate_count: number;
  diversity_threshold: number;
  inputs: InputDefinition[];
  geometry_variables: DemoVariableDefinition[];
  sizing_variables: DemoVariableDefinition[];
  optimizer: Record<string, unknown>;
  mission_model: Record<string, unknown>;
  metric_coverage: DemoMetricCoverage;
};

export type DemoJob = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  error: string | null;
  created_at?: string;
  updated_at?: string;
  mode: "demo";
  family_id: string;
  preset_id: string;
  profile_id: string;
  profile_version: string;
  formal_status: string;
};

export type DemoScoreTerm = {
  metric_key?: string;
  label?: string;
  value?: number;
  normalized_value?: number;
  contribution?: number;
  weight?: number;
  [key: string]: unknown;
};

export type DemoScoreBreakdown = {
  objective: number;
  normalized_takeoff_mass: number;
  constraint_penalty: number;
  constraint_violation: number;
  terms: DemoScoreTerm[];
};

export type DemoConstraint = {
  key?: string;
  name?: string;
  label?: string;
  metric_key?: string;
  actual?: number;
  value?: number;
  limit?: number;
  margin?: number;
  violation?: number;
  unit?: string;
  relation?: string;
  operator?: string;
  satisfied?: boolean;
  [key: string]: unknown;
};

export type DemoCandidate = {
  rank: number;
  candidate_id: string;
  family_id: string;
  preset_id: string;
  feasible: boolean;
  objective: number;
  design: DesignValues;
  sizing: Record<string, number>;
  geometry_state: GeometryState;
  design_hash: string;
  condition: ConditionValues;
  metrics: Record<string, number>;
  constraints: DemoConstraint[];
  score_breakdown: DemoScoreBreakdown;
  analysis_summary: AnalyzeSummary;
  domain_status: { status: string; checks: DomainCheck[] };
  warnings: string[];
  provenance: Record<string, unknown>;
};

export type DemoSearchResult = {
  schema_version: string;
  job_id: string;
  status: "feasible" | "no_feasible_solution_found";
  mode: "demo";
  formal_status: string;
  profile: { id: string; version: string; hash: string };
  family_id: string;
  preset_id: string;
  inputs: Record<string, number>;
  condition: ConditionValues;
  metric_coverage: DemoMetricCoverage;
  ranking_rule: {
    feasible_first: boolean;
    primary: string;
    tie_breaker: string;
    diversity: { method: string; threshold: number; variables: string[] };
  };
  search: {
    method: string;
    seed: number;
    iterations: number;
    evaluations: number;
    invalid: number;
    records: unknown[];
  };
  candidates: DemoCandidate[];
  warnings: string[];
  provenance: Record<string, unknown>;
};

export type DemoAnalyzeHandoff = {
  familyId: string;
  presetId: string;
  candidateId: string;
  design: DesignValues;
  condition: ConditionValues;
};

export type DomainCheck = {
  name: string;
  value: number;
  minimum: number;
  maximum: number;
  unit: string;
  status: string;
};

export type AnalyzePolar = {
  alpha_deg: number[];
  cl: number[];
  cd: number[];
  ld: number[];
};

export type AnalyzeSummary = Record<string, number> & {
  max_ld?: number;
  alpha_at_max_ld_deg?: number;
};

export type AnalyzeEnvelope = {
  family_id: string;
  preset_id?: string | null;
  design_hash: string;
  geometry_state: GeometryState;
  geometry_metrics: Record<string, number>;
  analysis: {
    polar: AnalyzePolar;
    summary: AnalyzeSummary;
  };
  domain_status: { status: string; checks: DomainCheck[] };
  warnings: string[];
  provenance: {
    model_id: string;
    model_version?: string;
    geometry_decoder_id?: string;
    geometry_decoder_version?: string;
    methodology?: string;
    scope?: string;
    uses_external_weights?: boolean;
    uses_mit_assets?: boolean;
  };
  fidelity: string;
  geometry?: Record<string, number>;
  polar?: AnalyzePolar;
  summary?: AnalyzeSummary;
};

export type GeometryMetricRow = {
  key: string;
  label: string;
  unit: string;
  digits: number;
  value: number;
};

export const OPTIMIZE_METRICS = [
  ["takeoff_mass_kg", "起飞质量", "kg"],
  ["achieved_range_km", "预计航程", "km"],
  ["lift_to_drag", "巡航 L/D", ""],
  ["fuel_mass_kg", "燃油质量", "kg"],
] as const;

export const STAGE_LABELS: Record<string, string> = {
  queued: "等待计算",
  initializing_surrogate: "载入代理模型",
  optimizing: "搜索可行设计",
  evaluating: "评估候选方案",
  completed: "计算完成",
  cancelling: "正在停止",
  cancelled: "已停止",
  failed: "计算失败",
};

const METRIC_PRESENTATION: Record<string, Omit<GeometryMetricRow, "key" | "value">> = {
  reference_area_m2: { label: "参考面积", unit: "m²", digits: 2 },
  wing_area_m2: { label: "机翼面积", unit: "m²", digits: 2 },
  span_m: { label: "全翼展", unit: "m", digits: 2 },
  semi_span_m: { label: "半翼展", unit: "m", digits: 2 },
  aspect_ratio: { label: "展弦比", unit: "", digits: 2 },
  mean_aerodynamic_chord_m: { label: "平均气动弦", unit: "m", digits: 2 },
  wetted_area_m2: { label: "湿表面积", unit: "m²", digits: 2 },
  taper_ratio: { label: "梢根比", unit: "", digits: 3 },
  volume_proxy_m3: { label: "容积代理量", unit: "m³", digits: 2 },
  fuselage_length_m: { label: "机身长度", unit: "m", digits: 2 },
  fuselage_max_width_m: { label: "机身最大宽度", unit: "m", digits: 2 },
  fuselage_max_height_m: { label: "机身最大高度", unit: "m", digits: 2 },
};

const METRIC_ORDER = [
  "reference_area_m2",
  "wing_area_m2",
  "span_m",
  "aspect_ratio",
  "mean_aerodynamic_chord_m",
  "fuselage_length_m",
  "wetted_area_m2",
  "volume_proxy_m3",
  "taper_ratio",
  "fuselage_max_width_m",
  "fuselage_max_height_m",
  "semi_span_m",
];

function humanizeKey(key: string): string {
  return key
    .replace(/_(m2|m3|m|deg|kg)$/i, "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function digitsForStep(step: number): number {
  if (!Number.isFinite(step) || step <= 0) return 2;
  const text = step.toString().toLowerCase();
  if (text.includes("e-")) return Math.min(6, Number(text.split("e-")[1]));
  return Math.min(6, text.includes(".") ? text.split(".")[1].length : 0);
}

export function isIntegerParameter(definition: FamilyParameterDefinition): boolean {
  return /(?:^|_)(?:samples|count|number)(?:_|$)/i.test(definition.key);
}

export function formatNumber(value: number | undefined, digits = 1): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export async function errorFromResponse(response: Response, fallback: string): Promise<Error> {
  const body = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  if (typeof body?.detail === "string") return new Error(body.detail);
  if (Array.isArray(body?.detail)) {
    const message = body.detail.map((item) => item.msg).filter(Boolean).join("；");
    if (message) return new Error(message);
  }
  return new Error(fallback);
}

export function familyPreset(
  manifest: FamilyManifest,
  presetId?: string | null,
): FamilyPreset | null {
  const requested = presetId ?? manifest.default_preset_id;
  return manifest.presets.find((preset) => preset.preset_id === requested)
    ?? manifest.presets[0]
    ?? null;
}

export function preferredInitialFamily(families: FamilyManifest[]): FamilyManifest | null {
  return families.find((manifest) => manifest.family_id === "conventional_v2")
    ?? families[0]
    ?? null;
}

export function initialDesignValues(
  manifest: FamilyManifest,
  presetId?: string | null,
): DesignValues {
  const values = Object.fromEntries(
    manifest.design_parameters.map((definition) => [definition.key, definition.default]),
  );
  const preset = familyPreset(manifest, presetId);
  for (const [key, value] of Object.entries(preset?.design ?? {})) {
    if (Number.isFinite(value) && manifest.design_parameters.some((definition) => definition.key === key)) {
      values[key] = value;
    }
  }
  return values;
}

export function initialConditionValues(manifest: FamilyManifest): ConditionValues {
  return Object.fromEntries(
    manifest.condition_parameters.map((definition) => [definition.key, definition.default]),
  );
}

export function parameterGroups(
  definitions: FamilyParameterDefinition[],
): Array<{ group: string; definitions: FamilyParameterDefinition[] }> {
  const groups = new Map<string, FamilyParameterDefinition[]>();
  for (const definition of definitions) {
    const key = definition.group || "parameters";
    groups.set(key, [...(groups.get(key) ?? []), definition]);
  }
  return Array.from(groups, ([group, groupedDefinitions]) => ({
    group,
    definitions: groupedDefinitions,
  }));
}

export function groupLabel(group: string): string {
  const labels: Record<string, string> = {
    geometry: "几何参数",
    flight_condition: "分析工况",
    planform: "平面形参数",
    fuselage: "机身参数",
    wing: "主翼参数",
    tail: "尾翼参数",
    propulsion: "推进布局",
  };
  return labels[group] ?? humanizeKey(group);
}

export function toAnalyzePayload(
  familyId: string,
  presetId: string | null,
  design: DesignValues,
  condition: ConditionValues,
) {
  return {
    family_id: familyId,
    ...(presetId ? { preset_id: presetId } : {}),
    design,
    condition,
  };
}

export function geometryMetricRows(metrics: Record<string, number>): GeometryMetricRow[] {
  const keys = Object.keys(metrics).filter((key) => Number.isFinite(metrics[key]));
  keys.sort((left, right) => {
    const leftIndex = METRIC_ORDER.indexOf(left);
    const rightIndex = METRIC_ORDER.indexOf(right);
    if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
  return keys.map((key) => ({
    key,
    value: metrics[key],
    label: METRIC_PRESENTATION[key]?.label ?? humanizeKey(key),
    unit: METRIC_PRESENTATION[key]?.unit ?? "",
    digits: METRIC_PRESENTATION[key]?.digits ?? 2,
  }));
}

export function parseFamiliesResponse(payload: unknown): FamilyManifest[] {
  if (!payload || typeof payload !== "object" || !("families" in payload)) {
    throw new Error("Family manifest 响应格式无效");
  }
  const families = (payload as Partial<FamiliesResponse>).families;
  if (!Array.isArray(families) || families.length === 0) {
    throw new Error("没有可用的 aircraft family");
  }
  for (const manifest of families) {
    if (
      !manifest
      || typeof manifest.family_id !== "string"
      || typeof manifest.display_name !== "string"
      || !Array.isArray(manifest.design_parameters)
      || !Array.isArray(manifest.condition_parameters)
      || !Array.isArray(manifest.presets)
    ) {
      throw new Error("Family manifest 缺少必要字段");
    }
  }
  return families;
}

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 格式无效`);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} 缺少必要字段`);
  }
  return value;
}

function numberValue(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} 必须是有限数值`);
  }
  return value;
}

function booleanValue(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} 必须是布尔值`);
  return value;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${label} 格式无效`);
  }
  return [...value];
}

function numericRecord(value: unknown, label: string): Record<string, number> {
  const record = objectValue(value, label);
  const entries = Object.entries(record);
  if (entries.some(([, item]) => typeof item !== "number" || !Number.isFinite(item))) {
    throw new Error(`${label} 只能包含有限数值`);
  }
  return Object.fromEntries(entries) as Record<string, number>;
}

function parseCoverage(value: unknown): DemoMetricCoverage {
  const record = objectValue(value, "metric_coverage");
  if (!Array.isArray(record.metrics)) throw new Error("metric_coverage.metrics 格式无效");
  const statuses: DemoCoverageStatus[] = ["connected", "partial", "not_connected"];
  return {
    metrics: record.metrics.map((raw, index) => {
      const item = objectValue(raw, `metric_coverage.metrics[${index}]`);
      const status = stringValue(item.status, `metric_coverage.metrics[${index}].status`);
      if (!statuses.includes(status as DemoCoverageStatus)) {
        throw new Error(`metric_coverage.metrics[${index}].status 无效`);
      }
      const usedInScore = booleanValue(
        item.used_in_score,
        `metric_coverage.metrics[${index}].used_in_score`,
      );
      if (status === "not_connected" && usedInScore) {
        throw new Error("未接入指标不能参与 Demo 排名");
      }
      return {
        key: stringValue(item.key, `metric_coverage.metrics[${index}].key`),
        label: stringValue(item.label, `metric_coverage.metrics[${index}].label`),
        unit: typeof item.unit === "string" ? item.unit : "",
        status: status as DemoCoverageStatus,
        source: typeof item.source === "string" ? item.source : null,
        reason: typeof item.reason === "string" ? item.reason : null,
        used_in_score: usedInScore,
      };
    }),
  };
}

function parseInputDefinitions(value: unknown): InputDefinition[] {
  if (!Array.isArray(value)) throw new Error("Demo inputs 格式无效");
  return value.map((raw, index) => {
    const item = objectValue(raw, `inputs[${index}]`);
    const kind = stringValue(item.kind, `inputs[${index}].kind`);
    if (kind !== "requirement" && kind !== "constraint") {
      throw new Error(`inputs[${index}].kind 无效`);
    }
    return {
      key: stringValue(item.key, `inputs[${index}].key`),
      label: stringValue(item.label, `inputs[${index}].label`),
      unit: typeof item.unit === "string" ? item.unit : "",
      minimum: numberValue(item.minimum, `inputs[${index}].minimum`),
      maximum: numberValue(item.maximum, `inputs[${index}].maximum`),
      step: numberValue(item.step, `inputs[${index}].step`),
      default: numberValue(item.default, `inputs[${index}].default`),
      kind,
    };
  });
}

function parseDemoVariables(value: unknown, label: string): DemoVariableDefinition[] {
  if (!Array.isArray(value) || value.length === 0) throw new Error(`${label} 格式无效`);
  return value.map((raw, index) => {
    const item = objectValue(raw, `${label}[${index}]`);
    return {
      key: stringValue(item.key, `${label}[${index}].key`),
      label: stringValue(item.label, `${label}[${index}].label`),
      unit: typeof item.unit === "string" ? item.unit : "",
      minimum: numberValue(item.minimum, `${label}[${index}].minimum`),
      maximum: numberValue(item.maximum, `${label}[${index}].maximum`),
      step: numberValue(item.step, `${label}[${index}].step`),
      input_upper_bound: typeof item.input_upper_bound === "string"
        ? item.input_upper_bound
        : null,
    };
  });
}

export function parseDemoConfig(payload: unknown): DemoProfileConfig {
  const record = objectValue(payload, "Demo config");
  if (record.mode !== "demo_only") throw new Error("Demo config mode 必须为 demo_only");
  return {
    schema_version: stringValue(record.schema_version, "schema_version"),
    profile_id: stringValue(record.profile_id, "profile_id"),
    profile_version: stringValue(record.profile_version, "profile_version"),
    mode: "demo_only",
    formal_status: stringValue(record.formal_status, "formal_status"),
    title: stringValue(record.title, "title"),
    description: stringValue(record.description, "description"),
    disclaimer: stringValue(record.disclaimer, "disclaimer"),
    supported_family_ids: stringArray(record.supported_family_ids, "supported_family_ids"),
    candidate_count: numberValue(record.candidate_count, "candidate_count"),
    diversity_threshold: numberValue(record.diversity_threshold, "diversity_threshold"),
    inputs: parseInputDefinitions(record.inputs),
    geometry_variables: parseDemoVariables(record.geometry_variables, "geometry_variables"),
    sizing_variables: parseDemoVariables(record.sizing_variables, "sizing_variables"),
    optimizer: objectValue(record.optimizer, "optimizer"),
    mission_model: objectValue(record.mission_model, "mission_model"),
    metric_coverage: parseCoverage(record.metric_coverage),
  };
}

const DEMO_JOB_STATUSES = ["queued", "running", "succeeded", "failed", "cancelled"] as const;

export function parseDemoJob(payload: unknown): DemoJob {
  const record = objectValue(payload, "Demo job");
  const status = stringValue(record.status, "Demo job status");
  if (!DEMO_JOB_STATUSES.includes(status as DemoJob["status"])) {
    throw new Error("Demo job status 无效");
  }
  if (record.mode !== "demo") throw new Error("Demo job mode 必须为 demo");
  return {
    id: stringValue(record.id, "Demo job id"),
    status: status as DemoJob["status"],
    progress: clamp(numberValue(record.progress, "Demo job progress"), 0, 1),
    stage: stringValue(record.stage, "Demo job stage"),
    error: typeof record.error === "string" ? record.error : null,
    created_at: typeof record.created_at === "string" ? record.created_at : undefined,
    updated_at: typeof record.updated_at === "string" ? record.updated_at : undefined,
    mode: "demo",
    family_id: stringValue(record.family_id, "Demo job family_id"),
    preset_id: stringValue(record.preset_id, "Demo job preset_id"),
    profile_id: stringValue(record.profile_id, "Demo job profile_id"),
    profile_version: stringValue(record.profile_version, "Demo job profile_version"),
    formal_status: stringValue(record.formal_status, "Demo job formal_status"),
  };
}

function parseDemoCandidate(value: unknown, index: number): DemoCandidate {
  const record = objectValue(value, `candidates[${index}]`);
  const score = objectValue(record.score_breakdown, `candidates[${index}].score_breakdown`);
  if (!Array.isArray(score.terms)) {
    throw new Error(`candidates[${index}].score_breakdown.terms 格式无效`);
  }
  if (!Array.isArray(record.constraints)) {
    throw new Error(`candidates[${index}].constraints 格式无效`);
  }
  const geometry = objectValue(record.geometry_state, `candidates[${index}].geometry_state`);
  if (
    typeof geometry.family_id !== "string"
    || typeof geometry.geometry_version !== "string"
    || !Array.isArray(geometry.components)
  ) {
    throw new Error(`candidates[${index}].geometry_state 缺少必要字段`);
  }
  const analysisSummary = numericRecord(
    record.analysis_summary,
    `candidates[${index}].analysis_summary`,
  );
  const domain = objectValue(record.domain_status, `candidates[${index}].domain_status`);
  if (!Array.isArray(domain.checks)) {
    throw new Error(`candidates[${index}].domain_status.checks 格式无效`);
  }
  return {
    rank: numberValue(record.rank, `candidates[${index}].rank`),
    candidate_id: stringValue(record.candidate_id, `candidates[${index}].candidate_id`),
    family_id: stringValue(record.family_id, `candidates[${index}].family_id`),
    preset_id: stringValue(record.preset_id, `candidates[${index}].preset_id`),
    feasible: booleanValue(record.feasible, `candidates[${index}].feasible`),
    objective: numberValue(record.objective, `candidates[${index}].objective`),
    design: numericRecord(record.design, `candidates[${index}].design`),
    sizing: numericRecord(record.sizing, `candidates[${index}].sizing`),
    geometry_state: record.geometry_state as GeometryState,
    design_hash: stringValue(record.design_hash, `candidates[${index}].design_hash`),
    condition: numericRecord(record.condition, `candidates[${index}].condition`),
    metrics: numericRecord(record.metrics, `candidates[${index}].metrics`),
    constraints: record.constraints.map((item, constraintIndex) => (
      objectValue(item, `candidates[${index}].constraints[${constraintIndex}]`) as DemoConstraint
    )),
    score_breakdown: {
      objective: numberValue(score.objective, `candidates[${index}].score_breakdown.objective`),
      normalized_takeoff_mass: numberValue(
        score.normalized_takeoff_mass,
        `candidates[${index}].score_breakdown.normalized_takeoff_mass`,
      ),
      constraint_penalty: numberValue(
        score.constraint_penalty,
        `candidates[${index}].score_breakdown.constraint_penalty`,
      ),
      constraint_violation: numberValue(
        score.constraint_violation,
        `candidates[${index}].score_breakdown.constraint_violation`,
      ),
      terms: score.terms.map((item, termIndex) => (
        objectValue(item, `candidates[${index}].score_breakdown.terms[${termIndex}]`) as DemoScoreTerm
      )),
    },
    analysis_summary: analysisSummary,
    domain_status: {
      status: stringValue(domain.status, `candidates[${index}].domain_status.status`),
      checks: domain.checks as DomainCheck[],
    },
    warnings: stringArray(record.warnings ?? [], `candidates[${index}].warnings`),
    provenance: objectValue(record.provenance, `candidates[${index}].provenance`),
  };
}

export function parseDemoSearchResult(payload: unknown): DemoSearchResult {
  const record = objectValue(payload, "Demo result");
  if (record.mode !== "demo") throw new Error("Demo result mode 必须为 demo");
  if (record.status !== "feasible" && record.status !== "no_feasible_solution_found") {
    throw new Error("Demo result status 无效");
  }
  const profile = objectValue(record.profile, "Demo result profile");
  const ranking = objectValue(record.ranking_rule, "Demo result ranking_rule");
  const diversity = objectValue(ranking.diversity, "Demo result ranking_rule.diversity");
  const search = objectValue(record.search, "Demo result search");
  if (!Array.isArray(record.candidates) || record.candidates.length === 0) {
    throw new Error("Demo result 没有候选方案");
  }
  if (!Array.isArray(search.records)) throw new Error("Demo result search.records 格式无效");
  const candidates = record.candidates.map(parseDemoCandidate);
  const result: DemoSearchResult = {
    schema_version: stringValue(record.schema_version, "schema_version"),
    job_id: stringValue(record.job_id, "job_id"),
    status: record.status,
    mode: "demo",
    formal_status: stringValue(record.formal_status, "formal_status"),
    profile: {
      id: stringValue(profile.id, "profile.id"),
      version: stringValue(profile.version, "profile.version"),
      hash: stringValue(profile.hash, "profile.hash"),
    },
    family_id: stringValue(record.family_id, "family_id"),
    preset_id: stringValue(record.preset_id, "preset_id"),
    inputs: numericRecord(record.inputs, "inputs"),
    condition: numericRecord(record.condition, "condition"),
    metric_coverage: parseCoverage(record.metric_coverage),
    ranking_rule: {
      feasible_first: booleanValue(ranking.feasible_first, "ranking_rule.feasible_first"),
      primary: stringValue(ranking.primary, "ranking_rule.primary"),
      tie_breaker: stringValue(ranking.tie_breaker, "ranking_rule.tie_breaker"),
      diversity: {
        method: stringValue(diversity.method, "ranking_rule.diversity.method"),
        threshold: numberValue(diversity.threshold, "ranking_rule.diversity.threshold"),
        variables: stringArray(diversity.variables, "ranking_rule.diversity.variables"),
      },
    },
    search: {
      method: stringValue(search.method, "search.method"),
      seed: numberValue(search.seed, "search.seed"),
      iterations: numberValue(search.iterations, "search.iterations"),
      evaluations: numberValue(search.evaluations, "search.evaluations"),
      invalid: numberValue(search.invalid, "search.invalid"),
      records: [...search.records],
    },
    candidates,
    warnings: stringArray(record.warnings ?? [], "warnings"),
    provenance: objectValue(record.provenance, "provenance"),
  };

  if (result.candidates.some((candidate) => (
    candidate.family_id !== result.family_id
    || candidate.preset_id !== result.preset_id
    || candidate.geometry_state.family_id !== result.family_id
  ))) {
    throw new Error("Demo 候选与结果 family/preset 不一致");
  }
  return result;
}

export function topDemoCandidates(
  candidates: readonly DemoCandidate[],
  limit = 3,
): DemoCandidate[] {
  return [...candidates]
    .sort((left, right) => left.rank - right.rank || left.candidate_id.localeCompare(right.candidate_id))
    .slice(0, Math.max(0, limit));
}

export function demoRunUpdateMatches(
  activeToken: number,
  updateToken: number,
  activeJobId: string,
  updateJobId: unknown,
): boolean {
  return activeToken === updateToken && activeJobId === updateJobId;
}

export function demoSelectionMismatch(
  selectedFamilyId: string | null | undefined,
  selectedPresetId: string | null | undefined,
  runFamilyId: string | null | undefined,
  runPresetId: string | null | undefined,
): boolean {
  if (!runFamilyId || !runPresetId) return false;
  return selectedFamilyId !== runFamilyId || selectedPresetId !== runPresetId;
}

export function demoInputsMismatch(
  draftInputs: Readonly<Record<string, number>>,
  runInputs: Readonly<Record<string, number>> | null | undefined,
): boolean {
  if (!runInputs) return false;
  const keys = new Set([...Object.keys(draftInputs), ...Object.keys(runInputs)]);
  return [...keys].some((key) => draftInputs[key] !== runInputs[key]);
}

export function demoSharedReferenceSize(
  candidates: readonly DemoCandidate[],
  scaleMode: GeometryScaleMode = "world",
): number {
  return Math.max(
    1,
    ...candidates.map((candidate) => (
      geometryNominalSize(candidate.geometry_state)
      * modelScaleForMode(candidate.geometry_state, scaleMode)
    )),
  );
}

export function demoAnalyzeHandoff(
  result: DemoSearchResult,
  candidate: DemoCandidate,
): DemoAnalyzeHandoff {
  if (!result.candidates.some((item) => item.candidate_id === candidate.candidate_id)) {
    throw new Error("候选方案不属于当前 Demo 结果");
  }
  return {
    familyId: candidate.family_id,
    presetId: candidate.preset_id,
    candidateId: candidate.candidate_id,
    design: { ...candidate.design },
    // Analyze must use the run-level mission condition returned by the backend.
    // It intentionally does not infer one from the current UI or from Demo scores.
    condition: { ...result.condition },
  };
}
