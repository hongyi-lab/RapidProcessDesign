import type { GeometryState } from "@/components/rapid-design/geometry";

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
