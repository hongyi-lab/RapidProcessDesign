import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_BWB_DESIGN,
  buildBwbSurfaceData,
  normalizeBwbDesign,
  type BwbDesignVariables,
  type BwbGeometryMetrics,
  type BwbSurfaceData,
} from "./bwbGeometry.ts";

const EXTREME_BWB_DESIGN: BwbDesignVariables = {
  c1M: 6,
  c2Ratio: 0.55,
  c3Ratio: 0.25,
  c4Ratio: 0.08,
  b1Ratio: 0.15,
  b2Ratio: 0.8,
  b3Ratio: 1.2,
  x3Ratio: 0,
  sweepInnerDeg: 20,
  sweepOuterDeg: 15,
  thicknessRatio: 0.12,
  twistTipDeg: 0,
};

const KNOWN_SMOOTH_METRICS = [
  {
    design: DEFAULT_BWB_DESIGN,
    expected: {
      referenceAreaM2: 57.488283,
      spanM: 17.64,
      semiSpanM: 8.82,
      aspectRatio: 5.41274819,
      meanAerodynamicChordM: 3.929971,
      wettedAreaM2: 116.127898,
      taperRatio: 0.18,
      volumeProxyM3: 16.80899,
    },
  },
  {
    design: EXTREME_BWB_DESIGN,
    expected: {
      referenceAreaM2: 42.869631,
      spanM: 25.8,
      semiSpanM: 12.9,
      aspectRatio: 15.52707545,
      meanAerodynamicChordM: 2.395523,
      wettedAreaM2: 86.514229,
      taperRatio: 0.08,
      volumeProxyM3: 7.640522,
    },
  },
] as const;

function maximumAbsoluteZ(positions: Float32Array): number {
  let maximum = 0;
  for (let index = 2; index < positions.length; index += 3) {
    maximum = Math.max(maximum, Math.abs(positions[index]));
  }
  return maximum;
}

function coordinateDifference(left: Float32Array, right: Float32Array): number {
  assert.equal(left.length, right.length);
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference += Math.abs(left[index] - right[index]);
  }
  return difference;
}

function assertKnownMetrics(
  actual: BwbGeometryMetrics,
  expected: (typeof KNOWN_SMOOTH_METRICS)[number]["expected"],
): void {
  for (const [key, value] of Object.entries(expected)) {
    const actualValue = actual[key as keyof BwbGeometryMetrics];
    assert.ok(Math.abs(actualValue - value) < 1e-6, `${key}: ${actualValue} != ${value}`);
  }
}

function projectedPlanformArea(surface: BwbSurfaceData): number {
  let doubleCoveredArea = 0;
  for (let offset = 0; offset < surface.indices.length; offset += 3) {
    const first = surface.indices[offset] * 3;
    const second = surface.indices[offset + 1] * 3;
    const third = surface.indices[offset + 2] * 3;
    const twiceTriangleArea = Math.abs(
      (surface.positions[second] - surface.positions[first]) *
        (surface.positions[third + 1] - surface.positions[first + 1]) -
        (surface.positions[second + 1] - surface.positions[first + 1]) *
          (surface.positions[third] - surface.positions[first]),
    );
    doubleCoveredArea += 0.5 * twiceTriangleArea;
  }
  // A closed wing covers the planform once on top and once on the bottom. Tip
  // caps are perpendicular to x-y and contribute zero projected area.
  return doubleCoveredArea / 2;
}

function topologyFacts(surface: BwbSurfaceData): {
  boundaryEdges: number;
  nonManifoldEdges: number;
  zeroAreaTriangles: number;
} {
  const incidence = new Map<string, number>();
  let zeroAreaTriangles = 0;
  for (let offset = 0; offset < surface.indices.length; offset += 3) {
    const vertices = [
      surface.indices[offset],
      surface.indices[offset + 1],
      surface.indices[offset + 2],
    ];
    const point = (vertex: number) => {
      const start = vertex * 3;
      return [
        surface.positions[start],
        surface.positions[start + 1],
        surface.positions[start + 2],
      ] as const;
    };
    const a = point(vertices[0]);
    const b = point(vertices[1]);
    const c = point(vertices[2]);
    const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]] as const;
    const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]] as const;
    const cross = [
      ab[1] * ac[2] - ab[2] * ac[1],
      ab[2] * ac[0] - ab[0] * ac[2],
      ab[0] * ac[1] - ab[1] * ac[0],
    ];
    if (Math.hypot(...cross) <= 1e-10) zeroAreaTriangles += 1;

    for (const [left, right] of [
      [vertices[0], vertices[1]],
      [vertices[1], vertices[2]],
      [vertices[2], vertices[0]],
    ]) {
      const key = left < right ? `${left}:${right}` : `${right}:${left}`;
      incidence.set(key, (incidence.get(key) ?? 0) + 1);
    }
  }
  return {
    boundaryEdges: Array.from(incidence.values()).filter((count) => count === 1).length,
    nonManifoldEdges: Array.from(incidence.values()).filter((count) => count !== 2).length,
    zeroAreaTriangles,
  };
}

