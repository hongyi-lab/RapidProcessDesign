"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import styles from "./ParametricAircraftPreview.module.css";
import { createGeometryGroup, disposeObjectResources } from "./threeGeometry";
import type { GeometryState, GeometryView } from "./types";

export type ParametricAircraftPreviewProps = {
  geometry: GeometryState | null;
  baselineGeometry?: GeometryState | null;
  className?: string;
  view?: GeometryView;
  defaultView?: GeometryView;
  onViewChange?: (view: GeometryView) => void;
  showViewControls?: boolean;
};

type PreviewRuntime = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  render: () => void;
};

type ViewBounds = {
  center: THREE.Vector3;
  maxDimension: number;
};

const VIEW_PRESETS: ReadonlyArray<{ id: GeometryView; label: string }> = [
  { id: "3d", label: "3D" },
  { id: "top", label: "顶视" },
  { id: "side", label: "侧视" },
  { id: "front", label: "前视" },
];

function applyViewPreset(
  preset: GeometryView,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  bounds: ViewBounds,
): void {
  const { center, maxDimension } = bounds;
  const distance = maxDimension * 1.9;
  controls.target.copy(center);
  if (preset === "top") {
    camera.up.set(0, 1, 0);
    camera.position.set(center.x, center.y, center.z + distance);
  } else if (preset === "side") {
    camera.up.set(0, 0, 1);
    camera.position.set(center.x, center.y - distance, center.z);
  } else if (preset === "front") {
    camera.up.set(0, 0, 1);
    camera.position.set(center.x - distance, center.y, center.z);
  } else {
    camera.up.set(0, 0, 1);
    camera.position.set(
      center.x - maxDimension * 1.25,
      center.y - maxDimension * 1.25,
      center.z + maxDimension * 0.9,
    );
  }
  camera.near = Math.max(0.01, maxDimension / 300);
  camera.far = Math.max(100, maxDimension * 20);
  camera.updateProjectionMatrix();
  camera.lookAt(center);
  controls.minDistance = maxDimension * 0.16;
  controls.maxDistance = maxDimension * 7;
  controls.update();
}

function geometryDependencyKey(geometry: GeometryState | null | undefined): string {
  return geometry ? JSON.stringify(geometry) : "none";
}

export function ParametricAircraftPreview({
  geometry,
  baselineGeometry,
  className,
  view,
  defaultView = "3d",
  onViewChange,
  showViewControls = true,
}: ParametricAircraftPreviewProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const runtimeRef = useRef<PreviewRuntime | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const boundsRef = useRef<ViewBounds>({
    center: new THREE.Vector3(),
    maxDimension: 10,
  });
  const [internalView, setInternalView] = useState<GeometryView>(defaultView);
  const effectiveView = view ?? internalView;
  const selectedViewRef = useRef<GeometryView>(effectiveView);
  const [rendererError, setRendererError] = useState<string | null>(null);
  const [geometryError, setGeometryError] = useState<string | null>(null);
  const geometryKey = geometryDependencyKey(geometry);
  const baselineKey = geometryDependencyKey(baselineGeometry);

  useEffect(() => {
    const canvas = canvasRef.current;
    const root = rootRef.current;
    if (!canvas || !root) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: false,
        antialias: true,
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
    renderer.toneMappingExposure = 1.05;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.05, 300);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = false;
    controls.enablePan = false;
    controls.rotateSpeed = 0.62;
    controls.zoomSpeed = 0.72;
    const hemisphere = new THREE.HemisphereLight(0xffffff, 0xd9e1e8, 2.35);
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.55);
    keyLight.position.set(-9, -8, 13);
    const fillLight = new THREE.DirectionalLight(0xc8e1f2, 1.1);
    fillLight.position.set(8, 11, 6);
    scene.add(hemisphere, keyLight, fillLight);

    const render = () => renderer.render(scene, camera);
    runtimeRef.current = { renderer, scene, camera, controls, render };
    applyViewPreset(selectedViewRef.current, camera, controls, boundsRef.current);

    const resize = () => {
      const width = Math.max(1, root.clientWidth);
      const height = Math.max(1, root.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
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
        disposeObjectResources(modelRef.current);
        modelRef.current = null;
      }
      scene.clear();
      renderer.renderLists.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      runtimeRef.current = null;
    };
  }, []);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    if (modelRef.current) {
      runtime.scene.remove(modelRef.current);
      disposeObjectResources(modelRef.current);
      modelRef.current = null;
    }
    setGeometryError(null);
    if (!geometry) {
      runtime.render();
      return;
    }

    try {
      const comparison = new THREE.Group();
      comparison.name = "aircraft-geometry-comparison";
      if (baselineGeometry) comparison.add(createGeometryGroup(baselineGeometry, true));
      comparison.add(createGeometryGroup(geometry, false));
      if (comparison.children.every((group) => group.children.length === 0)) {
        throw new Error("GeometryState 中没有可显示的有效组件");
      }
      runtime.scene.add(comparison);
      modelRef.current = comparison;

      const box = new THREE.Box3().setFromObject(comparison);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDimension = Math.max(size.x, size.y, size.z, 1);
      boundsRef.current = { center, maxDimension };
      applyViewPreset(
        selectedViewRef.current,
        runtime.camera,
        runtime.controls,
        boundsRef.current,
      );
      runtime.render();
    } catch (reason) {
      setGeometryError(reason instanceof Error ? reason.message : "几何数据无法显示");
      runtime.render();
    }
  }, [geometry, geometryKey, baselineGeometry, baselineKey]);

  useEffect(() => {
    selectedViewRef.current = effectiveView;
    const runtime = runtimeRef.current;
    if (!runtime) return;
    applyViewPreset(effectiveView, runtime.camera, runtime.controls, boundsRef.current);
    runtime.render();
  }, [effectiveView]);

  function chooseView(nextView: GeometryView): void {
    selectedViewRef.current = nextView;
    if (view === undefined) setInternalView(nextView);
    onViewChange?.(nextView);
  }

  const rootClassName = className ? `${styles.root} ${className}` : styles.root;
  const fallbackMessage = rendererError ?? geometryError;
  return (
    <div ref={rootRef} className={rootClassName}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        aria-label="可旋转的整机参数化三维预览"
        tabIndex={0}
      />
      {showViewControls ? (
        <div className={styles.viewControls} role="toolbar" aria-label="三维预览视角">
          {VIEW_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`${styles.viewButton} ${
                effectiveView === preset.id ? styles.viewButtonActive : ""
              }`}
              aria-pressed={effectiveView === preset.id}
              onClick={() => chooseView(preset.id)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      ) : null}
      {baselineGeometry && geometry ? (
        <div className={styles.legend} aria-label="几何对比图例">
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} aria-hidden="true" />当前
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendWire} aria-hidden="true" />基准
          </span>
        </div>
      ) : null}
      {!geometry && !fallbackMessage ? (
        <div className={styles.fallback} role="status">
          <strong>等待几何数据</strong>
          <span>调整参数后将在这里显示整机外形。</span>
        </div>
      ) : null}
      {fallbackMessage ? (
        <div className={styles.fallback} role="status" title={fallbackMessage}>
          <strong>当前几何无法显示</strong>
          <span>{fallbackMessage}</span>
        </div>
      ) : null}
    </div>
  );
}

