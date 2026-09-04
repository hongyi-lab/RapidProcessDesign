import * as THREE from "three";

import { buildGeometrySurfaces, type SurfaceMeshData } from "./geometrySurfaces.ts";
import type { GeometryComponent, GeometryState } from "./types";

const CURRENT_COLORS: Readonly<Record<GeometryComponent["kind"], number>> = {
  loft_body: 0x8da4b5,
  lifting_surface: 0x2f78a8,
  nacelle: 0x5f7484,
};

export type DisposedResourceCounts = {
  geometries: number;
  materials: number;
  textures: number;
};

export function surfaceToBufferGeometry(surface: SurfaceMeshData): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(surface.positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(surface.indices, 1));
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function collectMaterialTextures(material: THREE.Material, textures: Set<THREE.Texture>): void {
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) textures.add(value);
  }
}

/** Dispose every GPU resource owned by an object exactly once. */
export function disposeObjectResources(object: THREE.Object3D): DisposedResourceCounts {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  object.traverse((child) => {
    if ("geometry" in child && child.geometry instanceof THREE.BufferGeometry) {
      geometries.add(child.geometry);
    }
    if ("material" in child) {
      const childMaterials = Array.isArray(child.material) ? child.material : [child.material];
      for (const material of childMaterials) {
        if (material instanceof THREE.Material) materials.add(material);
      }
    }
  });
  materials.forEach((material) => collectMaterialTextures(material, textures));
  textures.forEach((texture) => texture.dispose());
  geometries.forEach((geometry) => geometry.dispose());
  materials.forEach((material) => material.dispose());
  return {
    geometries: geometries.size,
    materials: materials.size,
    textures: textures.size,
  };
}

export function createGeometryGroup(
  geometryState: GeometryState,
  baseline = false,
): THREE.Group {
  const group = new THREE.Group();
  group.name = baseline ? "geometry-baseline" : "geometry-current";
  const surfaces = buildGeometrySurfaces(geometryState);
  for (const surface of surfaces) {
    const geometry = surfaceToBufferGeometry(surface);
    const material = baseline
      ? new THREE.MeshBasicMaterial({
          color: 0x8b99a7,
          depthWrite: false,
          opacity: 0.72,
          side: THREE.DoubleSide,
          transparent: true,
          wireframe: true,
        })
      : new THREE.MeshStandardMaterial({
          color: CURRENT_COLORS[surface.componentKind],
          emissive: 0x071d2b,
          emissiveIntensity: 0.025,
          metalness: 0.04,
          roughness: 0.64,
          side: THREE.DoubleSide,
        });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `${baseline ? "baseline" : "current"}-${surface.instanceId}`;
    mesh.userData.componentId = surface.componentId;
    mesh.userData.componentKind = surface.componentKind;
    mesh.renderOrder = baseline ? 4 : 1;
    group.add(mesh);
  }
  return group;
}
