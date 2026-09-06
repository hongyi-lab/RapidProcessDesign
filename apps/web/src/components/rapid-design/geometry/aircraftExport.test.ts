import assert from "node:assert/strict";
import test from "node:test";
import { binaryStl, createGeometryExport, exportSurfaces, facetedStep, geometryExportFilename } from "./aircraftExport.ts";
import type { GeometryState } from "./types";

const aircraft: GeometryState = {
  family_id: "conventional_v2", geometry_version: "0.1.0", geometry_status: "valid",
  components: [
    { id: "body", kind: "loft_body", stations: [
      { x_m: 0, width_m: 0.2, height_m: 0.2, z_offset_m: 0, shape_exponent: 2 },
      { x_m: 2, width_m: 1, height_m: 1, z_offset_m: 0, shape_exponent: 2 },
      { x_m: 4, width_m: 0.2, height_m: 0.2, z_offset_m: 0, shape_exponent: 2 },
    ] },
    { id: "propeller", kind: "propeller", symmetry: "none", center_x_m: -0.3,
      centerline_y_m: 0, center_z_m: 0, radius_m: 0.7, hub_radius_m: 0.1,
      hub_length_m: 0.3, blade_count: 3, blade_chord_m: 0.1, rotation_deg: 15 },
  ],
};

test("STL contains every component with finite unit normals and full-scale millimeter coordinates", () => {
  const surfaces = exportSurfaces(aircraft);
  const buffer = binaryStl(surfaces);
  const reader = new DataView(buffer);
  const triangles = reader.getUint32(80, true);
  assert.equal(triangles, surfaces.reduce((sum, surface) => sum + surface.indices.length / 3, 0));
  assert.equal(buffer.byteLength, 84 + 50 * triangles);
  let maxX = -Infinity;
  for (let triangle = 0; triangle < triangles; triangle += 1) {
    const offset = 84 + 50 * triangle;
    const normal = [0, 1, 2].map((axis) => reader.getFloat32(offset + 4 * axis, true));
    assert.ok(Math.abs(Math.hypot(...normal) - 1) < 1e-6);
    for (let vertex = 0; vertex < 3; vertex += 1) {
      maxX = Math.max(maxX, reader.getFloat32(offset + 12 + vertex * 12, true));
      for (let axis = 0; axis < 3; axis += 1) {
        assert.ok(Number.isFinite(reader.getFloat32(offset + 12 + vertex * 12 + axis * 4, true)));
      }
    }
    assert.equal(reader.getUint16(offset + 48, true), 0);
  }
  assert.equal(maxX, 4000, "A four-meter model must export at 4000 mm, independent of camera scale");
});

test("STEP supplies planar faces, separate closed solids and explicit millimeter units", () => {
  const surfaces = exportSurfaces(aircraft);
  const step = facetedStep(surfaces, "Aircraft 'A'");
  assert.ok(step.startsWith("ISO-10303-21;\nHEADER;"));
  assert.ok(step.endsWith("END-ISO-10303-21;\n"));
  assert.match(step, /FILE_SCHEMA\(\('CONFIG_CONTROL_DESIGN'\)\)/);
  assert.match(step, /SI_UNIT\(\.MILLI\.,\.METRE\.\)/);
  assert.match(step, /Aircraft ''A''/);
  assert.equal((step.match(/=FACETED_BREP\(/g) ?? []).length, surfaces.length);
  assert.equal((step.match(/=CLOSED_SHELL\(/g) ?? []).length, surfaces.length);
  const triangles = surfaces.reduce((sum, surface) => sum + surface.indices.length / 3, 0);
  assert.equal((step.match(/=FACE_SURFACE\(/g) ?? []).length, triangles);
  assert.equal((step.match(/=PLANE\(/g) ?? []).length, triangles);
  const defined = new Set([...step.matchAll(/^#(\d+)=/gm)].map((match) => match[1]));
  for (const reference of step.matchAll(/#(\d+)/g)) assert.ok(defined.has(reference[1]));
  assert.doesNotMatch(step, /NaN|Infinity/);
});

test("changing the selected geometry changes the exported model without mutating inputs", async () => {
  const original = JSON.stringify(aircraft);
  const bodyOnly = { ...aircraft, components: [aircraft.components[0]] };
  const full = createGeometryExport(aircraft, "full", "stl");
  const body = createGeometryExport(bodyOnly, "body", "stl");
  assert.ok(full.size > body.size);
  const step = createGeometryExport(bodyOnly, "body", "step");
  assert.equal(step.type, "application/step");
  assert.doesNotMatch(await step.text(), /FACETED_BREP\('propeller/);
  assert.equal(JSON.stringify(aircraft), original);
});

test("invalid, empty and partially unbuildable geometry cannot produce a misleading download", () => {
  assert.throws(() => exportSurfaces({ ...aircraft, geometry_status: "invalid" }), /valid geometry/);
  assert.throws(() => exportSurfaces({ ...aircraft, components: [] }), /valid geometry/);
  assert.throws(() => exportSurfaces({ ...aircraft, components: [
    ...aircraft.components, { id: "missing", kind: "loft_body", stations: [] },
  ] }), /could not be exported/);
});

test("download names are safe and identify the format and STL scale", () => {
  assert.equal(geometryExportFilename("../Aircraft: 01", "step"), "Aircraft-01-mm.step");
  assert.equal(geometryExportFilename("", "stl"), "aircraft-mm.stl");
});
