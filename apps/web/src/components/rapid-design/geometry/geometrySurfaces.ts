import type {
  GeometryComponent,
  GeometryState,
  LiftingSurfaceComponent,
  LiftingSurfaceSection,
  LoftBodyComponent,
  NacelleComponent,
  PropellerComponent,
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
  longitudinalSections?: number;
  spanwiseSections?: number;
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

function rotateAroundAxis(vector: Point3, axis: Point3, angle: number): Point3 {
  const unit = normalize(axis, [1, 0, 0]);
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const dot = vector[0] * unit[0] + vector[1] * unit[1] + vector[2] * unit[2];
  const crossed = cross(unit, vector);
  return [
    vector[0] * cosine + crossed[0] * sine + unit[0] * dot * (1 - cosine),
    vector[1] * cosine + crossed[1] * sine + unit[1] * dot * (1 - cosine),
    vector[2] * cosine + crossed[2] * sine + unit[2] * dot * (1 - cosine),
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

function monotoneSlopes(coordinates: readonly number[], values: readonly number[]): number[] {
  if (coordinates.length <= 1) return [0];
  const deltas = Array.from(
    { length: coordinates.length - 1 },
    (_, index) => (values[index + 1] - values[index])
      / Math.max(EPSILON, coordinates[index + 1] - coordinates[index]),
  );
  const slopes = new Array<number>(coordinates.length).fill(0);
  slopes[0] = deltas[0];
  slopes[slopes.length - 1] = deltas[deltas.length - 1];
  for (let index = 1; index < slopes.length - 1; index += 1) {
    const before = deltas[index - 1];
    const after = deltas[index];
    if (before === 0 || after === 0 || Math.sign(before) !== Math.sign(after)) {
      slopes[index] = 0;
      continue;
    }
    const beforeWidth = coordinates[index] - coordinates[index - 1];
    const afterWidth = coordinates[index + 1] - coordinates[index];
    const weightBefore = 2 * afterWidth + beforeWidth;
    const weightAfter = afterWidth + 2 * beforeWidth;
    slopes[index] = (weightBefore + weightAfter)
      / (weightBefore / before + weightAfter / after);
  }
  return slopes;
}

function sampleHermite(
  coordinates: readonly number[],
  values: readonly number[],
  slopes: readonly number[],
  segment: number,
  coordinate: number,
): number {
  const width = Math.max(EPSILON, coordinates[segment + 1] - coordinates[segment]);
  const t = clamp((coordinate - coordinates[segment]) / width, 0, 1);
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    (2 * t3 - 3 * t2 + 1) * values[segment]
    + (t3 - 2 * t2 + t) * width * slopes[segment]
    + (-2 * t3 + 3 * t2) * values[segment + 1]
    + (t3 - t2) * width * slopes[segment + 1]
  );
}

function resampleRingStations(
  stations: readonly RingStation[],
  sectionsPerSegment: number,
): RingStation[] {
  if (stations.length < 2 || sectionsPerSegment <= 1) return [...stations];
  const coordinates = stations.map((station) => station.x);
  const fields = {
    centerY: stations.map((station) => station.centerY),
    centerZ: stations.map((station) => station.centerZ),
    radiusY: stations.map((station) => station.radiusY),
    radiusZ: stations.map((station) => station.radiusZ),
    shapeExponent: stations.map((station) => station.shapeExponent),
  };
  const slopes = Object.fromEntries(
    Object.entries(fields).map(([key, values]) => [key, monotoneSlopes(coordinates, values)]),
  ) as Record<keyof typeof fields, number[]>;
  const result: RingStation[] = [];
  for (let segment = 0; segment < stations.length - 1; segment += 1) {
    for (let step = 0; step < sectionsPerSegment; step += 1) {
      const t = step / sectionsPerSegment;
      const x = coordinates[segment]
        + t * (coordinates[segment + 1] - coordinates[segment]);
      result.push({
        x,
        centerY: sampleHermite(coordinates, fields.centerY, slopes.centerY, segment, x),
        centerZ: sampleHermite(coordinates, fields.centerZ, slopes.centerZ, segment, x),
        radiusY: Math.max(
          EPSILON,
          sampleHermite(coordinates, fields.radiusY, slopes.radiusY, segment, x),
        ),
        radiusZ: Math.max(
          EPSILON,
          sampleHermite(coordinates, fields.radiusZ, slopes.radiusZ, segment, x),
        ),
        shapeExponent: clamp(
          sampleHermite(
            coordinates,
            fields.shapeExponent,
            slopes.shapeExponent,
            segment,
            x,
          ),
          1.2,
          8,
        ),
      });
    }
  }
  result.push({ ...stations[stations.length - 1] });
  return result;
}

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
  componentKind: "loft_body" | "nacelle" | "propeller",
  instanceId: string,
  inputStations: readonly RingStation[],
  radialSections: number,
  longitudinalSections: number,
): SurfaceMeshData | null {
  const stations = resampleRingStations(
    normalizeRingStations(inputStations),
    integerAtLeast(longitudinalSections, 4, 1),
  );
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
    integerAtLeast(options.longitudinalSections, 4, 1),
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
  camber_ratio: number;
  camber_position_ratio: number;
};

function airfoilCamber(airfoilId: string): readonly [number, number] {
  const match = /naca\s*([0-9])([0-9])([0-9]{2})/i.exec(airfoilId);
  if (!match) return [0, 0.4];
  const camber = Number(match[1]) / 100;
  const position = Number(match[2]) / 10;
  return [camber, position > 0 ? position : 0.4];
}

function normalizeLiftingSections(
  component: LiftingSurfaceComponent,
): NormalizedLiftingSection[] {
  const orientation = component.orientation ?? "horizontal";
  const sections = component.sections.map((section) => {
    const airfoilId = section.airfoil_id || "symmetric";
    const [fallbackCamber, fallbackPosition] = airfoilCamber(airfoilId);
    return {
      ...section,
      y_m: finiteOr(section.y_m, 0),
      leading_edge_x_m: finiteOr(section.leading_edge_x_m, 0),
      leading_edge_z_m: finiteOr(section.leading_edge_z_m, 0),
      chord_m: Math.max(EPSILON, Math.abs(finiteOr(section.chord_m, 1))),
      twist_deg: clamp(finiteOr(section.twist_deg, 0), -35, 35),
      dihedral_deg: clamp(finiteOr(section.dihedral_deg, 0), -75, 75),
      thickness_ratio: clamp(
        Math.abs(finiteOr(section.thickness_ratio, 0.12)),
        0.01,
        0.4,
      ),
      airfoil_id: airfoilId,
      camber_ratio: clamp(
        finiteOr(section.camber_ratio ?? Number.NaN, fallbackCamber),
        0,
        0.12,
      ),
      camber_position_ratio: clamp(
        finiteOr(section.camber_position_ratio ?? Number.NaN, fallbackPosition),
        0.05,
        0.95,
      ),
    };
  });

  sections.sort((left, right) => {
    if (orientation === "vertical") {
      return left.y_m - right.y_m || left.leading_edge_z_m - right.leading_edge_z_m;
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

function resampleLiftingSections(
  sections: readonly NormalizedLiftingSection[],
  sectionsPerSegment: number,
): NormalizedLiftingSection[] {
  if (sections.length < 2 || sectionsPerSegment <= 1) return [...sections];
  const coordinates = sections.map((section) => section.y_m);
  const fields = {
    leading_edge_x_m: sections.map((section) => section.leading_edge_x_m),
    leading_edge_z_m: sections.map((section) => section.leading_edge_z_m),
    chord_m: sections.map((section) => section.chord_m),
    twist_deg: sections.map((section) => section.twist_deg),
    dihedral_deg: sections.map((section) => section.dihedral_deg),
    thickness_ratio: sections.map((section) => section.thickness_ratio),
    camber_ratio: sections.map((section) => section.camber_ratio),
    camber_position_ratio: sections.map((section) => section.camber_position_ratio),
  };
  const slopes = Object.fromEntries(
    Object.entries(fields).map(([key, values]) => [key, monotoneSlopes(coordinates, values)]),
  ) as Record<keyof typeof fields, number[]>;
  const result: NormalizedLiftingSection[] = [];
  for (let segment = 0; segment < sections.length - 1; segment += 1) {
    for (let step = 0; step < sectionsPerSegment; step += 1) {
      const t = step / sectionsPerSegment;
      const y = coordinates[segment]
        + t * (coordinates[segment + 1] - coordinates[segment]);
      const interpolation = sections[segment].interpolation_to_next ?? "smooth";
      const sample = <Key extends keyof typeof fields>(key: Key) => interpolation === "linear"
        ? fields[key][segment] + t * (fields[key][segment + 1] - fields[key][segment])
        : sampleHermite(coordinates, fields[key], slopes[key], segment, y);
      result.push({
        y_m: y,
        leading_edge_x_m: sample("leading_edge_x_m"),
        leading_edge_z_m: sample("leading_edge_z_m"),
        chord_m: Math.max(EPSILON, sample("chord_m")),
        twist_deg: sample("twist_deg"),
        dihedral_deg: sample("dihedral_deg"),
        thickness_ratio: Math.max(0.01, sample("thickness_ratio")),
        airfoil_id: t < 0.5
          ? sections[segment].airfoil_id
          : sections[segment + 1].airfoil_id,
        camber_ratio: Math.max(0, sample("camber_ratio")),
        camber_position_ratio: clamp(sample("camber_position_ratio"), 0.05, 0.95),
        interpolation_to_next: interpolation,
      });
    }
  }
  result.push({ ...sections[sections.length - 1] });
  return result;
}

function sectionBase(
  section: NormalizedLiftingSection,
  orientation: "horizontal" | "vertical",
  centerlineY: number,
): Point3 {
  return [
    section.leading_edge_x_m,
    orientation === "vertical" ? centerlineY : centerlineY + section.y_m,
    section.leading_edge_z_m,
  ];
}

function sectionSpanTangent(
  sections: readonly NormalizedLiftingSection[],
  index: number,
  orientation: "horizontal" | "vertical",
  centerlineY: number,
): Point3 {
  const before = sectionBase(
    sections[Math.max(0, index - 1)],
    orientation,
    centerlineY,
  );
  const after = sectionBase(
    sections[Math.min(sections.length - 1, index + 1)],
    orientation,
    centerlineY,
  );
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

function nacaMeanCamber(
  chordFraction: number,
  camberRatio: number,
  camberPositionRatio: number,
): number {
  const x = clamp(chordFraction, 0, 1);
  const camber = clamp(camberRatio, 0, 0.12);
  const position = clamp(camberPositionRatio, 0.05, 0.95);
  if (camber <= EPSILON) return 0;
  if (x < position) {
    return camber / (position * position) * (2 * position * x - x * x);
  }
  const aft = 1 - position;
  return camber / (aft * aft)
    * ((1 - 2 * position) + 2 * position * x - x * x);
}

function sampleLiftingPoint(
  sections: readonly NormalizedLiftingSection[],
  sectionIndex: number,
  chordFraction: number,
  surfaceSign: -1 | 1,
  orientation: "horizontal" | "vertical",
  centerlineY: number,
): Point3 {
  const section = sections[sectionIndex];
  const twist = section.twist_deg * DEG_TO_RAD;
  const chordDirection: Point3 = [Math.cos(twist), 0, -Math.sin(twist)];
  const spanDirection = sectionSpanTangent(
    sections,
    sectionIndex,
    orientation,
    centerlineY,
  );
  const normalFallback: Point3 = orientation === "vertical" ? [0, 1, 0] : [0, 0, 1];
  let normal = normalize(cross(chordDirection, spanDirection), normalFallback);
  if (orientation === "horizontal") {
    const geometricDihedral = Math.atan2(
      spanDirection[2],
      Math.max(EPSILON, Math.abs(spanDirection[1])),
    );
    const side = Math.sign(section.y_m);
    const requestedDihedral = side * section.dihedral_deg * DEG_TO_RAD;
    normal = normalize(
      rotateAroundAxis(normal, chordDirection, requestedDihedral - geometricDihedral),
      normalFallback,
    );
  }
  if (orientation === "horizontal" && normal[2] < 0) normal = scale(normal, -1);
  if (orientation === "vertical" && normal[1] < 0) normal = scale(normal, -1);

  const base = sectionBase(section, orientation, centerlineY);
  const quarterChord = add(base, [0.25 * section.chord_m, 0, 0]);
  const chordPoint = add(
    quarterChord,
    scale(chordDirection, (chordFraction - 0.25) * section.chord_m),
  );
  const camber = nacaMeanCamber(
    chordFraction,
    section.camber_ratio,
    section.camber_position_ratio,
  ) * section.chord_m;
  const thickness = nacaThickness(chordFraction, section.thickness_ratio) * section.chord_m;
  return add(chordPoint, scale(normal, camber + surfaceSign * thickness));
}

/** Build one closed, indexed wing/tail surface, including both mirrored halves. */
export function buildLiftingSurface(
  component: LiftingSurfaceComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData | null {
  const orientation = component.orientation ?? "horizontal";
  const centerlineY = finiteOr(component.centerline_y_m ?? 0, 0);
  const sections = resampleLiftingSections(
    normalizeLiftingSections(component),
    integerAtLeast(options.spanwiseSections, 3, 1),
  );
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
          centerlineY,
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
          centerlineY,
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
      integerAtLeast(options.longitudinalSections, 4, 1),
    );
    if (surface) results.push(surface);
  }
  return results;
}

function buildPropellerBlade(
  component: PropellerComponent,
  centerY: number,
  bladeIndex: number,
): SurfaceMeshData {
  const bladeCount = integerAtLeast(component.blade_count, 3, 2);
  const angle = (finiteOr(component.rotation_deg, 0) * DEG_TO_RAD)
    + (2 * Math.PI * bladeIndex) / bladeCount;
  const radius = Math.max(EPSILON, Math.abs(finiteOr(component.radius_m, 1)));
  const hubRadius = clamp(
    Math.abs(finiteOr(component.hub_radius_m, 0.12 * radius)),
    EPSILON,
    0.8 * radius,
  );
  const rootRadius = 1.06 * hubRadius;
  const tipRadius = radius;
  const rootChord = Math.max(EPSILON, Math.abs(finiteOr(component.blade_chord_m, 0.1)));
  const tipChord = 0.38 * rootChord;
  const axialHalfThickness = Math.max(0.008 * radius, 0.045 * rootChord);
  const radial = (distance: number): Point3 => [
    finiteOr(component.center_x_m, 0),
    centerY + distance * Math.cos(angle),
    finiteOr(component.center_z_m, 0) + distance * Math.sin(angle),
  ];
  const tangent: Point3 = [0, -Math.sin(angle), Math.cos(angle)];
  const rootCenter = radial(rootRadius);
  const tipCenter = radial(tipRadius);
  const corners = [
    add(add(rootCenter, scale(tangent, 0.5 * rootChord)), [-axialHalfThickness, 0, 0]),
    add(add(rootCenter, scale(tangent, -0.5 * rootChord)), [-axialHalfThickness, 0, 0]),
    add(add(tipCenter, scale(tangent, -0.5 * tipChord)), [-axialHalfThickness, 0, 0]),
    add(add(tipCenter, scale(tangent, 0.5 * tipChord)), [-axialHalfThickness, 0, 0]),
    add(add(rootCenter, scale(tangent, 0.5 * rootChord)), [axialHalfThickness, 0, 0]),
    add(add(rootCenter, scale(tangent, -0.5 * rootChord)), [axialHalfThickness, 0, 0]),
    add(add(tipCenter, scale(tangent, -0.5 * tipChord)), [axialHalfThickness, 0, 0]),
    add(add(tipCenter, scale(tangent, 0.5 * tipChord)), [axialHalfThickness, 0, 0]),
  ];
  const positions: number[] = [];
  corners.forEach((corner) => appendPoint(positions, corner));
  const indices = new Uint32Array([
    0, 2, 1, 0, 3, 2,
    4, 5, 6, 4, 6, 7,
    0, 5, 4, 0, 1, 5,
    1, 6, 5, 1, 2, 6,
    2, 7, 6, 2, 3, 7,
    3, 4, 7, 3, 0, 4,
  ]);
  return {
    componentId: component.id,
    componentKind: component.kind,
    instanceId: `${component.id}-${centerY < 0 ? "left" : centerY > 0 ? "right" : "centre"}-blade-${bladeIndex + 1}`,
    positions: new Float32Array(positions),
    indices,
  };
}

export function buildPropellerSurfaces(
  component: PropellerComponent,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData[] {
  const centerline = Math.abs(finiteOr(component.centerline_y_m, 0));
  const centreLines = component.symmetry === "y" && centerline > EPSILON
    ? [-centerline, centerline]
    : [finiteOr(component.centerline_y_m, 0)];
  const bladeCount = integerAtLeast(component.blade_count, 3, 2);
  const results: SurfaceMeshData[] = [];
  for (const centerY of centreLines) {
    const radius = Math.max(EPSILON, Math.abs(finiteOr(component.hub_radius_m, 0.1)));
    const halfLength = 0.5 * Math.max(
      EPSILON,
      Math.abs(finiteOr(component.hub_length_m, 0.2)),
    );
    const centerX = finiteOr(component.center_x_m, 0);
    const centerZ = finiteOr(component.center_z_m, 0);
    const suffix = centreLines.length > 1 ? (centerY < 0 ? "left" : "right") : "centre";
    const hub = buildRingLoft(
      component.id,
      component.kind,
      `${component.id}-${suffix}-hub`,
      [
        {
          x: centerX - halfLength,
          centerY,
          centerZ,
          radiusY: 0.18 * radius,
          radiusZ: 0.18 * radius,
          shapeExponent: 2,
        },
        {
          x: centerX - 0.35 * halfLength,
          centerY,
          centerZ,
          radiusY: radius,
          radiusZ: radius,
          shapeExponent: 2,
        },
        {
          x: centerX + 0.35 * halfLength,
          centerY,
          centerZ,
          radiusY: radius,
          radiusZ: radius,
          shapeExponent: 2,
        },
        {
          x: centerX + halfLength,
          centerY,
          centerZ,
          radiusY: 0.18 * radius,
          radiusZ: 0.18 * radius,
          shapeExponent: 2,
        },
      ],
      integerAtLeast(options.radialSections, 24, 12),
      integerAtLeast(options.longitudinalSections, 2, 1),
    );
    if (hub) results.push(hub);
    for (let bladeIndex = 0; bladeIndex < bladeCount; bladeIndex += 1) {
      results.push(buildPropellerBlade(component, centerY, bladeIndex));
    }
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
  if (component.kind === "nacelle") {
    return buildNacelleSurfaces(component, options);
  }
  if (component.kind === "propeller") {
    return buildPropellerSurfaces(component, options);
  }
  return [];
}

export function buildGeometrySurfaces(
  geometry: GeometryState,
  options: SurfaceBuildOptions = {},
): SurfaceMeshData[] {
  return geometry.components.flatMap((component) => buildComponentSurfaces(component, options));
}
