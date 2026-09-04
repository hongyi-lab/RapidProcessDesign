import type { GeometryState, GeometryScaleMode } from "./types";

const MINIMUM_SIZE = 1e-4;

function finitePositive(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > MINIMUM_SIZE
    ? value
    : null;
}

/** Return the canonical body length without depending on a family-specific design vector. */
export function geometryFuselageLength(geometry: GeometryState | null | undefined): number {
  const metric = finitePositive(geometry?.derived_metrics?.fuselage_length_m);
  if (metric) return metric;
  const bodies = geometry?.components.filter((component) => component.kind === "loft_body") ?? [];
  const extents = bodies.map((body) => {
    const xs = body.stations.map((station) => station.x_m).filter(Number.isFinite);
    return xs.length > 1 ? Math.max(...xs) - Math.min(...xs) : 0;
  });
  const bodyLength = Math.max(0, ...extents);
  if (bodyLength > MINIMUM_SIZE) return bodyLength;

  // BWB and future tailless families may have no loft_body. In that case the
  // canonical longitudinal envelope is the meaningful normalization length.
  const xValues: number[] = [];
  for (const component of geometry?.components ?? []) {
    if (component.kind === "lifting_surface") {
      component.sections.forEach((section) => {
        xValues.push(section.leading_edge_x_m, section.leading_edge_x_m + section.chord_m);
      });
    } else if (component.kind === "nacelle") {
      component.stations.forEach((station) => xValues.push(station.x_m));
    } else if (component.kind === "propeller") {
      xValues.push(
        component.center_x_m - component.hub_length_m / 2,
        component.center_x_m + component.hub_length_m / 2,
      );
    }
  }
  const finiteValues = xValues.filter(Number.isFinite);
  return finiteValues.length > 1
    ? Math.max(MINIMUM_SIZE, Math.max(...finiteValues) - Math.min(...finiteValues))
    : 1;
}

/** A stable, family-neutral estimate of the largest world-space aircraft dimension. */
export function geometryNominalSize(geometry: GeometryState | null | undefined): number {
  if (!geometry) return 1;
  const metricCandidates = [
    geometry.derived_metrics?.span_m,
    geometry.derived_metrics?.fuselage_length_m,
    geometry.derived_metrics?.fuselage_max_width_m,
    geometry.derived_metrics?.fuselage_max_height_m,
  ].map(finitePositive).filter((value): value is number => value !== null);
  if (metricCandidates.length > 0) return Math.max(...metricCandidates);

  const coordinates: Array<readonly [number, number, number]> = [];
  for (const component of geometry.components) {
    if (component.kind === "loft_body") {
      component.stations.forEach((station) => {
        coordinates.push(
          [station.x_m, -station.width_m / 2, station.z_offset_m - station.height_m / 2],
          [station.x_m, station.width_m / 2, station.z_offset_m + station.height_m / 2],
        );
      });
    } else if (component.kind === "lifting_surface") {
      const centerY = component.centerline_y_m ?? 0;
      component.sections.forEach((section) => {
        const ys = component.symmetry === "y"
          ? [centerY - Math.abs(section.y_m), centerY + Math.abs(section.y_m)]
          : [centerY + section.y_m];
        ys.forEach((y) => coordinates.push(
          [section.leading_edge_x_m, y, section.leading_edge_z_m],
          [section.leading_edge_x_m + section.chord_m, y, section.leading_edge_z_m],
        ));
      });
    } else if (component.kind === "nacelle") {
      const ys = component.symmetry === "y"
        ? [-Math.abs(component.centerline_y_m), Math.abs(component.centerline_y_m)]
        : [component.centerline_y_m];
      component.stations.forEach((station) => ys.forEach((y) => coordinates.push(
        [station.x_m, y - station.radius_y_m, station.z_offset_m - station.radius_z_m],
        [station.x_m, y + station.radius_y_m, station.z_offset_m + station.radius_z_m],
      )));
    } else if (component.kind === "propeller") {
      const ys = component.symmetry === "y"
        ? [-Math.abs(component.centerline_y_m), Math.abs(component.centerline_y_m)]
        : [component.centerline_y_m];
      ys.forEach((y) => coordinates.push(
        [component.center_x_m, y - component.radius_m, component.center_z_m - component.radius_m],
        [component.center_x_m, y + component.radius_m, component.center_z_m + component.radius_m],
      ));
    }
  }
  if (coordinates.length === 0) return 1;
  const axes = [0, 1, 2] as const;
  return Math.max(
    1,
    ...axes.map((axis) => {
      const values = coordinates.map((point) => point[axis]).filter(Number.isFinite);
      return values.length > 1 ? Math.max(...values) - Math.min(...values) : 0;
    }),
  );
}

export function modelScaleForMode(
  geometry: GeometryState | null | undefined,
  mode: GeometryScaleMode,
): number {
  return mode === "normalized" ? 1 / geometryFuselageLength(geometry) : 1;
}

export function framingReferenceSize(
  ownSize: number,
  mode: GeometryScaleMode,
  sharedReferenceSize?: number,
): number {
  const safeOwnSize = finitePositive(ownSize) ?? 1;
  if (mode === "auto") return safeOwnSize;
  return finitePositive(sharedReferenceSize) ?? safeOwnSize;
}

export type OrthographicFrustum = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

/** Fit a padded square reference dimension without cropping at any aspect ratio. */
export function orthographicFrustum(
  referenceSize: number,
  aspect: number,
  padding = 1.18,
): OrthographicFrustum {
  const safeReference = finitePositive(referenceSize) ?? 1;
  const safeAspect = finitePositive(aspect) ?? 1;
  const paddedHalfSize = 0.5 * safeReference * Math.max(1, padding);
  const halfHeight = safeAspect >= 1 ? paddedHalfSize : paddedHalfSize / safeAspect;
  const halfWidth = safeAspect >= 1 ? paddedHalfSize * safeAspect : paddedHalfSize;
  return {
    left: -halfWidth,
    right: halfWidth,
    top: halfHeight,
    bottom: -halfHeight,
  };
}
