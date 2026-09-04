export { ParametricAircraftPreview } from "./ParametricAircraftPreview";
export type { ParametricAircraftPreviewProps } from "./ParametricAircraftPreview";
export {
  buildComponentSurfaces,
  buildGeometrySurfaces,
  buildLiftingSurface,
  buildLoftBodySurface,
  buildNacelleSurfaces,
} from "./geometrySurfaces";
export type { SurfaceBuildOptions, SurfaceMeshData } from "./geometrySurfaces";
export {
  createGeometryGroup,
  disposeObjectResources,
  surfaceToBufferGeometry,
} from "./threeGeometry";
export type { DisposedResourceCounts } from "./threeGeometry";
export type {
  GeometryCheck,
  GeometryComponent,
  GeometryState,
  GeometryVector3,
  GeometryView,
  LiftingSurfaceComponent,
  LiftingSurfaceSection,
  LoftBodyComponent,
  LoftBodyStation,
  NacelleComponent,
  NacelleStation,
} from "./types";

