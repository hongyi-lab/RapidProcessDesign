import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  buildGeometrySurfaces,
  buildLiftingSurface,
  buildLoftBodySurface,
  buildNacelleSurfaces,
  buildPropellerSurfaces,
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
  PropellerComponent,
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

const PROPELLERS: PropellerComponent = {
  id: "wing-propellers",
  kind: "propeller",
  symmetry: "y",
  center_x_m: 3.25,
  centerline_y_m: 2.75,
  center_z_m: -0.36,
  radius_m: 0.92,
  hub_radius_m: 0.13,
  hub_length_m: 0.4,
  blade_count: 3,
  blade_chord_m: 0.16,
  rotation_deg: 18,
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

function signedVolume(surface: SurfaceMeshData): number {
  let volume = 0;
  const p = (vertex: number): [number, number, number] => {
    const offset = vertex * 3;
    return [
      surface.positions[offset],
      surface.positions[offset + 1],
      surface.positions[offset + 2],
    ];
  };
  for (let offset = 0; offset < surface.indices.length; offset += 3) {
    const a = p(surface.indices[offset]);
    const b = p(surface.indices[offset + 1]);
    const c = p(surface.indices[offset + 2]);
    volume += (
      a[0] * (b[1] * c[2] - b[2] * c[1])
      + a[1] * (b[2] * c[0] - b[0] * c[2])
      + a[2] * (b[0] * c[1] - b[1] * c[0])
    ) / 6;
  }
  return volume;
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

test("vertical fin caps and skins traverse shared edges in opposite directions for CAD solids", () => {
  const fin = buildLiftingSurface(VERTICAL_TAIL);
  assert.ok(fin);
  const edges = new Map<string, number[]>();
  for (let offset = 0; offset < fin.indices.length; offset += 3) {
    const [a, b, c] = fin.indices.slice(offset, offset + 3);
    for (const [from, to] of [[a, b], [b, c], [c, a]]) {
      const key = from < to ? `${from}:${to}` : `${to}:${from}`;
      edges.set(key, [...(edges.get(key) ?? []), from < to ? 1 : -1]);
    }
  }
  for (const directions of edges.values()) {
    assert.equal(directions.length, 2);
    assert.equal(directions[0] + directions[1], 0);
  }
  assert.ok(signedVolume(fin) > 0);
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

test("longitudinal interpolation adds smooth body rings between canonical stations", () => {
  const surface = buildLoftBodySurface(BODY, {
    radialSections: 24,
    longitudinalSections: 5,
  });
  assert.ok(surface);
  const uniqueX = new Set<number>();
  for (let index = 0; index < surface.positions.length - 6; index += 3) {
    uniqueX.add(Number(surface.positions[index].toFixed(6)));
  }
  assert.equal(uniqueX.size, (BODY.stations.length - 1) * 5 + 1);
  assert.ok(uniqueX.size > BODY.stations.length);
});

test("airfoil camber and standalone dihedral fields change lifting-surface mesh", () => {
  const symmetric = buildLiftingSurface({
    ...MAIN_WING,
    sections: MAIN_WING.sections.map((section) => ({
      ...section,
      leading_edge_z_m: 0,
      dihedral_deg: 0,
      airfoil_id: "naca0012",
    })),
  }, { chordSections: 21, spanwiseSections: 2 });
  const cambered = buildLiftingSurface({
    ...MAIN_WING,
    sections: MAIN_WING.sections.map((section) => ({
      ...section,
      leading_edge_z_m: 0,
      dihedral_deg: 0,
      airfoil_id: "naca4412",
    })),
  }, { chordSections: 21, spanwiseSections: 2 });
  const dihedral = buildLiftingSurface({
    ...MAIN_WING,
    sections: MAIN_WING.sections.map((section) => ({
      ...section,
      leading_edge_z_m: 0,
      dihedral_deg: 9,
      airfoil_id: "naca0012",
    })),
  }, { chordSections: 21, spanwiseSections: 2 });
  assert.ok(symmetric && cambered && dihedral);
  assert.ok(coordinateDifference(symmetric.positions, cambered.positions) > 1);
  assert.ok(coordinateDifference(symmetric.positions, dihedral.positions) > 1);
});

test("canted symmetric V-tail remains mirrored at the centreline", () => {
  const angle = 38 * Math.PI / 180;
  const tail = buildLiftingSurface({
    id: "v-tail",
    kind: "lifting_surface",
    symmetry: "y",
    sections: [0, 0.8, 1.7].map((y, index) => ({
      y_m: y,
      leading_edge_x_m: 9 + 0.2 * y,
      leading_edge_z_m: 0.4 + Math.tan(angle) * y,
      chord_m: [1.2, 0.8, 0.35][index],
      twist_deg: 0,
      dihedral_deg: 38,
      thickness_ratio: 0.1,
      airfoil_id: "naca0010",
    })),
  }, { chordSections: 17, spanwiseSections: 3 });
  assert.ok(tail);
  const rounded = new Set<string>();
  for (let index = 0; index < tail.positions.length; index += 3) {
    rounded.add([
      tail.positions[index].toFixed(4),
      tail.positions[index + 1].toFixed(4),
      tail.positions[index + 2].toFixed(4),
    ].join(":"));
  }
  for (let index = 0; index < tail.positions.length; index += 3) {
    const mirrored = [
      tail.positions[index].toFixed(4),
      (-tail.positions[index + 1]).toFixed(4),
      tail.positions[index + 2].toFixed(4),
    ].join(":");
    assert.ok(rounded.has(mirrored), `missing mirrored vertex ${mirrored}`);
  }
});

test("propeller hubs and blades are closed, outward and match declared layout", () => {
  const surfaces = buildPropellerSurfaces(PROPELLERS, {
    radialSections: 24,
    longitudinalSections: 2,
  });
  assert.equal(surfaces.length, 2 * (1 + PROPELLERS.blade_count));
  const hubs = surfaces.filter((surface) => surface.instanceId.endsWith("-hub"));
  const blades = surfaces.filter((surface) => surface.instanceId.includes("-blade-"));
  assert.equal(hubs.length, 2);
  assert.equal(blades.length, 6);
  for (const surface of surfaces) {
    assert.deepEqual(topology(surface), {
      boundaryEdges: 0,
      nonManifoldEdges: 0,
      zeroAreaTriangles: 0,
    }, surface.instanceId);
    assert.ok(signedVolume(surface) > 0, `${surface.instanceId} must face outward`);
  }
  for (const hub of hubs) {
    const [minimumX, maximumX] = rangeForAxis(hub, 0);
    assert.ok(Math.abs(maximumX - minimumX - PROPELLERS.hub_length_m) < 1e-5);
  }
  const left = rangeForAxis(hubs[0], 1);
  const right = rangeForAxis(hubs[1], 1);
  assert.ok(Math.abs(left[0] + right[1]) < 1e-5);
  assert.ok(Math.abs(left[1] + right[0]) < 1e-5);
});

test("off-centre vertical surfaces honour pylon centreline", () => {
  const pylon = buildLiftingSurface({
    ...VERTICAL_TAIL,
    id: "engine-pylon",
    centerline_y_m: 2.75,
  }, { chordSections: 17 });
  assert.ok(pylon);
  const [minimumY, maximumY] = rangeForAxis(pylon, 1);
  assert.ok(minimumY < 2.75 && maximumY > 2.75);
  assert.ok(Math.abs((minimumY + maximumY) / 2 - 2.75) < 1e-5);
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
