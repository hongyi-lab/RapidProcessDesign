import { buildGeometrySurfaces, type SurfaceMeshData } from "./geometrySurfaces.ts";
import type { GeometryState } from "./types";

export type GeometryExportFormat = "step" | "stl";

function normal(surface: SurfaceMeshData, offset: number): [number, number, number] {
  const [a, b, c] = Array.from(surface.indices.slice(offset, offset + 3), (index) => index * 3);
  const p = surface.positions;
  const ab = [p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]];
  const ac = [p[c] - p[a], p[c + 1] - p[a + 1], p[c + 2] - p[a + 2]];
  return [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]];
}

/** Export model coordinates, before camera fitting, display scaling or baseline overlays. */
export function exportSurfaces(geometry: GeometryState): SurfaceMeshData[] {
  if (geometry.geometry_status !== "valid" || geometry.components.length === 0) {
    throw new Error("Generate valid geometry before exporting.");
  }
  const surfaces = buildGeometrySurfaces(geometry);
  if (geometry.components.some((component) => !surfaces.some((surface) => surface.componentId === component.id))) {
    throw new Error("Some aircraft components could not be exported.");
  }
  for (const surface of surfaces) {
    if (!surface.positions.length || !surface.indices.length
      || surface.positions.length % 3 || surface.indices.length % 3
      || !surface.positions.every(Number.isFinite)
      || !surface.indices.every((index) => index < surface.positions.length / 3)) {
      throw new Error(`Invalid geometry in ${surface.instanceId}.`);
    }
    const edges = new Map<string, { count: number; direction: number }>();
    let volume = 0;
    for (let offset = 0; offset < surface.indices.length; offset += 3) {
      const [a, b, c] = surface.indices.slice(offset, offset + 3);
      const n = normal(surface, offset);
      if (Math.hypot(...n) === 0) throw new Error(`Degenerate face in ${surface.instanceId}.`);
      volume += (surface.positions[a * 3] * n[0]
        + surface.positions[a * 3 + 1] * n[1] + surface.positions[a * 3 + 2] * n[2]) / 6;
      for (const [from, to] of [[a, b], [b, c], [c, a]]) {
        const key = from < to ? `${from}:${to}` : `${to}:${from}`;
        const edge = edges.get(key) ?? { count: 0, direction: 0 };
        edge.count += 1;
        edge.direction += from < to ? 1 : -1;
        edges.set(key, edge);
      }
    }
    if ([...edges.values()].some((edge) => edge.count !== 2 || edge.direction !== 0)
      || !Number.isFinite(volume) || volume === 0) {
      throw new Error(`The ${surface.instanceId} mesh is not a closed, oriented body.`);
    }
    if (volume < 0) {
      for (let offset = 0; offset < surface.indices.length; offset += 3) {
        [surface.indices[offset + 1], surface.indices[offset + 2]] =
          [surface.indices[offset + 2], surface.indices[offset + 1]];
      }
    }
  }
  return surfaces;
}

export function geometryExportFilename(name: string, format: GeometryExportFormat): string {
  const safeName = name.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 100);
  return `${safeName || "aircraft"}-mm.${format}`;
}

/** STL has no unit metadata. Coordinates and the download filename explicitly use millimeters. */
export function binaryStl(surfaces: readonly SurfaceMeshData[]): ArrayBuffer {
  const triangleCount = surfaces.reduce((sum, surface) => sum + surface.indices.length / 3, 0);
  const buffer = new ArrayBuffer(84 + triangleCount * 50);
  new Uint8Array(buffer, 0, 80).set(new TextEncoder().encode("RapidProcessDesign | units: millimeters | aircraft mesh"));
  const view = new DataView(buffer);
  view.setUint32(80, triangleCount, true);
  let cursor = 84;
  for (const surface of surfaces) {
    for (let offset = 0; offset < surface.indices.length; offset += 3) {
      const n = normal(surface, offset);
      const length = Math.hypot(...n);
      for (const value of n) { view.setFloat32(cursor, value / length, true); cursor += 4; }
      for (const index of surface.indices.slice(offset, offset + 3)) {
        for (let axis = 0; axis < 3; axis += 1) {
          view.setFloat32(cursor, surface.positions[index * 3 + axis] * 1000, true);
          cursor += 4;
        }
      }
      cursor += 2; // STL attribute byte count stays zero.
    }
  }
  return buffer;
}

function stepString(value: string): string {
  return `'${value.replace(/[^\x20-\x7E]/g, "_").replaceAll("'", "''").replaceAll("\\", "_")}'`;
}

