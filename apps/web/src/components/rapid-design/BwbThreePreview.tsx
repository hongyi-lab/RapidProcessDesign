"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import {
  buildBwbSurfaceData,
  normalizeBwbDesign,
  type BwbDesignVariables,
} from "./bwbGeometry";
import styles from "./BwbThreePreview.module.css";

export {
  BWB_DESIGN_BOUNDS,
  DEFAULT_BWB_DESIGN,
  buildBwbSurfaceData,
  deriveBwbPlanformStations,
  normalizeBwbDesign,
} from "./bwbGeometry";
export type {
  BwbDesignVariables,
  BwbGeometryMetrics,
  BwbPlanformStation,
  BwbSurfaceData,
  BwbSurfaceOptions,
  BwbVariableBounds,
} from "./bwbGeometry";

export type BwbThreePreviewProps = {
  design: BwbDesignVariables;
  baselineDesign?: BwbDesignVariables;
  className?: string;
};

type ViewPreset = "perspective" | "top" | "front";

type PreviewRuntime = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  render: () => void;
};

type ViewBounds = {
  centreX: number;
  centreY: number;
  centreZ: number;
  maxDimension: number;
};

const VIEW_PRESETS: ReadonlyArray<{ id: ViewPreset; label: string }> = [
  { id: "perspective", label: "3D" },
  { id: "top", label: "顶视" },
  { id: "front", label: "前视" },
];

function disposeMaterial(material: THREE.Material): void {
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) value.dispose();
  }
  material.dispose();
}

function disposeObject(object: THREE.Object3D): void {
  const materials = new Set<THREE.Material>();
  const geometries = new Set<THREE.BufferGeometry>();
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
  geometries.forEach((geometry) => geometry.dispose());
  materials.forEach(disposeMaterial);
}

function toBufferGeometry(design: BwbDesignVariables): {
  geometry: THREE.BufferGeometry;
  outline: THREE.BufferGeometry;
} {
  const surface = buildBwbSurfaceData(design);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(surface.positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(surface.indices, 1));
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();

  const outline = new THREE.BufferGeometry();
  outline.setAttribute("position", new THREE.BufferAttribute(surface.outlinePositions, 3));
  return { geometry, outline };
}

function createCurrentModel(design: BwbDesignVariables): THREE.Group {
  const { geometry, outline } = toBufferGeometry(design);
  const group = new THREE.Group();
  group.name = "bwb-current-design";

  const surface = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: 0x2079b0,
      emissive: 0x082f49,
      emissiveIntensity: 0.035,
      metalness: 0.06,
      roughness: 0.5,
      side: THREE.DoubleSide,
    }),
  );
  surface.name = "bwb-smooth-loft";
  surface.castShadow = false;
  surface.receiveShadow = false;
  group.add(surface);

  const perimeter = new THREE.LineLoop(
    outline,
    new THREE.LineBasicMaterial({
      color: 0x0d4f7d,
      transparent: true,
      opacity: 0.82,
      depthTest: false,
    }),
  );
  perimeter.name = "bwb-planform-outline";
  perimeter.renderOrder = 2;
  group.add(perimeter);

  return group;
}

function createBaselineModel(design: BwbDesignVariables): THREE.Group {
  const { geometry, outline } = toBufferGeometry(design);
  // A perimeter is clearer than a dense triangle wireframe when the baseline
  // and current design overlap, and still makes planform changes easy to read.
  geometry.dispose();
  const group = new THREE.Group();
  group.name = "bwb-baseline-design";
  const perimeter = new THREE.LineLoop(
    outline,
    new THREE.LineBasicMaterial({
      color: 0xaab5c0,
      transparent: true,
      opacity: 0.9,
      depthTest: false,
    }),
  );
  perimeter.renderOrder = 3;
  group.add(perimeter);
  return group;
}

function applyViewPreset(
  preset: ViewPreset,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  bounds: ViewBounds,
): void {
  const { centreX, centreY, centreZ, maxDimension } = bounds;
  const target = new THREE.Vector3(centreX, centreY, centreZ);
  controls.target.copy(target);

  if (preset === "top") {
    camera.up.set(0, 1, 0);
    camera.position.set(centreX, centreY, centreZ + maxDimension * 1.84);
  } else if (preset === "front") {
    camera.up.set(0, 0, 1);
    camera.position.set(
      centreX - maxDimension * 1.86,
      centreY,
      centreZ + maxDimension * 0.08,
    );
  } else {
    camera.up.set(0, 0, 1);
    camera.position.set(
      centreX - maxDimension * 1.2,
      centreY,
      centreZ + maxDimension * 0.95,
    );
  }

  camera.near = Math.max(0.01, maxDimension / 250);
  camera.far = maxDimension * 20;
  camera.updateProjectionMatrix();
  camera.lookAt(target);
  controls.minDistance = maxDimension * 0.22;
  controls.maxDistance = maxDimension * 5;
  controls.update();
}

function designDependencyKey(design: BwbDesignVariables | undefined): string {
  if (!design) return "none";
  return [
    design.c1M,
    design.c2Ratio,
    design.c3Ratio,
    design.c4Ratio,
    design.b1Ratio,
    design.b2Ratio,
    design.b3Ratio,
    design.x3Ratio,
    design.sweepInnerDeg,
    design.sweepOuterDeg,
    design.thicknessRatio,
    design.twistTipDeg,
  ].join("|");
}

