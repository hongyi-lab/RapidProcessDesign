/**
 * Clean-room BWB geometry used by the Rapid Design preview.
 *
 * The decoder deliberately operates on plain typed arrays so it can be tested
 * without WebGL. Three.js is only involved when the React preview uploads the
 * returned mesh to the GPU.
 */

export type BwbDesignVariables = {
  c1M: number;
  c2Ratio: number;
  c3Ratio: number;
  c4Ratio: number;
  b1Ratio: number;
  b2Ratio: number;
  b3Ratio: number;
  x3Ratio: number;
  sweepInnerDeg: number;
  sweepOuterDeg: number;
  thicknessRatio: number;
  twistTipDeg: number;
};

export type BwbVariableBounds = {
  minimum: number;
  maximum: number;
};

export const BWB_DESIGN_BOUNDS: Readonly<
  Record<keyof BwbDesignVariables, BwbVariableBounds>
> = Object.freeze({
  c1M: { minimum: 2, maximum: 12 },
  c2Ratio: { minimum: 0.55, maximum: 0.95 },
  c3Ratio: { minimum: 0.25, maximum: 0.7 },
  c4Ratio: { minimum: 0.08, maximum: 0.35 },
  b1Ratio: { minimum: 0.15, maximum: 0.6 },
  b2Ratio: { minimum: 0.2, maximum: 0.8 },
  b3Ratio: { minimum: 0.3, maximum: 1.2 },
  x3Ratio: { minimum: 0, maximum: 0.8 },
  sweepInnerDeg: { minimum: 20, maximum: 55 },
  sweepOuterDeg: { minimum: 15, maximum: 45 },
  thicknessRatio: { minimum: 0.08, maximum: 0.18 },
  twistTipDeg: { minimum: -6, maximum: 2 },
});

export const DEFAULT_BWB_DESIGN: Readonly<BwbDesignVariables> = Object.freeze({
  c1M: 6,
  c2Ratio: 0.78,
  c3Ratio: 0.48,
  c4Ratio: 0.18,
  b1Ratio: 0.32,
  b2Ratio: 0.45,
  b3Ratio: 0.7,
  x3Ratio: 0.25,
  sweepInnerDeg: 38,
  sweepOuterDeg: 28,
  thicknessRatio: 0.12,
  twistTipDeg: -2,
});

export type BwbPlanformStation = {
  yM: number;
  leadingEdgeXM: number;
  chordM: number;
};

export type BwbGeometryMetrics = {
  referenceAreaM2: number;
  spanM: number;
  semiSpanM: number;
  aspectRatio: number;
  meanAerodynamicChordM: number;
  wettedAreaM2: number;
  taperRatio: number;
  volumeProxyM3: number;
  minimumXM: number;
  maximumXM: number;
  maximumAbsZM: number;
};

export type BwbSurfaceData = {
  /** xyz triples for top, then bottom, surfaces. */
  positions: Float32Array;
  /** Triangle indices, including closed left and right tip caps. */
  indices: Uint32Array;
  /** Top-surface perimeter xyz triples ordered as a closed planform loop. */
  outlinePositions: Float32Array;
  spanSections: number;
  chordSections: number;
  stations: readonly BwbPlanformStation[];
  metrics: BwbGeometryMetrics;
  design: BwbDesignVariables;
};

export type BwbSurfaceOptions = {
  /** Odd values keep a mesh row exactly on the aircraft centreline. */
  spanSections?: number;
  chordSections?: number;
};

type Curve = {
  coordinates: readonly number[];
  values: readonly number[];
  tangents: readonly number[];
};

type CurveSample = {
  value: number;
  derivative: number;
};

type PlanformCurves = {
  chord: Curve;
  leadingEdge: Curve;
};

type SurfacePoint = {
  x: number;
  y: number;
  z: number;
};