function stepNumber(value: number): string {
  // Retain small end caps while emitting STEP REAL syntax, including decimal points.
  return value.toExponential(12).replace("e", "E");
}

/** AP203 faceted B-rep: each closed preview component becomes a separate solid.
 * This first export preserves triangles; it does not reconstruct smooth CAD features.
 */
export function facetedStep(surfaces: readonly SurfaceMeshData[], name: string): string {
  const entities: string[] = [];
  const entity = (value: string) => { entities.push(`#${entities.length + 1}=${value};`); return `#${entities.length}`; };
  const application = entity("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')");
  entity(`APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,${application})`);
  const productContext = entity(`PRODUCT_CONTEXT('',${application},'mechanical')`);
  const product = entity(`PRODUCT(${stepString(name)},${stepString(name)},'',(${productContext}))`);
  const formation = entity(`PRODUCT_DEFINITION_FORMATION('1','',${product})`);
  const definitionContext = entity(`PRODUCT_DEFINITION_CONTEXT('part definition',${application},'design')`);
  const definition = entity(`PRODUCT_DEFINITION('design','',${formation},${definitionContext})`);
  const productShape = entity(`PRODUCT_DEFINITION_SHAPE('','',${definition})`);
  const millimeter = entity("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))");
  const radian = entity("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))");
  const steradian = entity("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())");
  const uncertainty = entity(`UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-6),${millimeter},'distance_accuracy_value','')`);
  const context = entity(`(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((${uncertainty}))GLOBAL_UNIT_ASSIGNED_CONTEXT((${millimeter},${radian},${steradian}))REPRESENTATION_CONTEXT('','3D'))`);
  const bodies = surfaces.map((surface) => {
    const points: string[] = [];
    for (let index = 0; index < surface.positions.length; index += 3) {
      const coordinates = Array.from(surface.positions.slice(index, index + 3), (value) => stepNumber(value * 1000));
      points.push(entity(`CARTESIAN_POINT('',(${coordinates.join(",")}))`));
    }
    const faces: string[] = [];
    for (let offset = 0; offset < surface.indices.length; offset += 3) {
      const loop = entity(`POLY_LOOP('',(${Array.from(surface.indices.slice(offset, offset + 3), (index) => points[index]).join(",")}))`);
      const bound = entity(`FACE_OUTER_BOUND('',${loop},.T.)`);
      const n = normal(surface, offset);
      const length = Math.hypot(...n);
      const a = surface.indices[offset];
      const b = surface.indices[offset + 1];
      const edge = [0, 1, 2].map((axis) => surface.positions[b * 3 + axis] - surface.positions[a * 3 + axis]);
      const edgeLength = Math.hypot(...edge);
      const axis = entity(`DIRECTION('',(${n.map((value) => stepNumber(value / length)).join(",")}))`);
      const reference = entity(`DIRECTION('',(${edge.map((value) => stepNumber(value / edgeLength)).join(",")}))`);
      const placement = entity(`AXIS2_PLACEMENT_3D('',${points[a]},${axis},${reference})`);
      const plane = entity(`PLANE('',${placement})`);
      faces.push(entity(`FACE_SURFACE('',(${bound}),${plane},.T.)`));
    }
    const shell = entity(`CLOSED_SHELL('',(${faces.join(",")}))`);
    return entity(`FACETED_BREP(${stepString(surface.instanceId)},${shell})`);
  });
  const representation = entity(`FACETED_BREP_SHAPE_REPRESENTATION(${stepString(name)},(${bodies.join(",")}),${context})`);
  entity(`SHAPE_DEFINITION_REPRESENTATION(${productShape},${representation})`);
  return [
    "ISO-10303-21;", "HEADER;",
    "FILE_DESCRIPTION(('RapidProcessDesign faceted aircraft geometry; millimeters'),'2;1');",
    `FILE_NAME(${stepString(geometryExportFilename(name, "step"))},${stepString(new Date().toISOString())},(''),(''),'RapidProcessDesign','RapidProcessDesign','');`,
    "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));", "ENDSEC;", "DATA;",
    ...entities, "ENDSEC;", "END-ISO-10303-21;", "",
  ].join("\n");
}

export function createGeometryExport(geometry: GeometryState, name: string, format: GeometryExportFormat): Blob {
  const surfaces = exportSurfaces(geometry);
  return format === "step"
    ? new Blob([facetedStep(surfaces, name)], { type: "application/step" })
    : new Blob([binaryStl(surfaces)], { type: "model/stl" });
}
