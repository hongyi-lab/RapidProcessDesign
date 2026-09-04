import type {
  GeometryComponent,
  GeometryState,
  LiftingSurfaceComponent,
  LiftingSurfaceSection,
  LoftBodyComponent,
  NacelleComponent,
} from "./types";

export type SurfaceMeshData = {
  componentId: string;
  componentKind: GeometryComponent["kind"];
  instanceId: string;
  positions: Float32Array;
  indices: Uint32Array;
};

export type SurfaceBuildOptions = {
  radialSections?: number;
  chordSections?: number;
};

type Point3 = readonly [number, number, number];

const EPSILON = 1e-5;
const DEG_TO_RAD = Math.PI / 180;

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function integerAtLeast(value: number | undefined, fallback: number, minimum: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(minimum, Math.round(value as number));
}

function appendPoint(target: number[], point: Point3): void {
  target.push(point[0], point[1], point[2]);
}

function add(a: Point3, b: Point3): Point3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function subtract(a: Point3, b: Point3): Point3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function scale(vector: Point3, factor: number): Point3 {
  return [vector[0] * factor, vector[1] * factor, vector[2] * factor];
}

function cross(a: Point3, b: Point3): Point3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(vector: Point3, fallback: Point3): Point3 {
  const length = Math.hypot(vector[0], vector[1], vector[2]);
  if (!Number.isFinite(length) || length < EPSILON) return fallback;
  return scale(vector, 1 / length);
}

function signedPower(value: number, exponent: number): number {
  return Math.sign(value) * Math.pow(Math.abs(value), exponent);
}

type RingStation = {
  x: number;
  centerY: number;
  centerZ: number;
  radiusY: number;
  radiusZ: number;
  shapeExponent: number;
};

function normalizeRingStations(stations: readonly RingStation[]): RingStation[] {
  const sorted = stations
    .map((station) => ({
      x: finiteOr(station.x, 0),
      centerY: finiteOr(station.centerY, 0),
      centerZ: finiteOr(station.centerZ, 0),
      radiusY: Math.max(EPSILON, Math.abs(finiteOr(station.radiusY, EPSILON))),
      radiusZ: Math.max(EPSILON, Math.abs(finiteOr(station.radiusZ, EPSILON))),
      shapeExponent: clamp(finiteOr(station.shapeExponent, 2), 1.2, 8),
    }))
    .sort((left, right) => left.x - right.x);

  const unique: RingStation[] = [];
  for (const station of sorted) {
    const previous = unique[unique.length - 1];
    if (previous && Math.abs(previous.x - station.x) < EPSILON) {
      unique[unique.length - 1] = station;
    } else {
      unique.push(station);
    }
  }
  return unique;
}

function buildRingLoft(
  componentId: string,
  componentKind: "loft_body" | "nacelle",
  instanceId: string,
  inputStations: readonly RingStation[],
  radialSections: number,
): SurfaceMeshData | null {
  const stations = normalizeRingStations(inputStations);
  if (stations.length < 2) return null;

  const ringSections = integerAtLeast(radialSections, 32, 12);
  const positions: number[] = [];
  for (const station of stations) {
    const power = 2 / station.shapeExponent;
    for (let radialIndex = 0; radialIndex < ringSections; radialIndex += 1) {
      const angle = (2 * Math.PI * radialIndex) / ringSections;
      appendPoint(positions, [
        station.x,
        station.centerY + station.radiusY * signedPower(Math.cos(angle), power),
        station.centerZ + station.radiusZ * signedPower(Math.sin(angle), power),
      ]);
    }
  }

  const startCentreIndex = positions.length / 3;
  appendPoint(positions, [stations[0].x, stations[0].centerY, stations[0].centerZ]);
  const endStation = stations[stations.length - 1];
  const endCentreIndex = positions.length / 3;
  appendPoint(positions, [endStation.x, endStation.centerY, endStation.centerZ]);

  const vertex = (stationIndex: number, radialIndex: number) =>
    stationIndex * ringSections + ((radialIndex + ringSections) % ringSections);
  const indices: number[] = [];
  for (let stationIndex = 0; stationIndex < stations.length - 1; stationIndex += 1) {
    for (let radialIndex = 0; radialIndex < ringSections; radialIndex += 1) {
      const a = vertex(stationIndex, radialIndex);
      const b = vertex(stationIndex + 1, radialIndex);
      const c = vertex(stationIndex + 1, radialIndex + 1);
      const d = vertex(stationIndex, radialIndex + 1);
      indices.push(a, d, b, d, c, b);
    }
  }
  for (let radialIndex = 0; radialIndex < ringSections; radialIndex += 1) {
    indices.push(
      startCentreIndex,
      vertex(0, radialIndex + 1),
      vertex(0, radialIndex),
      endCentreIndex,
      vertex(stations.length - 1, radialIndex),
      vertex(stations.length - 1, radialIndex + 1),
    );
  }

  return {
    componentId,
    componentKind,
    instanceId,
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
  };
}