const DEG_TO_RAD = Math.PI / 180;
// Matches the 0.01 UI step. Valid backend designs are otherwise left intact.
const CHORD_RATIO_GAP = 0.01;
const GAUSS_NODES = [
  -0.9602898564975363,
  -0.7966664774136267,
  -0.525532409916329,
  -0.1834346424956498,
  0.1834346424956498,
  0.525532409916329,
  0.7966664774136267,
  0.9602898564975363,
] as const;
const GAUSS_WEIGHTS = [
  0.1012285362903763,
  0.2223810344533745,
  0.3137066458778873,
  0.362683783378362,
  0.362683783378362,
  0.3137066458778873,
  0.2223810344533745,
  0.1012285362903763,
] as const;

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function clampVariable<K extends keyof BwbDesignVariables>(
  key: K,
  value: BwbDesignVariables[K],
): number {
  const bounds = BWB_DESIGN_BOUNDS[key];
  return clamp(finiteOr(value, DEFAULT_BWB_DESIGN[key]), bounds.minimum, bounds.maximum);
}

/**
 * Clamps malformed input and preserves the family invariant C2 > C3 > C4.
 * This is intentionally deterministic, so the same design always produces the
 * same mesh and metrics.
 */
export function normalizeBwbDesign(design: BwbDesignVariables): BwbDesignVariables {
  const c2Ratio = clampVariable("c2Ratio", design.c2Ratio);
  const c3Ratio = Math.min(
    clampVariable("c3Ratio", design.c3Ratio),
    c2Ratio - CHORD_RATIO_GAP,
  );
  const c4Ratio = Math.min(
    clampVariable("c4Ratio", design.c4Ratio),
    c3Ratio - CHORD_RATIO_GAP,
  );

  return {
    c1M: clampVariable("c1M", design.c1M),
    c2Ratio,
    c3Ratio: Math.max(BWB_DESIGN_BOUNDS.c3Ratio.minimum, c3Ratio),
    c4Ratio: Math.max(BWB_DESIGN_BOUNDS.c4Ratio.minimum, c4Ratio),
    b1Ratio: clampVariable("b1Ratio", design.b1Ratio),
    b2Ratio: clampVariable("b2Ratio", design.b2Ratio),
    b3Ratio: clampVariable("b3Ratio", design.b3Ratio),
    x3Ratio: clampVariable("x3Ratio", design.x3Ratio),
    sweepInnerDeg: clampVariable("sweepInnerDeg", design.sweepInnerDeg),
    sweepOuterDeg: clampVariable("sweepOuterDeg", design.sweepOuterDeg),
    thicknessRatio: clampVariable("thicknessRatio", design.thicknessRatio),
    twistTipDeg: clampVariable("twistTipDeg", design.twistTipDeg),
  };
}

/** Build the four clean-room planform control stations for one semi-wing. */
export function deriveBwbPlanformStations(
  input: BwbDesignVariables,
): readonly BwbPlanformStation[] {
  const design = normalizeBwbDesign(input);
  const c1 = design.c1M;
  const b1 = design.b1Ratio * c1;
  const b2 = design.b2Ratio * c1;
  const b3 = design.b3Ratio * c1;
  const sweepInner = design.sweepInnerDeg * DEG_TO_RAD;
  const sweepOuter = design.sweepOuterDeg * DEG_TO_RAD;
  const transitionSweep = 0.55 * sweepInner + 0.45 * sweepOuter;

  // A common translation does not alter the analysis geometry. Segment-to-
  // segment offsets exactly match the clean-room API decoder.
  const rootLeadingEdge = -0.22 * c1;
  const station2LeadingEdge = rootLeadingEdge + b1 * Math.tan(sweepInner);
  const station3LeadingEdge =
    station2LeadingEdge +
    b2 * Math.tan(transitionSweep) +
    0.25 * c1 * design.x3Ratio;
  const tipLeadingEdge = station3LeadingEdge + b3 * Math.tan(sweepOuter);

  return [
    { yM: 0, leadingEdgeXM: rootLeadingEdge, chordM: c1 },
    { yM: b1, leadingEdgeXM: station2LeadingEdge, chordM: design.c2Ratio * c1 },
    {
      yM: b1 + b2,
      leadingEdgeXM: station3LeadingEdge,
      chordM: design.c3Ratio * c1,
    },
    {
      yM: b1 + b2 + b3,
      leadingEdgeXM: tipLeadingEdge,
      chordM: design.c4Ratio * c1,
    },
  ];
}

