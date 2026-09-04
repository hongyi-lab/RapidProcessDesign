"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import styles from "./ParametricAircraftPreview.module.css";
import {
  framingReferenceSize,
  modelScaleForMode,
  orthographicFrustum,
} from "./cameraFraming";
import { createGeometryGroup, disposeObjectResources } from "./threeGeometry";
import type { GeometryScaleMode, GeometryState, GeometryView } from "./types";

export type ParametricAircraftPreviewProps = {
  geometry: GeometryState | null;
  baselineGeometry?: GeometryState | null;
  className?: string;
  view?: GeometryView;
  defaultView?: GeometryView;
  onViewChange?: (view: GeometryView) => void;
  showViewControls?: boolean;
  scaleMode?: GeometryScaleMode;
  defaultScaleMode?: GeometryScaleMode;
  sharedReferenceSize?: number;
  onScaleModeChange?: (mode: GeometryScaleMode) => void;
  showScaleControls?: boolean;
  interactive?: boolean;
};

type PreviewCamera = THREE.PerspectiveCamera | THREE.OrthographicCamera;

type PreviewRuntime = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  perspectiveCamera: THREE.PerspectiveCamera;
  orthographicCamera: THREE.OrthographicCamera;
  activeCamera: PreviewCamera;
  controls: OrbitControls;
  width: number;
  height: number;
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

const SCALE_PRESETS: ReadonlyArray<{ id: GeometryScaleMode; label: string; title: string }> = [
  { id: "auto", label: "自动", title: "当前构型自动充满画幅" },
  { id: "world", label: "同尺度", title: "比较对象使用相同米制比例" },
  { id: "normalized", label: "机长归一", title: "机身长度归一后比较轮廓" },
];

function applyViewPreset(
  runtime: PreviewRuntime,
  preset: GeometryView,
  bounds: ViewBounds,
  referenceSize: number,
): void {
  const { center } = bounds;
  const safeReference = Math.max(0.01, referenceSize);
  const aspect = Math.max(0.05, runtime.width / Math.max(1, runtime.height));
  const camera = preset === "3d"
    ? runtime.perspectiveCamera
    : runtime.orthographicCamera;
  runtime.activeCamera = camera;
  runtime.controls.object = camera;
  runtime.controls.target.copy(center);
  runtime.controls.enableRotate = preset === "3d";

  if (camera instanceof THREE.PerspectiveCamera) {
    camera.aspect = aspect;
    const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
    const distance = (safeReference * 0.67) / Math.tan(halfFov);
    const direction = new THREE.Vector3(-1.25, -1.25, 0.9).normalize();
    camera.up.set(0, 0, 1);
    camera.position.copy(center).addScaledVector(direction, distance);
    camera.near = Math.max(0.005, safeReference / 500);
    camera.far = Math.max(100, distance + safeReference * 30);
    runtime.controls.minDistance = safeReference * 0.12;
    runtime.controls.maxDistance = safeReference * 8;
  } else {
    const frustum = orthographicFrustum(safeReference, aspect);
    camera.left = frustum.left;
    camera.right = frustum.right;
    camera.top = frustum.top;
    camera.bottom = frustum.bottom;
    camera.zoom = 1;
    const distance = safeReference * 3;
    if (preset === "top") {
      camera.up.set(0, 1, 0);
      camera.position.set(center.x, center.y, center.z + distance);
    } else if (preset === "side") {
      camera.up.set(0, 0, 1);
      camera.position.set(center.x, center.y - distance, center.z);
    } else {
      camera.up.set(0, 0, 1);
      camera.position.set(center.x - distance, center.y, center.z);
    }
    camera.near = 0.001;
    camera.far = Math.max(100, safeReference * 10);
    runtime.controls.minZoom = 0.35;
    runtime.controls.maxZoom = 8;
  }
  camera.lookAt(center);
  camera.updateProjectionMatrix();
  runtime.controls.update();
}

function geometryDependencyKey(geometry: GeometryState | null | undefined): string {
  return geometry ? JSON.stringify(geometry) : "none";
}

function scaledGeometryGroup(
  geometry: GeometryState,
  baseline: boolean,
  scaleMode: GeometryScaleMode,
): THREE.Group {
  const group = createGeometryGroup(geometry, baseline);
  const scale = modelScaleForMode(geometry, scaleMode);
  group.scale.setScalar(scale);
  group.updateMatrixWorld(true);
  return group;
}

