import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  buildGeometrySurfaces,
  buildLiftingSurface,
  buildLoftBodySurface,
  buildNacelleSurfaces,
  type SurfaceMeshData,
} from "./geometrySurfaces.ts";
import {
  disposeObjectResources,
  surfaceToBufferGeometry,
} from "./threeGeometry.ts";
import type {
  GeometryState,
  LiftingSurfaceComponent,
  LoftBodyComponent,
  NacelleComponent,
} from "./types.ts";

const BODY: LoftBodyComponent = {
  id: "fuselage",
  kind: "loft_body",
  stations: [
    { x_m: 0, width_m: 0.04, height_m: 0.04, z_offset_m: 0, shape_exponent: 2 },
    { x_m: 0.7, width_m: 0.72, height_m: 0.78, z_offset_m: 0.03, shape_exponent: 2.1 },
    { x_m: 2.1, width_m: 1.05, height_m: 1.12, z_offset_m: 0.04, shape_exponent: 2.5 },
    { x_m: 4.2, width_m: 1.12, height_m: 1.18, z_offset_m: 0.03, shape_exponent: 2.7 },
    { x_m: 6.1, width_m: 0.94, height_m: 0.98, z_offset_m: 0.08, shape_exponent: 2.4 },
    { x_m: 8.6, width_m: 0.58, height_m: 0.62, z_offset_m: 0.17, shape_exponent: 2.1 },
    { x_m: 10.8, width_m: 0.3, height_m: 0.34, z_offset_m: 0.25, shape_exponent: 2 },
    { x_m: 12, width_m: 0.035, height_m: 0.035, z_offset_m: 0.31, shape_exponent: 2 },
  ],
};

const MAIN_WING: LiftingSurfaceComponent = {
  id: "main-wing",
  kind: "lifting_surface",
  symmetry: "y",
  orientation: "horizontal",
  sections: [
    { y_m: 0, leading_edge_x_m: 3.1, leading_edge_z_m: 0.2, chord_m: 2.5, twist_deg: 1, dihedral_deg: 2, thickness_ratio: 0.14, airfoil_id: "naca2414" },
    { y_m: 2.2, leading_edge_x_m: 3.35, leading_edge_z_m: 0.27, chord_m: 2.05, twist_deg: 0, dihedral_deg: 2, thickness_ratio: 0.13, airfoil_id: "naca2413" },
    { y_m: 5.2, leading_edge_x_m: 4, leading_edge_z_m: 0.37, chord_m: 1.3, twist_deg: -1.2, dihedral_deg: 2, thickness_ratio: 0.11, airfoil_id: "naca2411" },
    { y_m: 8.4, leading_edge_x_m: 4.9, leading_edge_z_m: 0.48, chord_m: 0.64, twist_deg: -2.5, dihedral_deg: 2, thickness_ratio: 0.1, airfoil_id: "naca2410" },
  ],
};

const HORIZONTAL_TAIL: LiftingSurfaceComponent = {
  id: "horizontal-tail",
  kind: "lifting_surface",
  symmetry: "y",
  sections: [
    { y_m: 0, leading_edge_x_m: 9.25, leading_edge_z_m: 0.42, chord_m: 1.25, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.1, airfoil_id: "naca0010" },
    { y_m: 1.15, leading_edge_x_m: 9.55, leading_edge_z_m: 0.42, chord_m: 0.72, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.09, airfoil_id: "naca0009" },
    { y_m: 2.2, leading_edge_x_m: 9.95, leading_edge_z_m: 0.42, chord_m: 0.36, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.08, airfoil_id: "naca0008" },
  ],
};

const VERTICAL_TAIL: LiftingSurfaceComponent = {
  id: "vertical-tail",
  kind: "lifting_surface",
  symmetry: "none",
  orientation: "vertical",
  sections: [
    { y_m: 0, leading_edge_x_m: 8.8, leading_edge_z_m: 0.36, chord_m: 1.7, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.11, airfoil_id: "naca0011" },
    { y_m: 1.1, leading_edge_x_m: 9.2, leading_edge_z_m: 1.46, chord_m: 1.05, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.1, airfoil_id: "naca0010" },
    { y_m: 2.1, leading_edge_x_m: 9.65, leading_edge_z_m: 2.46, chord_m: 0.45, twist_deg: 0, dihedral_deg: 0, thickness_ratio: 0.08, airfoil_id: "naca0008" },
  ],
};

