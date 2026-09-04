import assert from "node:assert/strict";
import test from "node:test";

import {
  demoAnalyzeHandoff,
  demoInputsMismatch,
  demoRunUpdateMatches,
  demoSelectionMismatch,
  demoSharedReferenceSize,
  familyPreset,
  geometryMetricRows,
  initialConditionValues,
  initialDesignValues,
  parameterGroups,
  parseDemoConfig,
  parseDemoSearchResult,
  parseFamiliesResponse,
  preferredInitialFamily,
  topDemoCandidates,
  toAnalyzePayload,
  type FamilyManifest,
} from "./rapidDesignModel.ts";

const MANIFEST: FamilyManifest = {
  family_id: "conventional_v2",
  display_name: "Conventional Aircraft",
  description: "A family-neutral manifest fixture.",
  version: "2.0",
  default_preset_id: "utility",
  presets: [
    {
      preset_id: "utility",
      label: "Utility",
      description: "Payload-oriented preset.",
      design: { fuselage_length_m: 12.5 },
    },
  ],
  design_parameters: [
    {
      key: "fuselage_length_m",
      label: "Fuselage length",
      unit: "m",
      minimum: 8,
      maximum: 18,
      step: 0.1,
      default: 11,
      group: "geometry",
    },
    {
      key: "wing_span_m",
      label: "Wing span",
      unit: "m",
      minimum: 10,
      maximum: 24,
      step: 0.1,
      default: 16,
      group: "geometry",
    },
  ],
  condition_parameters: [
    {
      key: "altitude_m",
      label: "Altitude",
      unit: "m",
      minimum: 0,
      maximum: 11000,
      step: 100,
      default: 2000,
      group: "flight_condition",
    },
  ],
  capabilities: { geometry: true, analyze: true, optimize: false },
  analysis: {
    model_id: "clean_room_conventional_v2",
    fidelity: "conceptual_low_order",
    description: "Low-order conceptual analysis.",
  },
  optimization_status: "pending_teacher_decision",
};

test("manifest helpers apply the selected preset over parameter defaults", () => {
  assert.equal(familyPreset(MANIFEST)?.preset_id, "utility");
  assert.deepEqual(initialDesignValues(MANIFEST), {
    fuselage_length_m: 12.5,
    wing_span_m: 16,
  });
  assert.deepEqual(initialConditionValues(MANIFEST), { altitude_m: 2000 });
});

test("Analyze payload remains family-neutral and preserves snake_case manifest keys", () => {
  assert.deepEqual(
    toAnalyzePayload(
      "conventional_v2",
      "utility",
      { fuselage_length_m: 12.5, wing_span_m: 16 },
      { altitude_m: 2000 },
    ),
    {
      family_id: "conventional_v2",
      preset_id: "utility",
      design: { fuselage_length_m: 12.5, wing_span_m: 16 },
      condition: { altitude_m: 2000 },
    },
  );
});

test("manifest parser rejects missing collections and accepts full family lists", () => {
  assert.deepEqual(parseFamiliesResponse({ families: [MANIFEST] }), [MANIFEST]);
  assert.throws(() => parseFamiliesResponse({ families: [] }), /没有可用/);
  assert.throws(() => parseFamiliesResponse({ families: [{ family_id: "broken" }] }), /缺少必要字段/);
});

test("the workbench prefers conventional_v2 for its richer preset entry point", () => {
  const bwb = { ...MANIFEST, family_id: "bwb_v1", display_name: "BWB" };
  assert.equal(preferredInitialFamily([bwb, MANIFEST])?.family_id, "conventional_v2");
  assert.equal(preferredInitialFamily([bwb])?.family_id, "bwb_v1");
  assert.equal(preferredInitialFamily([]), null);
});

