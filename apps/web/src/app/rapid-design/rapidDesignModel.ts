import type { BwbDesignVariables } from "@/components/rapid-design/BwbThreePreview";

export type WorkspaceTab = "analyze" | "optimize";

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

export type AnalyzeCondition = {
  altitudeM: number;
  speedKmh: number;
  alphaMinDeg: number;
  alphaMaxDeg: number;
  alphaSamples: number;
};

export type DomainCheck = {
  name: string;
  value: number;
  minimum: number;
  maximum: number;
  unit: string;
  status: string;
};

export type AnalyzeResponse = {
  family_id: string;
  design_hash: string;
  domain_status: { status: string; checks: DomainCheck[] };
  geometry: {
    reference_area_m2: number;
    span_m: number;
    semi_span_m: number;
    aspect_ratio: number;
    mean_aerodynamic_chord_m: number;
    wetted_area_m2: number;
    taper_ratio: number;
    volume_proxy_m3: number;
  };
  polar: {
    alpha_deg: number[];
    cl: number[];
    cd: number[];
    ld: number[];
  };
  summary: {
    reynolds_number: number;
    mach: number;
    cl_alpha_per_rad: number;
    cl_at_zero_alpha: number;
    cd0: number;
    induced_drag_factor: number;
    max_ld: number;
    alpha_at_max_ld_deg: number;
  };
  warnings: string[];
  provenance: {
    model_id: string;
    model_version: string;
    geometry_decoder_id: string;
    geometry_decoder_version: string;
    methodology: string;
    scope: string;
    uses_external_weights: boolean;
    uses_mit_assets: boolean;
  };
  fidelity: string;
};

export type NumericDefinition<Key extends string> = {
  key: Key;
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  step: number;
  digits: number;
};

export const DEFAULT_CONDITION: AnalyzeCondition = {
  altitudeM: 2000,
  speedKmh: 220,
  alphaMinDeg: -4,
  alphaMaxDeg: 12,
  alphaSamples: 33,
};

export const PLANFORM_FIELDS: ReadonlyArray<NumericDefinition<keyof BwbDesignVariables>> = [
  { key: "c1M", label: "中心弦长 c1", unit: "m", minimum: 2, maximum: 12, step: 0.1, digits: 1 },
  { key: "c2Ratio", label: "弦长比 c2/c1", unit: "ratio", minimum: 0.55, maximum: 0.95, step: 0.01, digits: 2 },
  { key: "c3Ratio", label: "弦长比 c3/c1", unit: "ratio", minimum: 0.25, maximum: 0.7, step: 0.01, digits: 2 },
  { key: "c4Ratio", label: "弦长比 c4/c1", unit: "ratio", minimum: 0.08, maximum: 0.35, step: 0.01, digits: 2 },
  { key: "b1Ratio", label: "内段展长 b1/c1", unit: "ratio", minimum: 0.15, maximum: 0.6, step: 0.01, digits: 2 },
  { key: "b2Ratio", label: "中段展长 b2/c1", unit: "ratio", minimum: 0.2, maximum: 0.8, step: 0.01, digits: 2 },
  { key: "b3Ratio", label: "外段展长 b3/c1", unit: "ratio", minimum: 0.3, maximum: 1.2, step: 0.01, digits: 2 },
  { key: "x3Ratio", label: "外段后移 x3/c1", unit: "ratio", minimum: 0, maximum: 0.8, step: 0.01, digits: 2 },
  { key: "sweepInnerDeg", label: "内翼后掠角", unit: "deg", minimum: 20, maximum: 55, step: 1, digits: 0 },
  { key: "sweepOuterDeg", label: "外翼后掠角", unit: "deg", minimum: 15, maximum: 45, step: 1, digits: 0 },
];

export const SECTION_FIELDS: ReadonlyArray<NumericDefinition<keyof BwbDesignVariables>> = [
  { key: "thicknessRatio", label: "相对厚度 t/c", unit: "ratio", minimum: 0.08, maximum: 0.18, step: 0.005, digits: 3 },
  { key: "twistTipDeg", label: "翼尖扭转角", unit: "deg", minimum: -6, maximum: 2, step: 0.25, digits: 2 },
];