const NACELLES: NacelleComponent = {
  id: "wing-engines",
  kind: "nacelle",
  symmetry: "y",
  centerline_y_m: 2.75,
  stations: [
    { x_m: 3.4, radius_y_m: 0.04, radius_z_m: 0.04, z_offset_m: -0.38 },
    { x_m: 3.7, radius_y_m: 0.29, radius_z_m: 0.31, z_offset_m: -0.38 },
    { x_m: 4.65, radius_y_m: 0.34, radius_z_m: 0.35, z_offset_m: -0.36 },
    { x_m: 5.5, radius_y_m: 0.18, radius_z_m: 0.2, z_offset_m: -0.33 },
    { x_m: 5.8, radius_y_m: 0.035, radius_z_m: 0.035, z_offset_m: -0.31 },
  ],
};

const AIRCRAFT: GeometryState = {
  family_id: "conventional_v2",
  geometry_version: "0.1.0",
  geometry_status: "valid",
  components: [BODY, MAIN_WING, HORIZONTAL_TAIL, VERTICAL_TAIL, NACELLES],
};

function topology(surface: SurfaceMeshData): {
  boundaryEdges: number;
  nonManifoldEdges: number;
  zeroAreaTriangles: number;
} {
  const edgeCounts = new Map<string, number>();
  let zeroAreaTriangles = 0;
  const point = (vertex: number) => {
    const start = vertex * 3;
    return surface.positions.slice(start, start + 3);
  };
  for (let offset = 0; offset < surface.indices.length; offset += 3) {
    const vertices = [surface.indices[offset], surface.indices[offset + 1], surface.indices[offset + 2]];
    const [a, b, c] = vertices.map(point);
    const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const cross = [
      ab[1] * ac[2] - ab[2] * ac[1],
      ab[2] * ac[0] - ab[0] * ac[2],
      ab[0] * ac[1] - ab[1] * ac[0],
    ];
    if (Math.hypot(...cross) <= 1e-10) zeroAreaTriangles += 1;
    for (const [left, right] of [[vertices[0], vertices[1]], [vertices[1], vertices[2]], [vertices[2], vertices[0]]]) {
      const key = left < right ? `${left}:${right}` : `${right}:${left}`;
      edgeCounts.set(key, (edgeCounts.get(key) ?? 0) + 1);
    }
  }
  return {
    boundaryEdges: Array.from(edgeCounts.values()).filter((count) => count === 1).length,
    nonManifoldEdges: Array.from(edgeCounts.values()).filter((count) => count !== 2).length,
    zeroAreaTriangles,
  };
}

function coordinateDifference(left: Float32Array, right: Float32Array): number {
  assert.equal(left.length, right.length);
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference += Math.abs(left[index] - right[index]);
  }
  return difference;
}

function rangeForAxis(surface: SurfaceMeshData, axis: 0 | 1 | 2): [number, number] {
  const values: number[] = [];
  for (let index = axis; index < surface.positions.length; index += 3) values.push(surface.positions[index]);
  return [Math.min(...values), Math.max(...values)];
}

test("family-neutral GeometryState creates finite indexed surfaces for every component", () => {
  const surfaces = buildGeometrySurfaces(AIRCRAFT, { radialSections: 24, chordSections: 21 });
  assert.equal(surfaces.length, 6);
  assert.deepEqual(
    surfaces.map((surface) => surface.componentKind),
    ["loft_body", "lifting_surface", "lifting_surface", "lifting_surface", "nacelle", "nacelle"],
  );
  for (const surface of surfaces) {
    assert.ok(surface.positions.length > 30);
    assert.ok(surface.indices.length > 30);
    assert.ok(Array.from(surface.positions).every(Number.isFinite));
    assert.ok(Array.from(surface.indices).every(Number.isFinite));
    assert.ok(Array.from(surface.indices).every((index) => index < surface.positions.length / 3));
  }
});

test("body, wing, tail and nacelle lofts close root and tip without degenerate triangles", () => {
  for (const surface of buildGeometrySurfaces(AIRCRAFT, { radialSections: 24, chordSections: 21 })) {
    assert.deepEqual(topology(surface), {
      boundaryEdges: 0,
      nonManifoldEdges: 0,
      zeroAreaTriangles: 0,
    }, surface.instanceId);
  }
});