test("controls group by manifest group and geometry metrics get stable ordering", () => {
  const groups = parameterGroups([
    MANIFEST.design_parameters[0],
    MANIFEST.condition_parameters[0],
    MANIFEST.design_parameters[1],
  ]);
  assert.deepEqual(groups.map(({ group, definitions }) => [group, definitions.map(({ key }) => key)]), [
    ["geometry", ["fuselage_length_m", "wing_span_m"]],
    ["flight_condition", ["altitude_m"]],
  ]);

  const rows = geometryMetricRows({ custom_metric: 3, span_m: 14, reference_area_m2: 30 });
  assert.deepEqual(rows.map(({ key }) => key), ["reference_area_m2", "span_m", "custom_metric"]);
  assert.equal(rows[2].label, "Custom Metric");
});

const DEMO_COVERAGE = {
  metrics: [
    {
      key: "mission.takeoff_mass_kg",
      label: "Conceptual takeoff mass",
      unit: "kg",
      status: "connected",
      source: "demo mission model",
      reason: "Transparent estimate.",
      used_in_score: true,
    },
    {
      key: "structure.stress_and_buckling",
      label: "Structural stress and buckling",
      unit: "-",
      status: "not_connected",
      source: "unavailable",
      reason: "No structural solver is connected.",
      used_in_score: false,
    },
  ],
};

const DEMO_CONFIG_PAYLOAD = {
  schema_version: "1.0",
  profile_id: "mission_demo_v1",
  profile_version: "1.0.0",
  mode: "demo_only",
  formal_status: "pending_teacher_decision",
  title: "Mission Demo Search",
  description: "Deterministic concept search.",
  disclaimer: "DEMO / NOT FORMAL / UNAPPROVED ASSUMPTIONS.",
  supported_family_ids: ["conventional_v2"],
  candidate_count: 3,
  diversity_threshold: 0.18,
  inputs: [
    {
      key: "required_range_km",
      label: "Required range",
      unit: "km",
      minimum: 100,
      maximum: 3000,
      step: 50,
      default: 1000,
      kind: "requirement",
    },
  ],
  geometry_variables: [
    { key: "wing_span_m", label: "Wing span", unit: "m", minimum: 8, maximum: 30, step: 0.1 },
  ],
  sizing_variables: [
    { key: "fuel_mass_kg", label: "Fuel mass", unit: "kg", minimum: 25, maximum: 900, step: 5 },
  ],
  optimizer: { method: "seeded_uniform_search", seed: 2711 },
  mission_model: { reserve_fuel_fraction: 0.15 },
  metric_coverage: DEMO_COVERAGE,
};

function demoCandidate(rank: number, id: string, span: number) {
  return {
    rank,
    candidate_id: id,
    family_id: "conventional_v2",
    preset_id: "utility",
    feasible: rank === 1,
    objective: rank * 100,
    design: { wing_span_m: span, fuselage_length_m: 12 + rank },
    sizing: { fuel_mass_kg: 200 + rank },
    geometry_state: {
      family_id: "conventional_v2",
      geometry_version: "2.0",
      geometry_status: "valid",
      components: [],
      derived_metrics: { span_m: span, fuselage_length_m: 12 + rank },
    },
    design_hash: `hash-${id}`,
    condition: { altitude_m: 9999 },
    metrics: {
      takeoff_mass_kg: 1000 + rank,
      achieved_range_km: 1200 - rank,
      lift_to_drag: 15 + rank,
      fuel_mass_kg: 200 + rank,
    },
    constraints: [
      { key: "range", label: "Range", margin: 100, satisfied: true, unit: "km" },
    ],
    score_breakdown: {
      objective: rank * 100,
      normalized_takeoff_mass: 0.5,
      constraint_penalty: 0,
      constraint_violation: 0,
      terms: [{ metric_key: "mission.takeoff_mass_kg", contribution: 0.5 }],
    },
    analysis_summary: { max_ld: 16 + rank },
    domain_status: { status: "in_domain", checks: [] },
    warnings: [],
    provenance: { model_id: "mission-demo" },
  };
}