function buildMonotoneCurve(
  coordinates: readonly number[],
  values: readonly number[],
  flattenRoot = false,
): Curve {
  const count = coordinates.length;
  const deltas = Array.from({ length: count - 1 }, (_, index) =>
    (values[index + 1] - values[index]) /
    Math.max(1e-8, coordinates[index + 1] - coordinates[index]),
  );
  const tangents = new Array<number>(count);
  tangents[0] = flattenRoot ? 0 : deltas[0];
  tangents[count - 1] = deltas[count - 2];

  for (let index = 1; index < count - 1; index += 1) {
    const before = deltas[index - 1];
    const after = deltas[index];
    if (before === 0 || after === 0 || Math.sign(before) !== Math.sign(after)) {
      tangents[index] = 0;
      continue;
    }
    const beforeWidth = coordinates[index] - coordinates[index - 1];
    const afterWidth = coordinates[index + 1] - coordinates[index];
    const weight1 = 2 * afterWidth + beforeWidth;
    const weight2 = afterWidth + 2 * beforeWidth;
    tangents[index] =
      (weight1 + weight2) / (weight1 / before + weight2 / after);
  }

  // Fritsch-Carlson limiting prevents cubic overshoot between valid controls.
  for (let index = 0; index < count - 1; index += 1) {
    const delta = deltas[index];
    if (Math.abs(delta) < 1e-12) {
      tangents[index] = 0;
      tangents[index + 1] = 0;
      continue;
    }
    const alpha = tangents[index] / delta;
    const beta = tangents[index + 1] / delta;
    const magnitude = alpha * alpha + beta * beta;
    if (magnitude > 9) {
      const scale = 3 / Math.sqrt(magnitude);
      tangents[index] = scale * alpha * delta;
      tangents[index + 1] = scale * beta * delta;
    }
  }

  return { coordinates, values, tangents };
}

function sampleCurve(curve: Curve, coordinate: number): number {
  const { coordinates, values, tangents } = curve;
  const last = coordinates.length - 1;
  if (coordinate <= coordinates[0]) return values[0];
  if (coordinate >= coordinates[last]) return values[last];

  let segment = 0;
  while (segment < last - 1 && coordinate > coordinates[segment + 1]) {
    segment += 1;
  }

  return sampleCurveSegment(curve, segment, coordinate).value;
}

function sampleCurveSegment(
  curve: Curve,
  segment: number,
  coordinate: number,
): CurveSample {
  const { coordinates, values, tangents } = curve;
  const width = coordinates[segment + 1] - coordinates[segment];
  const t = clamp((coordinate - coordinates[segment]) / width, 0, 1);
  const t2 = t * t;
  const t3 = t2 * t;
  const h00 = 2 * t3 - 3 * t2 + 1;
  const h10 = t3 - 2 * t2 + t;
  const h01 = -2 * t3 + 3 * t2;
  const h11 = t3 - t2;
  const value =
    h00 * values[segment] +
    h10 * width * tangents[segment] +
    h01 * values[segment + 1] +
    h11 * width * tangents[segment + 1];
  const derivative =
    ((6 * t2 - 6 * t) * values[segment]) / width +
    (3 * t2 - 4 * t + 1) * tangents[segment] +
    ((-6 * t2 + 6 * t) * values[segment + 1]) / width +
    (3 * t2 - 2 * t) * tangents[segment + 1];
  return { value, derivative };
}

function createPlanformCurves(stations: readonly BwbPlanformStation[]): PlanformCurves {
  const spanCoordinates = stations.map((station) => station.yM);
  return {
    chord: buildMonotoneCurve(
      spanCoordinates,
      stations.map((station) => station.chordM),
      true,
    ),
    leadingEdge: buildMonotoneCurve(
      spanCoordinates,
      stations.map((station) => station.leadingEdgeXM),
      true,
    ),
  };
}

function integratePlanformSegments(
  coordinates: readonly number[],
  integrand: (coordinate: number, segment: number) => number,
): number[] {
  return coordinates.slice(1).map((upper, segment) => {
    const lower = coordinates[segment];
    const midpoint = 0.5 * (lower + upper);
    const halfWidth = 0.5 * (upper - lower);
    let integral = 0;
    for (let index = 0; index < GAUSS_NODES.length; index += 1) {
      integral +=
        GAUSS_WEIGHTS[index] *
        integrand(midpoint + halfWidth * GAUSS_NODES[index], segment);
    }
    return halfWidth * integral;
  });
}