export function ParametricAircraftPreview({
  geometry,
  baselineGeometry,
  className,
  view,
  defaultView = "3d",
  onViewChange,
  showViewControls = true,
  scaleMode,
  defaultScaleMode = "auto",
  sharedReferenceSize,
  onScaleModeChange,
  showScaleControls = true,
  interactive = true,
}: ParametricAircraftPreviewProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const runtimeRef = useRef<PreviewRuntime | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const boundsRef = useRef<ViewBounds>({
    center: new THREE.Vector3(),
    maxDimension: 10,
  });
  const referenceSizeRef = useRef(10);
  const [internalView, setInternalView] = useState<GeometryView>(defaultView);
  const [internalScaleMode, setInternalScaleMode] = useState<GeometryScaleMode>(defaultScaleMode);
  const effectiveView = view ?? internalView;
  const effectiveScaleMode = scaleMode ?? internalScaleMode;
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
    const perspectiveCamera = new THREE.PerspectiveCamera(34, 1, 0.05, 300);
    const orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 300);
    const controls = new OrbitControls(perspectiveCamera, canvas);
    controls.enableDamping = false;
    controls.enabled = interactive;
    controls.enablePan = false;
    controls.rotateSpeed = 0.62;
    controls.zoomSpeed = 0.72;
    const hemisphere = new THREE.HemisphereLight(0xffffff, 0xd9e1e8, 2.35);
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.55);
    keyLight.position.set(-9, -8, 13);
    const fillLight = new THREE.DirectionalLight(0xc8e1f2, 1.1);
    fillLight.position.set(8, 11, 6);
    scene.add(hemisphere, keyLight, fillLight);

    const runtime = {} as PreviewRuntime;
    Object.assign(runtime, {
      renderer,
      scene,
      perspectiveCamera,
      orthographicCamera,
      activeCamera: perspectiveCamera,
      controls,
      width: 1,
      height: 1,
      render: () => renderer.render(scene, runtime.activeCamera),
    });
    runtimeRef.current = runtime;

    const resize = () => {
      runtime.width = Math.max(1, root.clientWidth);
      runtime.height = Math.max(1, root.clientHeight);
      renderer.setSize(runtime.width, runtime.height, false);
      applyViewPreset(
        runtime,
        selectedViewRef.current,
        boundsRef.current,
        referenceSizeRef.current,
      );
      runtime.render();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(root);
    controls.addEventListener("change", runtime.render);
    resize();

    return () => {
      resizeObserver.disconnect();
      controls.removeEventListener("change", runtime.render);
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
  }, [interactive]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    setGeometryError(null);
    if (!geometry) {
      if (modelRef.current) {
        runtime.scene.remove(modelRef.current);
        disposeObjectResources(modelRef.current);
        modelRef.current = null;
      }
      runtime.render();
      return;
    }

    let nextComparison: THREE.Group | null = new THREE.Group();
    nextComparison.name = "aircraft-geometry-comparison";
    try {
      if (baselineGeometry) {
        nextComparison.add(scaledGeometryGroup(baselineGeometry, true, effectiveScaleMode));
      }
      const currentGroup = scaledGeometryGroup(geometry, false, effectiveScaleMode);
      if (currentGroup.children.length === 0) {
        throw new Error("GeometryState 中没有可显示的有效组件");
      }
      nextComparison.add(currentGroup);
      nextComparison.updateMatrixWorld(true);

      const box = new THREE.Box3().setFromObject(nextComparison);
      if (box.isEmpty()) throw new Error("GeometryState 没有有限的三维边界");
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDimension = Math.max(size.x, size.y, size.z, 1e-3);
      const nextBounds = { center, maxDimension };
      const referenceSize = framingReferenceSize(
        maxDimension,
        effectiveScaleMode,
        sharedReferenceSize,
      );

      runtime.scene.add(nextComparison);
      const previous = modelRef.current;
      modelRef.current = nextComparison;
      nextComparison = null;
      if (previous) {
        runtime.scene.remove(previous);
        disposeObjectResources(previous);
      }
      boundsRef.current = nextBounds;
      referenceSizeRef.current = referenceSize;
      applyViewPreset(runtime, selectedViewRef.current, nextBounds, referenceSize);
      runtime.render();
    } catch (reason) {
      if (nextComparison) disposeObjectResources(nextComparison);
      setGeometryError(reason instanceof Error ? reason.message : "几何数据无法显示");
      runtime.render();
    }
  }, [
    geometry,
    geometryKey,
    baselineGeometry,
    baselineKey,
    effectiveScaleMode,
    sharedReferenceSize,
  ]);

  useEffect(() => {
    selectedViewRef.current = effectiveView;
    const runtime = runtimeRef.current;
    if (!runtime) return;
    applyViewPreset(runtime, effectiveView, boundsRef.current, referenceSizeRef.current);
    runtime.render();
  }, [effectiveView]);

  function chooseView(nextView: GeometryView): void {
    selectedViewRef.current = nextView;
    if (view === undefined) setInternalView(nextView);
    onViewChange?.(nextView);
  }

  function chooseScaleMode(nextMode: GeometryScaleMode): void {
    if (scaleMode === undefined) setInternalScaleMode(nextMode);
    onScaleModeChange?.(nextMode);
  }

  const rootClassName = className ? `${styles.root} ${className}` : styles.root;
  const fallbackMessage = rendererError ?? geometryError;
  return (
    <div ref={rootRef} className={rootClassName} data-scale-mode={effectiveScaleMode}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        aria-label="可旋转的整机参数化三维预览"
        tabIndex={interactive ? 0 : -1}
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
      {showScaleControls ? (
        <div className={styles.scaleControls} role="toolbar" aria-label="预览尺度模式">
          {SCALE_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`${styles.scaleButton} ${
                effectiveScaleMode === preset.id ? styles.scaleButtonActive : ""
              }`}
              aria-pressed={effectiveScaleMode === preset.id}
              title={preset.title}
              onClick={() => chooseScaleMode(preset.id)}
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
