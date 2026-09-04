import assert from "node:assert/strict";
import test from "node:test";

import {
  familyPreset,
  geometryMetricRows,
  initialConditionValues,
  initialDesignValues,
  parameterGroups,
  parseFamiliesResponse,
  preferredInitialFamily,
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