test("BWB loft produces finite indexed top and bottom surfaces", () => {
  const surface = buildBwbSurfaceData(DEFAULT_BWB_DESIGN);

  assert.ok(surface.positions.length > 10_000);
  assert.ok(surface.indices.length > 10_000);
  assert.ok(surface.outlinePositions.length > 100);
  assert.ok(Array.from(surface.positions).every(Number.isFinite));
  assert.ok(Array.from(surface.indices).every(Number.isFinite));
  assert.ok(Array.from(surface.outlinePositions).every(Number.isFinite));
  assert.ok(
    Array.from(surface.indices).every((index) => index < surface.positions.length / 3),
  );
  assert.ok(surface.metrics.referenceAreaM2 > 0);
  assert.ok(surface.metrics.spanM > 0);
  assert.ok(surface.metrics.aspectRatio > 0);
  assert.ok(surface.metrics.volumeProxyM3 > 0);
});

test("default and extreme smooth metrics match backend-known values", () => {
  for (const { design, expected } of KNOWN_SMOOTH_METRICS) {
    assertKnownMetrics(buildBwbSurfaceData(design).metrics, expected);
  }
});

test("reported area follows the actual smooth mesh projection within one percent", () => {
  for (const { design } of KNOWN_SMOOTH_METRICS) {
    const surface = buildBwbSurfaceData(design);
    const projectedArea = projectedPlanformArea(surface);
    const relativeDifference =
      Math.abs(projectedArea - surface.metrics.referenceAreaM2) /
      surface.metrics.referenceAreaM2;
    assert.ok(relativeDifference < 0.01, `area mismatch: ${relativeDifference}`);
  }
});

test("loft is a closed two-manifold without zero-area triangles", () => {
  for (const { design } of KNOWN_SMOOTH_METRICS) {
    const facts = topologyFacts(buildBwbSurfaceData(design));
    assert.equal(facts.boundaryEdges, 0);
    assert.equal(facts.nonManifoldEdges, 0);
    assert.equal(facts.zeroAreaTriangles, 0);
  }
});

test("span and chord variables change both coordinates and reference area", () => {
  const baseline = buildBwbSurfaceData(DEFAULT_BWB_DESIGN);
  const broaderTip = buildBwbSurfaceData({
    ...DEFAULT_BWB_DESIGN,
    b3Ratio: 1.05,
    c4Ratio: 0.3,
  });

  assert.ok(coordinateDifference(baseline.positions, broaderTip.positions) > 100);
  assert.notEqual(
    baseline.metrics.referenceAreaM2.toFixed(4),
    broaderTip.metrics.referenceAreaM2.toFixed(4),
  );
  assert.ok(broaderTip.metrics.spanM > baseline.metrics.spanM);
});

test("thickness, sweep, break position and tip twist deform the actual mesh", () => {
  const baseline = buildBwbSurfaceData(DEFAULT_BWB_DESIGN);
  const deformed = buildBwbSurfaceData({
    ...DEFAULT_BWB_DESIGN,
    x3Ratio: 0.65,
    sweepInnerDeg: 52,
    sweepOuterDeg: 42,
    thicknessRatio: 0.18,
    twistTipDeg: -6,
  });

  assert.ok(coordinateDifference(baseline.positions, deformed.positions) > 100);
  assert.ok(maximumAbsoluteZ(deformed.positions) > maximumAbsoluteZ(baseline.positions));
  assert.ok(deformed.metrics.maximumXM > baseline.metrics.maximumXM);
});

test("thickness and washout each affect their corresponding 3D coordinates", () => {
  const baseline = buildBwbSurfaceData(DEFAULT_BWB_DESIGN);
  const thick = buildBwbSurfaceData({
    ...DEFAULT_BWB_DESIGN,
    thicknessRatio: 0.18,
  });
  const washedOut = buildBwbSurfaceData({
    ...DEFAULT_BWB_DESIGN,
    twistTipDeg: -6,
  });
  const lastTopTip =
    ((washedOut.spanSections - 1) * washedOut.chordSections +
      washedOut.chordSections -
      1) *
      3;
  const baselineLastTopTip =
    ((baseline.spanSections - 1) * baseline.chordSections + baseline.chordSections - 1) * 3;

  assert.ok(maximumAbsoluteZ(thick.positions) > maximumAbsoluteZ(baseline.positions));
  assert.notEqual(
    washedOut.positions[lastTopTip + 2].toFixed(5),
    baseline.positions[baselineLastTopTip + 2].toFixed(5),
  );
});

test("invalid numbers are clamped without emitting NaN", () => {
  const normalized = normalizeBwbDesign({
    ...DEFAULT_BWB_DESIGN,
    c1M: Number.NaN,
    c2Ratio: Number.POSITIVE_INFINITY,
    c3Ratio: 0.7,
    c4Ratio: 0.35,
    b1Ratio: -30,
    thicknessRatio: 8,
  });
  const surface = buildBwbSurfaceData(normalized, { spanSections: 17, chordSections: 15 });

  assert.equal(normalized.c1M, DEFAULT_BWB_DESIGN.c1M);
  assert.ok(normalized.c2Ratio > normalized.c3Ratio);
  assert.ok(normalized.c3Ratio > normalized.c4Ratio);
  assert.ok(Array.from(surface.positions).every(Number.isFinite));
  assert.ok(Object.values(surface.metrics).every(Number.isFinite));
});
