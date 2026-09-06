import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  framingReferenceSize,
  geometryFuselageLength,
  geometryNominalSize,
  modelScaleForMode,
  orthographicFrustum,
  perspectiveFitDistance,
  PREVIEW_DIRECTION,
  sharedGeometryFrame,
} from "./cameraFraming.ts";
import type { GeometryState } from "./types.ts";

const GEOMETRY: GeometryState = {
  family_id: "conventional_v2",
  geometry_version: "test",
  geometry_status: "valid",
  derived_metrics: { fuselage_length_m: 10, span_m: 20 },
  components: [
    {
      id: "body",
      kind: "loft_body",
      stations: [
        { x_m: 0, width_m: 0.1, height_m: 0.1, z_offset_m: 0, shape_exponent: 2 },
        { x_m: 10, width_m: 0.1, height_m: 0.1, z_offset_m: 0, shape_exponent: 2 },
      ],
    },
  ],
};

test("perspective framing keeps every aircraft corner on screen in wide and narrow viewports", () => {
  for (const aspect of [0.45, 1, 2.4, 3.5]) {
    for (const size of [[12, 28, 3], [25, 10, 5], [3, 3, 8]]) {
      const camera = new THREE.PerspectiveCamera(34, aspect, 0.001, 1000);
      camera.up.set(0, 0, 1);
      camera.position.copy(new THREE.Vector3(...PREVIEW_DIRECTION).normalize())
        .multiplyScalar(perspectiveFitDistance(size, aspect));
      camera.lookAt(0, 0, 0);
      camera.updateMatrixWorld();
      for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
        const projected = new THREE.Vector3(x * size[0] / 2, y * size[1] / 2, z * size[2] / 2).project(camera);
        assert.ok(Math.abs(projected.x) < 1 && Math.abs(projected.y) < 1, `Aircraft clipped at aspect ${aspect}`);
        assert.ok(projected.z > -1 && projected.z < 1);
      }
    }
  }
});

test("shared framing contains actual geometry even when declared dimensions are stale", () => {
  const first = { ...GEOMETRY, derived_metrics: { span_m: 1, fuselage_length_m: 1 } };
  const frame = sharedGeometryFrame([first]);
  assert.ok(frame);
  assert.equal(frame.min[0], 0);
  assert.equal(frame.max[0], 10);
  assert.ok(frame.max[1] > 0 && frame.min[1] < 0);
  assert.equal(sharedGeometryFrame([]), undefined);
});

test("world and normalized framing preserve their intended scale contracts", () => {
  assert.equal(geometryFuselageLength(GEOMETRY), 10);
  assert.equal(geometryNominalSize(GEOMETRY), 20);
  assert.equal(modelScaleForMode(GEOMETRY, "world"), 1);
  assert.equal(modelScaleForMode(GEOMETRY, "normalized"), 0.1);
  assert.equal(framingReferenceSize(9, "auto", 40), 9);
  assert.equal(framingReferenceSize(9, "world", 40), 40);
  assert.equal(framingReferenceSize(0.9, "normalized", 2), 2);
});

test("orthographic framing fits the same reference square in wide and tall viewports", () => {
  const wide = orthographicFrustum(20, 2);
  const tall = orthographicFrustum(20, 0.5);
  assert.ok(Math.abs(wide.right - wide.left - 47.2) < 1e-9);
  assert.ok(Math.abs(wide.top - wide.bottom - 23.6) < 1e-9);
  assert.ok(Math.abs(tall.right - tall.left - 23.6) < 1e-9);
  assert.ok(Math.abs(tall.top - tall.bottom - 47.2) < 1e-9);
});

test("geometry size falls back to canonical component coordinates", () => {
  const withoutMetrics = { ...GEOMETRY, derived_metrics: {} };
  assert.equal(geometryFuselageLength(withoutMetrics), 10);
  assert.equal(geometryNominalSize(withoutMetrics), 10);
});

test("tailless geometry normalizes by its canonical longitudinal envelope", () => {
  const bwb: GeometryState = {
    family_id: "bwb_v1",
    geometry_version: "test",
    geometry_status: "valid",
    components: [{
      id: "bwb",
      kind: "lifting_surface",
      symmetry: "y",
      sections: [
        { y_m: 0, leading_edge_x_m: -1, leading_edge_z_m: 0, chord_m: 8, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.15, airfoil_id: "symmetric" },
        { y_m: 7, leading_edge_x_m: 4, leading_edge_z_m: 0, chord_m: 1, twist_deg: -2, dihedral_deg: 0, thickness_ratio: 0.09, airfoil_id: "symmetric" },
      ],
    }],
  };
  assert.equal(geometryFuselageLength(bwb), 8);
  assert.equal(modelScaleForMode(bwb, "normalized"), 0.125);
  assert.ok(geometryNominalSize(bwb) >= 14);
});