test("symmetry mirrors a lifting surface and nacelles across y", () => {
  const wing = buildLiftingSurface(MAIN_WING, { chordSections: 21 });
  assert.ok(wing);
  const [, positiveWingY] = rangeForAxis(wing, 1);
  const [negativeWingY] = rangeForAxis(wing, 1);
  assert.ok(Math.abs(positiveWingY + negativeWingY) < 1e-5);

  const engines = buildNacelleSurfaces(NACELLES, { radialSections: 24 });
  assert.equal(engines.length, 2);
  const left = rangeForAxis(engines[0], 1);
  const right = rangeForAxis(engines[1], 1);
  assert.ok(Math.abs(left[0] + right[1]) < 1e-5);
  assert.ok(Math.abs(left[1] + right[0]) < 1e-5);
});

test("vertical lifting surfaces loft in z and have physical thickness in y", () => {
  const fin = buildLiftingSurface(VERTICAL_TAIL, { chordSections: 21 });
  assert.ok(fin);
  const yRange = rangeForAxis(fin, 1);
  const zRange = rangeForAxis(fin, 2);
  assert.ok(yRange[1] - yRange[0] > 0.05);
  assert.ok(zRange[1] - zRange[0] > 2);

  const geometry = surfaceToBufferGeometry(fin);
  const normals = geometry.getAttribute("normal");
  const middleTopVertex = 21 + 10;
  assert.ok(normals.getY(middleTopVertex) > 0, "positive fin skin normal must face +y");
  geometry.dispose();
});

test("component parameters deform their own generated coordinates", () => {
  const body = buildLoftBodySurface(BODY, { radialSections: 24 });
  const fullerBody = buildLoftBodySurface({
    ...BODY,
    stations: BODY.stations.map((station, index) => index === 3 ? { ...station, width_m: 1.48 } : station),
  }, { radialSections: 24 });
  assert.ok(body && fullerBody);
  assert.ok(coordinateDifference(body.positions, fullerBody.positions) > 1);

  const wing = buildLiftingSurface(MAIN_WING, { chordSections: 21 });
  const sweptWing = buildLiftingSurface({
    ...MAIN_WING,
    sections: MAIN_WING.sections.map((section, index) => index === 3 ? { ...section, leading_edge_x_m: 6.2 } : section),
  }, { chordSections: 21 });
  assert.ok(wing && sweptWing);
  assert.ok(coordinateDifference(wing.positions, sweptWing.positions) > 10);

  const engines = buildNacelleSurfaces(NACELLES, { radialSections: 24 });
  const widerEngines = buildNacelleSurfaces({ ...NACELLES, centerline_y_m: 3.4 }, { radialSections: 24 });
  assert.ok(coordinateDifference(engines[0].positions, widerEngines[0].positions) > 10);
});

test("Three.js upload computes finite normals for every canonical component", () => {
  for (const surface of buildGeometrySurfaces(AIRCRAFT, { radialSections: 24, chordSections: 21 })) {
    const geometry = surfaceToBufferGeometry(surface);
    const normals = geometry.getAttribute("normal");
    assert.ok(normals);
    assert.equal(normals.count, surface.positions.length / 3);
    assert.ok(Array.from(normals.array).every(Number.isFinite));
    geometry.dispose();
  }
});

test("resource disposal releases shared geometry, material and texture once", () => {
  const root = new THREE.Group();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
  const texture = new THREE.Texture();
  const material = new THREE.MeshBasicMaterial({ map: texture });
  root.add(new THREE.Mesh(geometry, material), new THREE.Mesh(geometry, material));

  let geometryDisposals = 0;
  let materialDisposals = 0;
  let textureDisposals = 0;
  geometry.addEventListener("dispose", () => { geometryDisposals += 1; });
  material.addEventListener("dispose", () => { materialDisposals += 1; });
  texture.addEventListener("dispose", () => { textureDisposals += 1; });

  assert.deepEqual(disposeObjectResources(root), { geometries: 1, materials: 1, textures: 1 });
  assert.equal(geometryDisposals, 1);
  assert.equal(materialDisposals, 1);
  assert.equal(textureDisposals, 1);
});