export function buildLoftBodySurface(
  component: LoftBodyComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData | null {
  return buildRingLoft(
    component.id,
    component.kind,
    component.id,
    component.stations.map((station) => ({
      x: station.x_m,
      centerY: 0,
      centerZ: station.z_offset_m,
      radiusY: station.width_m / 2,
      radiusZ: station.height_m / 2,
      shapeExponent: station.shape_exponent,
    })),
    integerAtLeast(options.radialSections, 36, 12),
  );
}

type NormalizedLiftingSection = LiftingSurfaceSection & {
  y_m: number;
  leading_edge_x_m: number;
  leading_edge_z_m: number;
  chord_m: number;
  twist_deg: number;
  dihedral_deg: number;
  thickness_ratio: number;
};

function normalizeLiftingSections(
  component: LiftingSurfaceComponent,
): NormalizedLiftingSection[] {
  const orientation = component.orientation ?? "horizontal";
  const sections = component.sections.map((section) => ({
    ...section,
    y_m: finiteOr(section.y_m, 0),
    leading_edge_x_m: finiteOr(section.leading_edge_x_m, 0),
    leading_edge_z_m: finiteOr(section.leading_edge_z_m, 0),
    chord_m: Math.max(EPSILON, Math.abs(finiteOr(section.chord_m, 1))),
    twist_deg: clamp(finiteOr(section.twist_deg, 0), -35, 35),
    dihedral_deg: clamp(finiteOr(section.dihedral_deg, 0), -45, 45),
    thickness_ratio: clamp(Math.abs(finiteOr(section.thickness_ratio, 0.12)), 0.01, 0.4),
    airfoil_id: section.airfoil_id || "symmetric",
  }));

  sections.sort((left, right) => {
    if (orientation === "vertical") {
      return left.leading_edge_z_m - right.leading_edge_z_m || left.y_m - right.y_m;
    }
    return left.y_m - right.y_m;
  });

  if (orientation === "horizontal" && component.symmetry === "y") {
    const positive = sections.map((section) => ({ ...section, y_m: Math.abs(section.y_m) }));
    positive.sort((left, right) => left.y_m - right.y_m);
    const negative = positive
      .slice()
      .reverse()
      .map((section) => ({ ...section, y_m: -section.y_m }));
    const hasRoot = positive.length > 0 && Math.abs(positive[0].y_m) < EPSILON;
    return hasRoot ? [...negative, ...positive.slice(1)] : [...negative, ...positive];
  }
  return sections;
}

function sectionBase(
  section: NormalizedLiftingSection,
  orientation: "horizontal" | "vertical",
): Point3 {
  return [
    section.leading_edge_x_m,
    orientation === "vertical" ? 0 : section.y_m,
    section.leading_edge_z_m,
  ];
}

function sectionSpanTangent(
  sections: readonly NormalizedLiftingSection[],
  index: number,
  orientation: "horizontal" | "vertical",
): Point3 {
  const before = sectionBase(sections[Math.max(0, index - 1)], orientation);
  const after = sectionBase(sections[Math.min(sections.length - 1, index + 1)], orientation);
  return normalize(
    subtract(after, before),
    orientation === "vertical" ? [0, 0, 1] : [0, 1, 0],
  );
}

function nacaThickness(chordFraction: number, thicknessRatio: number): number {
  const x = clamp(chordFraction, 0, 1);
  return (
    5 *
    thicknessRatio *
    (0.2969 * Math.sqrt(x) -
      0.126 * x -
      0.3516 * x * x +
      0.2843 * x * x * x -
      0.1036 * x * x * x * x)
  );
}

function sampleLiftingPoint(
  sections: readonly NormalizedLiftingSection[],
  sectionIndex: number,
  chordFraction: number,
  surfaceSign: -1 | 1,
  orientation: "horizontal" | "vertical",
): Point3 {
  const section = sections[sectionIndex];
  const twist = section.twist_deg * DEG_TO_RAD;
  const chordDirection: Point3 = [Math.cos(twist), 0, -Math.sin(twist)];
  const spanDirection = sectionSpanTangent(sections, sectionIndex, orientation);
  const normalFallback: Point3 = orientation === "vertical" ? [0, 1, 0] : [0, 0, 1];
  let normal = normalize(cross(chordDirection, spanDirection), normalFallback);
  if (orientation === "horizontal" && normal[2] < 0) normal = scale(normal, -1);
  if (orientation === "vertical" && normal[1] < 0) normal = scale(normal, -1);

  const base = sectionBase(section, orientation);
  const chordPoint = add(base, scale(chordDirection, chordFraction * section.chord_m));
  const thickness = nacaThickness(chordFraction, section.thickness_ratio) * section.chord_m;
  return add(chordPoint, scale(normal, surfaceSign * thickness));
}

/** Build one closed, indexed wing/tail surface, including both mirrored halves. */
export function buildLiftingSurface(
  component: LiftingSurfaceComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData | null {
  const orientation = component.orientation ?? "horizontal";
  const sections = normalizeLiftingSections(component);
  if (sections.length < 2) return null;
  const chordSections = integerAtLeast(options.chordSections, 33, 9);
  const topVertexCount = sections.length * chordSections;
  const bottomInteriorCount = chordSections - 2;
  const positions: number[] = [];
  const chordFractionAt = (index: number) =>
    0.5 * (1 - Math.cos((Math.PI * index) / (chordSections - 1)));

  for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
    for (let chordIndex = 0; chordIndex < chordSections; chordIndex += 1) {
      appendPoint(
        positions,
        sampleLiftingPoint(
          sections,
          sectionIndex,
          chordFractionAt(chordIndex),
          1,
          orientation,
        ),
      );
    }
  }
  for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
    for (let chordIndex = 1; chordIndex < chordSections - 1; chordIndex += 1) {
      appendPoint(
        positions,
        sampleLiftingPoint(
          sections,
          sectionIndex,
          chordFractionAt(chordIndex),
          -1,
          orientation,
        ),
      );
    }
  }

  const topIndex = (sectionIndex: number, chordIndex: number) =>
    sectionIndex * chordSections + chordIndex;
  const bottomIndex = (sectionIndex: number, chordIndex: number) => {
    if (chordIndex === 0 || chordIndex === chordSections - 1) {
      return topIndex(sectionIndex, chordIndex);
    }
    return topVertexCount + sectionIndex * bottomInteriorCount + chordIndex - 1;
  };
  const indices: number[] = [];
  for (let sectionIndex = 0; sectionIndex < sections.length - 1; sectionIndex += 1) {
    for (let chordIndex = 0; chordIndex < chordSections - 1; chordIndex += 1) {
      const topA = topIndex(sectionIndex, chordIndex);
      const topB = topIndex(sectionIndex, chordIndex + 1);
      const topC = topIndex(sectionIndex + 1, chordIndex);
      const topD = topIndex(sectionIndex + 1, chordIndex + 1);

      const bottomA = bottomIndex(sectionIndex, chordIndex);
      const bottomB = bottomIndex(sectionIndex, chordIndex + 1);
      const bottomC = bottomIndex(sectionIndex + 1, chordIndex);
      const bottomD = bottomIndex(sectionIndex + 1, chordIndex + 1);
      if (orientation === "vertical") {
        // x cross z points towards -y, while the canonical positive surface
        // is constructed towards +y. Reverse both skins for outward normals.
        indices.push(topA, topC, topB, topB, topC, topD);
        indices.push(bottomA, bottomB, bottomC, bottomB, bottomD, bottomC);
      } else {
        indices.push(topA, topB, topC, topB, topD, topC);
        indices.push(bottomA, bottomC, bottomB, bottomB, bottomC, bottomD);
      }
    }
  }

  function capSection(sectionIndex: number, reverse: boolean): void {
    const loop = [
      ...Array.from({ length: chordSections }, (_, index) => topIndex(sectionIndex, index)),
      ...Array.from(
        { length: chordSections - 2 },
        (_, index) => bottomIndex(sectionIndex, chordSections - 2 - index),
      ),
    ];
    const centreIndex = positions.length / 3;
    const centre = loop.reduce<Point3>(
      (sum, vertexIndex) => [
        sum[0] + positions[vertexIndex * 3],
        sum[1] + positions[vertexIndex * 3 + 1],
        sum[2] + positions[vertexIndex * 3 + 2],
      ],
      [0, 0, 0],
    );
    appendPoint(positions, scale(centre, 1 / loop.length));
    for (let index = 0; index < loop.length; index += 1) {
      const current = loop[index];
      const next = loop[(index + 1) % loop.length];
      if (reverse) indices.push(centreIndex, next, current);
      else indices.push(centreIndex, current, next);
    }
  }
  capSection(0, true);
  capSection(sections.length - 1, false);

  return {
    componentId: component.id,
    componentKind: component.kind,
    instanceId: component.id,
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
  };
}