const DEMO_RESULT_PAYLOAD = {
  schema_version: "1.0",
  job_id: "demo-job-1",
  status: "feasible",
  mode: "demo",
  formal_status: "pending_teacher_decision",
  profile: { id: "mission_demo_v1", version: "1.0.0", hash: "profile-hash" },
  family_id: "conventional_v2",
  preset_id: "utility",
  inputs: { required_range_km: 1000 },
  condition: { altitude_m: 2000, speed_kmh: 220 },
  metric_coverage: DEMO_COVERAGE,
  ranking_rule: {
    feasible_first: true,
    primary: "objective_ascending",
    tie_breaker: "candidate_id",
    diversity: { method: "normalized_l1", threshold: 0.18, variables: ["wing_span_m"] },
  },
  search: {
    method: "seeded_uniform_search",
    seed: 2711,
    iterations: 3,
    evaluations: 24,
    invalid: 1,
    records: [],
  },
  candidates: [demoCandidate(2, "candidate-b", 24), demoCandidate(1, "candidate-a", 18)],
  warnings: ["Demo assumptions are unapproved."],
  provenance: { implementation: "clean_room" },
};

test("Demo config parser keeps the versioned profile and three-state metric coverage", () => {
  const parsed = parseDemoConfig(DEMO_CONFIG_PAYLOAD);
  assert.equal(parsed.profile_id, "mission_demo_v1");
  assert.deepEqual(parsed.metric_coverage.metrics.map(({ status }) => status), [
    "connected",
    "not_connected",
  ]);
  assert.throws(
    () => parseDemoConfig({
      ...DEMO_CONFIG_PAYLOAD,
      metric_coverage: {
        metrics: [{ ...DEMO_COVERAGE.metrics[1], used_in_score: true }],
      },
    }),
    /未接入指标不能参与/,
  );
});

test("Demo result parsing provides stable rank order and one shared world reference", () => {
  const parsed = parseDemoSearchResult(DEMO_RESULT_PAYLOAD);
  const top = topDemoCandidates(parsed.candidates);
  assert.deepEqual(top.map(({ candidate_id }) => candidate_id), ["candidate-a", "candidate-b"]);
  assert.equal(demoSharedReferenceSize(top, "world"), 24);
});

test("Demo Analyze handoff preserves candidate design and the result-level condition", () => {
  const parsed = parseDemoSearchResult(DEMO_RESULT_PAYLOAD);
  const candidate = topDemoCandidates(parsed.candidates)[0];
  const handoff = demoAnalyzeHandoff(parsed, candidate);
  assert.deepEqual(handoff, {
    familyId: "conventional_v2",
    presetId: "utility",
    candidateId: "candidate-a",
    design: { wing_span_m: 18, fuselage_length_m: 13 },
    condition: { altitude_m: 2000, speed_kmh: 220 },
  });
  assert.notEqual(handoff.design, candidate.design);
  assert.notEqual(handoff.condition, parsed.condition);
});

test("Demo run identity rejects stale tokens and events from a different job", () => {
  assert.equal(demoRunUpdateMatches(4, 4, "job-current", "job-current"), true);
  assert.equal(demoRunUpdateMatches(4, 3, "job-current", "job-current"), false);
  assert.equal(demoRunUpdateMatches(4, 4, "job-current", "job-old"), false);
});

test("Demo selection mismatch keeps an existing run attributed to its own family and preset", () => {
  assert.equal(
    demoSelectionMismatch("conventional_v2", "utility", "conventional_v2", "utility"),
    false,
  );
  assert.equal(
    demoSelectionMismatch("conventional_v2", "trainer", "conventional_v2", "utility"),
    true,
  );
  assert.equal(
    demoSelectionMismatch("bwb_v1", "baseline", "conventional_v2", "utility"),
    true,
  );
  assert.equal(demoSelectionMismatch("bwb_v1", "baseline", undefined, undefined), false);
});

test("Demo input mismatch distinguishes the current draft from completed run inputs", () => {
  assert.equal(demoInputsMismatch({ range_km: 1000 }, { range_km: 1000 }), false);
  assert.equal(demoInputsMismatch({ range_km: 1200 }, { range_km: 1000 }), true);
  assert.equal(demoInputsMismatch({ range_km: 1000, payload_kg: 50 }, { range_km: 1000 }), true);
  assert.equal(demoInputsMismatch({ range_km: 1200 }, null), false);
});