export function BwbThreePreview({
  design,
  baselineDesign,
  className,
}: BwbThreePreviewProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const runtimeRef = useRef<PreviewRuntime | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const viewBoundsRef = useRef<ViewBounds>({
    centreX: 0,
    centreY: 0,
    centreZ: 0,
    maxDimension: 10,
  });
  const selectedViewRef = useRef<ViewPreset>("perspective");
  const [selectedView, setSelectedView] = useState<ViewPreset>("perspective");
  const [rendererError, setRendererError] = useState<string | null>(null);

  const designKey = designDependencyKey(design);
  const baselineKey = designDependencyKey(baselineDesign);
  const normalizedDesign = useMemo(() => normalizeBwbDesign(design), [designKey]);
  const normalizedBaseline = useMemo(
    () => (baselineDesign ? normalizeBwbDesign(baselineDesign) : undefined),
    [baselineKey],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const root = rootRef.current;
    if (!canvas || !root) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      });
    } catch (reason) {
      setRendererError(reason instanceof Error ? reason.message : "WebGL 初始化失败");
      return;
    }

    renderer.setClearColor(0xf7f9fb, 1);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.04;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xf7f9fb, 80, 240);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.05, 300);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = false;
    controls.enablePan = false;
    controls.rotateSpeed = 0.62;
    controls.zoomSpeed = 0.72;

    const hemisphere = new THREE.HemisphereLight(0xffffff, 0xd6e0e8, 2.25);
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
    keyLight.position.set(-9, -8, 13);
    const fillLight = new THREE.DirectionalLight(0xc7e4f7, 1.15);
    fillLight.position.set(8, 11, 5);
    scene.add(hemisphere, keyLight, fillLight);

    const render = () => renderer.render(scene, camera);
    const runtime = { renderer, scene, camera, controls, render };
    runtimeRef.current = runtime;
    applyViewPreset(selectedViewRef.current, camera, controls, viewBoundsRef.current);

    const resize = () => {
      const width = Math.max(1, root.clientWidth);
      const height = Math.max(1, root.clientHeight);
      const pixelRatio = renderer.getPixelRatio();
      const drawingBufferWidth = Math.round(width * pixelRatio);
      const drawingBufferHeight = Math.round(height * pixelRatio);
      if (canvas.width !== drawingBufferWidth || canvas.height !== drawingBufferHeight) {
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
      render();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(root);
    controls.addEventListener("change", render);
    resize();

    return () => {
      resizeObserver.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      if (modelRef.current) {
        scene.remove(modelRef.current);
        disposeObject(modelRef.current);
        modelRef.current = null;
      }
      renderer.renderLists.dispose();
      renderer.dispose();
      runtimeRef.current = null;
    };
  }, []);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    const { scene, camera, controls } = runtime;
    if (modelRef.current) {
      scene.remove(modelRef.current);
      disposeObject(modelRef.current);
    }

    const assembly = new THREE.Group();
    assembly.name = "bwb-design-comparison";
    if (normalizedBaseline) assembly.add(createBaselineModel(normalizedBaseline));
    const current = createCurrentModel(normalizedDesign);
    assembly.add(current);
    scene.add(assembly);
    modelRef.current = assembly;

    // Fit the union, not just the current design. A larger stored baseline must
    // remain visible and inside the fog range during direct shape comparison.
    const modelBounds = new THREE.Box3().setFromObject(assembly);
    const centre = modelBounds.getCenter(new THREE.Vector3());
    const size = modelBounds.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z, 1);
    viewBoundsRef.current = {
      centreX: centre.x,
      centreY: centre.y,
      centreZ: centre.z,
      maxDimension,
    };
    if (scene.fog instanceof THREE.Fog) {
      scene.fog.near = maxDimension * 1.65;
      scene.fog.far = maxDimension * 4.2;
    }
    applyViewPreset(selectedViewRef.current, camera, controls, viewBoundsRef.current);
    runtime.render();
  }, [designKey, baselineKey, normalizedDesign, normalizedBaseline]);

  function chooseView(preset: ViewPreset): void {
    selectedViewRef.current = preset;
    setSelectedView(preset);
    const runtime = runtimeRef.current;
    if (runtime) {
      applyViewPreset(preset, runtime.camera, runtime.controls, viewBoundsRef.current);
      runtime.render();
    }
  }

  const rootClassName = className ? `${styles.root} ${className}` : styles.root;
  return (
    <div ref={rootRef} className={rootClassName}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        aria-label="可旋转的翼身融合飞机三维参数化预览"
        tabIndex={0}
      />
      <div className={styles.viewControls} role="toolbar" aria-label="三维预览视角">
        {VIEW_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`${styles.viewButton} ${
              selectedView === preset.id ? styles.viewButtonActive : ""
            }`}
            aria-pressed={selectedView === preset.id}
            onClick={() => chooseView(preset.id)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      {rendererError ? (
        <div className={styles.fallback} role="status" title={rendererError}>
          <strong>当前环境无法显示三维预览</strong>
          <span>设计参数与分析功能仍可继续使用。</span>
        </div>
      ) : null}
    </div>
  );
}