function airfoilHalfThickness(chordFraction: number, thicknessRatio: number): number {
  const x = clamp(chordFraction, 0, 1);
  // Closed trailing-edge NACA thickness distribution, expressed as a fraction
  // of local chord. It gives the BWB a real top and bottom loft, not an extrusion.
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

function createSectionSampler(
  design: BwbDesignVariables,
  stations: readonly BwbPlanformStation[],
  curves: PlanformCurves,
) {
  const semiSpan = stations[stations.length - 1].yM;

  return (signedYM: number, chordFraction: number, surfaceSign: -1 | 1): SurfacePoint => {
    const absoluteY = clamp(Math.abs(signedYM), 0, semiSpan);
    const eta = absoluteY / semiSpan;
    const chord = sampleCurve(curves.chord, absoluteY);
    const leadingEdge = sampleCurve(curves.leadingEdge, absoluteY);
    const twist = design.twistTipDeg * Math.pow(eta, 1.55) * DEG_TO_RAD;
    const localThicknessRatio =
      design.thicknessRatio * (1.34 - 0.52 * Math.pow(eta, 0.78));
    const halfThickness =
      surfaceSign * chord * airfoilHalfThickness(chordFraction, localThicknessRatio);
    const quarterChordX = leadingEdge + chord * 0.25;
    const sectionX = chord * (chordFraction - 0.25);

    return {
      x: quarterChordX + sectionX * Math.cos(twist) + halfThickness * Math.sin(twist),
      y: signedYM,
      z: -sectionX * Math.sin(twist) + halfThickness * Math.cos(twist),
    };
  };
}

function oddAtLeast(value: number | undefined, fallback: number, minimum: number): number {
  const rounded = Math.max(minimum, Math.round(finiteOr(value ?? fallback, fallback)));
  return rounded % 2 === 0 ? rounded + 1 : rounded;
}

function integerAtLeast(value: number | undefined, fallback: number, minimum: number): number {
  return Math.max(minimum, Math.round(finiteOr(value ?? fallback, fallback)));
}

function pushPoint(target: number[], point: SurfacePoint): void {
  target.push(point.x, point.y, point.z);
}

function deriveMetrics(
  design: BwbDesignVariables,
  stations: readonly BwbPlanformStation[],
  curves: PlanformCurves,
  sampler: ReturnType<typeof createSectionSampler>,
): BwbGeometryMetrics {
  const semiSpan = stations[stations.length - 1].yM;
  const spanCoordinates = stations.map((station) => station.yM);
  const halfSegmentAreas = integratePlanformSegments(
    spanCoordinates,
    (coordinate, segment) => sampleCurveSegment(curves.chord, segment, coordinate).value,
  );
  const chordSquaredSegments = integratePlanformSegments(
    spanCoordinates,
    (coordinate, segment) => {
      const chord = sampleCurveSegment(curves.chord, segment, coordinate).value;
      return chord * chord;
    },
  );
  const halfArea = halfSegmentAreas.reduce((sum, area) => sum + area, 0);
  const chordSquaredIntegral = chordSquaredSegments.reduce(
    (sum, integral) => sum + integral,
    0,
  );
  const referenceArea = 2 * halfArea;
  const span = 2 * semiSpan;
  const meanAerodynamicChord = chordSquaredIntegral / halfArea;

  const leadingEdgeSegments = integratePlanformSegments(
    spanCoordinates,
    (coordinate, segment) => {
      const derivative = sampleCurveSegment(
        curves.leadingEdge,
        segment,
        coordinate,
      ).derivative;
      return Math.hypot(1, derivative);
    },
  );
  const trailingEdgeSegments = integratePlanformSegments(
    spanCoordinates,
    (coordinate, segment) => {
      const leadingDerivative = sampleCurveSegment(
        curves.leadingEdge,
        segment,
        coordinate,
      ).derivative;
      const chordDerivative = sampleCurveSegment(
        curves.chord,
        segment,
        coordinate,
      ).derivative;
      return Math.hypot(1, leadingDerivative + chordDerivative);
    },
  );
  const leadingEdgeLength = leadingEdgeSegments.reduce((sum, length) => sum + length, 0);
  const trailingEdgeLength = trailingEdgeSegments.reduce((sum, length) => sum + length, 0);
  const edgePathRatio = (leadingEdgeLength + trailingEdgeLength) / (2 * semiSpan);
  const twistTangent = Math.tan(design.twistTipDeg * DEG_TO_RAD);
  const wettedArea =
    2 *
    referenceArea *
    (1 + 0.06 * design.thicknessRatio + 0.02 * (edgePathRatio - 1)) *
    (1 + 0.5 * twistTangent * twistTangent);

  const volumeProxy = 2 * 0.62 * design.thicknessRatio * chordSquaredIntegral;

  const sampleCount = 180;
  let minimumX = Number.POSITIVE_INFINITY;
  let maximumX = Number.NEGATIVE_INFINITY;
  let maximumAbsZ = 0;
  for (let spanIndex = 0; spanIndex <= sampleCount; spanIndex += 1) {
    const y = -semiSpan + (2 * semiSpan * spanIndex) / sampleCount;
    for (const chordFraction of [0, 0.3, 1]) {
      for (const sign of [-1, 1] as const) {
        const point = sampler(y, chordFraction, sign);
        minimumX = Math.min(minimumX, point.x);
        maximumX = Math.max(maximumX, point.x);
        maximumAbsZ = Math.max(maximumAbsZ, Math.abs(point.z));
      }
    }
  }

  return {
    referenceAreaM2: referenceArea,
    spanM: span,
    semiSpanM: semiSpan,
    aspectRatio: (span * span) / referenceArea,
    meanAerodynamicChordM: meanAerodynamicChord,
    wettedAreaM2: wettedArea,
    taperRatio: design.c4Ratio,
    volumeProxyM3: volumeProxy,
    minimumXM: minimumX,
    maximumXM: maximumX,
    maximumAbsZM: maximumAbsZ,
  };
}

/**
 * Generate a watertight-looking, indexed top/bottom loft for a symmetric BWB.
 * Leading and trailing rows meet exactly; separate tip caps close the span ends.
 */
export function buildBwbSurfaceData(
  input: BwbDesignVariables,
  options: BwbSurfaceOptions = {},
): BwbSurfaceData {
  const design = normalizeBwbDesign(input);
  const stations = deriveBwbPlanformStations(design);
  const curves = createPlanformCurves(stations);
  const sampler = createSectionSampler(design, stations, curves);
  const spanSections = oddAtLeast(options.spanSections, 65, 9);
  const chordSections = integerAtLeast(options.chordSections, 41, 9);
  const semiSpan = stations[stations.length - 1].yM;
  const topVertexCount = spanSections * chordSections;
  const bottomInteriorPerRow = chordSections - 2;
  const positions: number[] = [];

  const chordFractionAt = (chordIndex: number) => {
    // Cosine spacing resolves the rounded leading edge without a dense mesh.
    const phase = chordIndex / (chordSections - 1);
    return 0.5 * (1 - Math.cos(Math.PI * phase));
  };
  const spanYAt = (spanIndex: number) =>
    -semiSpan + (2 * semiSpan * spanIndex) / (spanSections - 1);
  const topIndex = (spanIndex: number, chordIndex: number) =>
    spanIndex * chordSections + chordIndex;
  const bottomIndex = (spanIndex: number, chordIndex: number) => {
    if (chordIndex === 0 || chordIndex === chordSections - 1) {
      return topIndex(spanIndex, chordIndex);
    }
    return topVertexCount + spanIndex * bottomInteriorPerRow + chordIndex - 1;
  };

  // Top includes the common leading and trailing edges. Bottom only adds its
  // interior vertices and references those same edge indices, making the mesh
  // topologically closed rather than merely placing duplicate points together.
  for (let spanIndex = 0; spanIndex < spanSections; spanIndex += 1) {
    const y = spanYAt(spanIndex);
    for (let chordIndex = 0; chordIndex < chordSections; chordIndex += 1) {
      pushPoint(positions, sampler(y, chordFractionAt(chordIndex), 1));
    }
  }
  for (let spanIndex = 0; spanIndex < spanSections; spanIndex += 1) {
    const y = spanYAt(spanIndex);
    for (let chordIndex = 1; chordIndex < chordSections - 1; chordIndex += 1) {
      pushPoint(positions, sampler(y, chordFractionAt(chordIndex), -1));
    }
  }

  const indices: number[] = [];
  for (let spanIndex = 0; spanIndex < spanSections - 1; spanIndex += 1) {
    for (let chordIndex = 0; chordIndex < chordSections - 1; chordIndex += 1) {
      const topA = topIndex(spanIndex, chordIndex);
      const topB = topIndex(spanIndex, chordIndex + 1);
      const topC = topIndex(spanIndex + 1, chordIndex);
      const topD = topIndex(spanIndex + 1, chordIndex + 1);
      indices.push(topA, topB, topC, topB, topD, topC);

      const bottomA = bottomIndex(spanIndex, chordIndex);
      const bottomB = bottomIndex(spanIndex, chordIndex + 1);
      const bottomC = bottomIndex(spanIndex + 1, chordIndex);
      const bottomD = bottomIndex(spanIndex + 1, chordIndex + 1);
      indices.push(bottomA, bottomC, bottomB, bottomB, bottomC, bottomD);
    }
  }

  // Tip caps start and end with one triangle because the top and bottom share
  // their edge vertex. Interior strips use two triangles, with no repeated
  // indices or zero-area slivers.
  const negativeSpanIndex = 0;
  const positiveSpanIndex = spanSections - 1;
  indices.push(
    topIndex(negativeSpanIndex, 0),
    bottomIndex(negativeSpanIndex, 1),
    topIndex(negativeSpanIndex, 1),
    topIndex(positiveSpanIndex, 0),
    topIndex(positiveSpanIndex, 1),
    bottomIndex(positiveSpanIndex, 1),
  );
  for (let chordIndex = 1; chordIndex < chordSections - 2; chordIndex += 1) {
    const negativeTopA = topIndex(negativeSpanIndex, chordIndex);
    const negativeTopB = topIndex(negativeSpanIndex, chordIndex + 1);
    const negativeBottomA = bottomIndex(negativeSpanIndex, chordIndex);
    const negativeBottomB = bottomIndex(negativeSpanIndex, chordIndex + 1);
    indices.push(
      negativeTopA,
      negativeBottomA,
      negativeTopB,
      negativeTopB,
      negativeBottomA,
      negativeBottomB,
    );

    const positiveTopA = topIndex(positiveSpanIndex, chordIndex);
    const positiveTopB = topIndex(positiveSpanIndex, chordIndex + 1);
    const positiveBottomA = bottomIndex(positiveSpanIndex, chordIndex);
    const positiveBottomB = bottomIndex(positiveSpanIndex, chordIndex + 1);
    indices.push(
      positiveTopA,
      positiveTopB,
      positiveBottomA,
      positiveTopB,
      positiveBottomB,
      positiveBottomA,
    );
  }
  const lastInteriorChord = chordSections - 2;
  indices.push(
    topIndex(negativeSpanIndex, lastInteriorChord),
    bottomIndex(negativeSpanIndex, lastInteriorChord),
    topIndex(negativeSpanIndex, chordSections - 1),
    topIndex(positiveSpanIndex, lastInteriorChord),
    topIndex(positiveSpanIndex, chordSections - 1),
    bottomIndex(positiveSpanIndex, lastInteriorChord),
  );

  const outlinePositions: number[] = [];
  for (let spanIndex = 0; spanIndex < spanSections; spanIndex += 1) {
    const y = -semiSpan + (2 * semiSpan * spanIndex) / (spanSections - 1);
    pushPoint(outlinePositions, sampler(y, 0, 1));
  }
  for (let spanIndex = spanSections - 1; spanIndex >= 0; spanIndex -= 1) {
    const y = -semiSpan + (2 * semiSpan * spanIndex) / (spanSections - 1);
    pushPoint(outlinePositions, sampler(y, 1, 1));
  }

  return {
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
    outlinePositions: new Float32Array(outlinePositions),
    spanSections,
    chordSections,
    stations,
    metrics: deriveMetrics(design, stations, curves, sampler),
    design,
  };
}
