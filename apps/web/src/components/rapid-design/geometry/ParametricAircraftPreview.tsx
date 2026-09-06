"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import styles from "./ParametricAircraftPreview.module.css";
import {
  framingReferenceSize,
  modelScaleForMode,
  orthographicFrustum,
  perspectiveFitDistance,
  PREVIEW_DIRECTION,
  type GeometryFrame,
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
  sharedFrame?: GeometryFrame;
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
  size: THREE.Vector3;
  fitToGeometry: boolean;
};

const VIEW_PRESETS: ReadonlyArray<{ id: GeometryView; label: string }> = [
  { id: "3d", label: "3D" },
  { id: "top", label: "Top" },
  { id: "side", label: "Side" },
  { id: "front", label: "Front" },
];

const SCALE_PRESETS: ReadonlyArray<{ id: GeometryScaleMode; label: string; title: string }> = [
  { id: "auto", label: "Fit view", title: "Fit the current aircraft to the view" },
  { id: "world", label: "Same scale", title: "Keep the same physical scale when comparing aircraft" },
  { id: "normalized", label: "Body length", title: "Normalize body length to compare shapes" },
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
    const distance = bounds.fitToGeometry
      ? perspectiveFitDistance(bounds.size.toArray(), aspect, camera.fov)
      : (safeReference * 0.67) / Math.min(Math.tan(halfFov), Math.tan(halfFov) * aspect);
    const direction = new THREE.Vector3(...PREVIEW_DIRECTION).normalize();
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
  sharedFrame,
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
    size: new THREE.Vector3(10, 10, 2),
    fitToGeometry: true,
  });
  const referenceSizeRef = useRef(10);
  const [internalView, setInternalView] = useState<GeometryView>(defaultView);
  const [internalScaleMode, setInternalScaleMode] = useState<GeometryScaleMode>(defaultScaleMode);
  const [showBaseline, setShowBaseline] = useState(false);
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
      setRendererError(reason instanceof Error ? reason.message : "3D preview could not start");
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
    controls.enableZoom = false;
    // Ordinary scrolling moves the page; zoom is an intentional modified gesture.
    const onWheel = (event: WheelEvent) => {
      controls.enableZoom = event.ctrlKey || event.metaKey;
    };
    canvas.addEventListener("wheel", onWheel, { capture: true, passive: true });
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
      canvas.removeEventListener("wheel", onWheel, true);
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
      if (baselineGeometry && showBaseline) {
        nextComparison.add(scaledGeometryGroup(baselineGeometry, true, effectiveScaleMode));
      }
      const currentGroup = scaledGeometryGroup(geometry, false, effectiveScaleMode);
      if (currentGroup.children.length === 0) {
        throw new Error("No valid components to display");
      }
      nextComparison.add(currentGroup);
      nextComparison.updateMatrixWorld(true);

      const box = effectiveScaleMode === "world" && sharedFrame
        ? new THREE.Box3(new THREE.Vector3(...sharedFrame.min), new THREE.Vector3(...sharedFrame.max))
        : new THREE.Box3().setFromObject(nextComparison);
      if (box.isEmpty()) throw new Error("Geometry bounds are invalid");
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDimension = Math.max(size.x, size.y, size.z, 1e-3);
      const nextBounds = {
        center, maxDimension, size,
        fitToGeometry: effectiveScaleMode === "auto" || (effectiveScaleMode === "world" && Boolean(sharedFrame)),
      };
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
      setGeometryError(reason instanceof Error ? reason.message : "Unable to display this geometry");
      runtime.render();
    }
  }, [
    geometry,
    geometryKey,
    baselineGeometry,
    baselineKey,
    showBaseline,
    effectiveScaleMode,
    sharedReferenceSize,
    sharedFrame,
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
        aria-label="Interactive 3D aircraft preview"
        tabIndex={interactive ? 0 : -1}
      />
      {showViewControls ? (
        <div className={styles.viewControls} role="toolbar" aria-label="Aircraft view">
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
        <div className={styles.scaleControls} role="toolbar" aria-label="View scale">
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
      <div className={styles.previewFooter}>
        {interactive && <span>Drag to rotate · Ctrl + scroll to zoom</span>}
        {baselineGeometry && geometry && (
          <button type="button" aria-pressed={showBaseline} onClick={() => setShowBaseline((current) => !current)}>
            {showBaseline ? "Hide baseline" : "Overlay baseline"}
          </button>
        )}
        {interactive && <button type="button" onClick={() => {
          const runtime = runtimeRef.current;
          if (!runtime) return;
          applyViewPreset(runtime, effectiveView, boundsRef.current, referenceSizeRef.current);
          runtime.render();
        }}>Reset view</button>}
      </div>
      {baselineGeometry && geometry && showBaseline ? (
        <div className={styles.legend} aria-label="Comparison legend">
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} aria-hidden="true" />Current
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendWire} aria-hidden="true" />Baseline
          </span>
        </div>
      ) : null}
      {!geometry && !fallbackMessage ? (
        <div className={styles.fallback} role="status">
          <strong>Loading aircraft</strong>
          <span>The aircraft preview will appear here.</span>
        </div>
      ) : null}
      {fallbackMessage ? (
        <div className={styles.fallback} role="status" title={fallbackMessage}>
          <strong>Preview unavailable</strong>
          <span>{fallbackMessage}</span>
        </div>
      ) : null}
    </div>
  );
}