export function buildNacelleSurfaces(
  component: NacelleComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData[] {
  const centerline = Math.abs(finiteOr(component.centerline_y_m, 0));
  const centreLines = component.symmetry === "y" && centerline > EPSILON
    ? [-centerline, centerline]
    : [finiteOr(component.centerline_y_m, 0)];
  const results: SurfaceMeshData[] = [];
  for (const centreY of centreLines) {
    const suffix = centreLines.length > 1 ? (centreY < 0 ? "left" : "right") : "centre";
    const surface = buildRingLoft(
      component.id,
      component.kind,
      `${component.id}-${suffix}`,
      component.stations.map((station) => ({
        x: station.x_m,
        centerY: centreY,
        centerZ: station.z_offset_m,
        radiusY: station.radius_y_m,
        radiusZ: station.radius_z_m,
        shapeExponent: 2,
      })),
      integerAtLeast(options.radialSections, 28, 12),
    );
    if (surface) results.push(surface);
  }
  return results;
}

export function buildComponentSurfaces(
  component: GeometryComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData[] {
  if (component.kind === "loft_body") {
    const surface = buildLoftBodySurface(component, options);
    return surface ? [surface] : [];
  }
  if (component.kind === "lifting_surface") {
    const surface = buildLiftingSurface(component, options);
    return surface ? [surface] : [];
  }
  return buildNacelleSurfaces(component, options);
}

export function buildGeometrySurfaces(
  geometry: GeometryState,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData[] {
  return geometry.components.flatMap((component) => buildComponentSurfaces(component, options));
}
