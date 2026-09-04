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
  /** Optional explicit mean-line camber; otherwise derived from a supported airfoil_id. */
  camber_ratio?: number | null;
  camber_position_ratio?: number | null;
  /** Preserve deliberate planform breaks while allowing smooth spanwise lofts elsewhere. */
  interpolation_to_next?: "smooth" | "linear";
};

export type LiftingSurfaceComponent = {
  id: string;
  kind: "lifting_surface";
  symmetry: "none" | "y";
  /** Omitted values are horizontal for backwards-compatible envelopes. */
  orientation?: "horizontal" | "vertical";
  /** Span-axis offset; used by fins and pylons away from the aircraft centreline. */
  centerline_y_m?: number;
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

export type PropellerComponent = {
  id: string;
  kind: "propeller";
  symmetry: "none" | "y";
  center_x_m: number;
  centerline_y_m: number;
  center_z_m: number;
  radius_m: number;
  hub_radius_m: number;
  hub_length_m: number;
  blade_count: number;
  blade_chord_m: number;
  rotation_deg: number;
};

export type GeometryComponent =
  | LoftBodyComponent
  | LiftingSurfaceComponent
  | NacelleComponent
  | PropellerComponent;

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
export type GeometryScaleMode = "auto" | "world" | "normalized";