export const CONDITION_FIELDS: ReadonlyArray<NumericDefinition<keyof AnalyzeCondition>> = [
  { key: "altitudeM", label: "飞行高度", unit: "m", minimum: 0, maximum: 11000, step: 100, digits: 0 },
  { key: "speedKmh", label: "真空速", unit: "km/h", minimum: 80, maximum: 500, step: 5, digits: 0 },
  { key: "alphaMinDeg", label: "最小迎角", unit: "deg", minimum: -10, maximum: 15, step: 0.5, digits: 1 },
  { key: "alphaMaxDeg", label: "最大迎角", unit: "deg", minimum: -5, maximum: 20, step: 0.5, digits: 1 },
  { key: "alphaSamples", label: "迎角采样数", unit: "pts", minimum: 5, maximum: 81, step: 2, digits: 0 },
];

export const GEOMETRY_METRICS = [
  ["reference_area_m2", "参考面积", "m²", 2],
  ["span_m", "全翼展", "m", 2],
  ["aspect_ratio", "展弦比", "", 2],
  ["mean_aerodynamic_chord_m", "平均气动弦", "m", 2],
  ["wetted_area_m2", "湿表面积", "m²", 2],
  ["taper_ratio", "梢根比", "", 3],
  ["volume_proxy_m3", "容积代理量", "m³", 2],
] as const;

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

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
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

export function designFieldBounds(
  field: NumericDefinition<keyof BwbDesignVariables>,
  design: BwbDesignVariables,
): { minimum: number; maximum: number } {
  if (field.key === "c2Ratio") {
    return { minimum: Math.max(field.minimum, design.c3Ratio + 0.01), maximum: field.maximum };
  }
  if (field.key === "c3Ratio") {
    return {
      minimum: Math.max(field.minimum, design.c4Ratio + 0.01),
      maximum: Math.min(field.maximum, design.c2Ratio - 0.01),
    };
  }
  if (field.key === "c4Ratio") {
    return { minimum: field.minimum, maximum: Math.min(field.maximum, design.c3Ratio - 0.01) };
  }
  return { minimum: field.minimum, maximum: field.maximum };
}

export function conditionFieldBounds(
  field: NumericDefinition<keyof AnalyzeCondition>,
  condition: AnalyzeCondition,
): { minimum: number; maximum: number } {
  if (field.key === "alphaMinDeg") {
    return { minimum: field.minimum, maximum: Math.min(field.maximum, condition.alphaMaxDeg - 0.5) };
  }
  if (field.key === "alphaMaxDeg") {
    return { minimum: Math.max(field.minimum, condition.alphaMinDeg + 0.5), maximum: field.maximum };
  }
  return { minimum: field.minimum, maximum: field.maximum };
}

export function toAnalyzePayload(design: BwbDesignVariables, condition: AnalyzeCondition) {
  return {
    family_id: "bwb_v1",
    design: {
      c1_m: design.c1M,
      c2_ratio: design.c2Ratio,
      c3_ratio: design.c3Ratio,
      c4_ratio: design.c4Ratio,
      b1_ratio: design.b1Ratio,
      b2_ratio: design.b2Ratio,
      b3_ratio: design.b3Ratio,
      x3_ratio: design.x3Ratio,
      sweep_inner_deg: design.sweepInnerDeg,
      sweep_outer_deg: design.sweepOuterDeg,
      thickness_ratio: design.thicknessRatio,
      twist_tip_deg: design.twistTipDeg,
    },
    condition: {
      altitude_m: condition.altitudeM,
      speed_kmh: condition.speedKmh,
      alpha_min_deg: condition.alphaMinDeg,
      alpha_max_deg: condition.alphaMaxDeg,
      alpha_samples: condition.alphaSamples,
    },
  };
}
