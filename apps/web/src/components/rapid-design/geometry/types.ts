export type GeometryVector3 = {
  x: number;
  y: number;
  z: number;
};

export type LoftBodyStation = {
  x_m: number;
  /** Full cross-section width, not semi-width. */
  width_m: number;
  /** Full cross-section height, not semi-height. */
  height_m: number;
  z_offset_m: number;
  /** 2 is elliptical; larger values make a progressively squarer superellipse. */
  shape_exponent: number;
};

export type LoftBodyComponent = {
  id: string;
  kind: "loft_body";
  stations: readonly LoftBodyStation[];
};

export type LiftingSurfaceSection = {
  /** Horizontal semi-span station, or the vertical fin's local span station. */
  y_m: number;
  leading_edge_x_m: number;
  /** Absolute leading-edge height at this station. */
  leading_edge_z_m: number;
  chord_m: number;
  twist_deg: number;
  dihedral_deg: number;
  thickness_ratio: number;
  airfoil_id: string;
};

export type LiftingSurfaceComponent = {
  id: string;
  kind: "lifting_surface";
  symmetry: "none" | "y";
  /** Omitted values are horizontal for backwards-compatible envelopes. */
  orientation?: "horizontal" | "vertical";
  sections: readonly LiftingSurfaceSection[];
};

export type NacelleStation = {
  x_m: number;
  radius_y_m: number;
  radius_z_m: number;
  z_offset_m: number;
};

export type NacelleComponent = {
  id: string;
  kind: "nacelle";
  symmetry: "none" | "y";
  /** Positive-side centreline; symmetry=y mirrors it across the aircraft plane. */
  centerline_y_m: number;
  stations: readonly NacelleStation[];
};

export type GeometryComponent =
  | LoftBodyComponent
  | LiftingSurfaceComponent
  | NacelleComponent;

export type GeometryCheck = {
  id?: string;
  name?: string;
  status?: "pass" | "warning" | "fail" | string;
  message?: string;
  [key: string]: unknown;
};

/**
 * Family-neutral geometry contract returned by the Rapid Design API.
 *
 * Renderers intentionally receive no family design variables. Family decoders
 * own the conversion from high-level controls into these canonical components.
 */
export type GeometryState = {
  family_id: string;
  geometry_version: string;
  geometry_status: "valid" | "invalid";
  components: readonly GeometryComponent[];
  derived_metrics?: Readonly<Record<string, unknown>>;
  geometry_checks?: readonly GeometryCheck[];
  provenance?: Readonly<Record<string, unknown>>;
};

export type GeometryView = "3d" | "top" | "side" | "front";
