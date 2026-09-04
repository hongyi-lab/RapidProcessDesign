"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ParametricAircraftPreview,
  geometryNominalSize,
  modelScaleForMode,
  type GeometryScaleMode,
  type GeometryView,
} from "@/components/rapid-design/geometry";

import styles from "./GeometryValidationPanel.module.css";
import {
  clamp,
  errorFromResponse,
  formatNumber,
  initialConditionValues,
  initialDesignValues,
  toAnalyzePayload,
  type AnalyzeEnvelope,
  type ConditionValues,
  type FamilyManifest,
  type FamilyParameterDefinition,
} from "./rapidDesignModel";

type PresetAnalysis = {
  presetId: string;
  label: string;
  analysis: AnalyzeEnvelope;
};

type SensitivityAnalysis = {
  id: "minimum" | "default" | "maximum";
  label: string;
  value: number;
  analysis: AnalyzeEnvelope;
};

const VIEW_OPTIONS: ReadonlyArray<{ id: GeometryView; label: string }> = [
  { id: "3d", label: "3D" },
  { id: "top", label: "顶视" },
  { id: "side", label: "侧视" },
  { id: "front", label: "前视" },
];

const SCALE_OPTIONS: ReadonlyArray<{ id: GeometryScaleMode; label: string }> = [
  { id: "auto", label: "自动适配" },
  { id: "world", label: "统一米制" },
  { id: "normalized", label: "同机身长" },
];

async function requestAnalysis(
  apiBaseUrl: string,
  manifest: FamilyManifest,
  presetId: string,
  design: Record<string, number>,
  condition: ConditionValues,
  signal: AbortSignal,
): Promise<AnalyzeEnvelope> {
  const response = await fetch(`${apiBaseUrl}/api/rapid-design/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toAnalyzePayload(
      manifest.family_id,
      presetId,
      design,
      condition,
    )),
    signal,
  });
  if (!response.ok) throw await errorFromResponse(response, "视觉对比分析失败");
  return (await response.json()) as AnalyzeEnvelope;
}

function sharedReference(
  analyses: readonly AnalyzeEnvelope[],
  mode: GeometryScaleMode,
  view: GeometryView,
): number | undefined {
  if (mode === "auto" || analyses.length === 0) return undefined;
  return Math.max(...analyses.map((analysis) => {
    const length = analysis.geometry_metrics.fuselage_length_m;
    const span = analysis.geometry_metrics.span_m;
    const projectedSize = view === "side" && Number.isFinite(length)
      ? length
      : Number.isFinite(length) && Number.isFinite(span)
        ? Math.max(length, span)
        : geometryNominalSize(analysis.geometry_state);
    return projectedSize * modelScaleForMode(analysis.geometry_state, mode);
  }));
}

function parameterDefault(
  definition: FamilyParameterDefinition,
  manifest: FamilyManifest,
  presetId: string,
): number {
  const design = initialDesignValues(manifest, presetId);
  return clamp(
    design[definition.key] ?? definition.default,
    definition.minimum,
    definition.maximum,
  );
}

export function GeometryValidationPanel({
  apiBaseUrl,
  manifest,
  selectedPresetId,
}: {
  apiBaseUrl: string;
  manifest: FamilyManifest;
  selectedPresetId: string | null;
}) {
  const [view, setView] = useState<GeometryView>("3d");
  const [scaleMode, setScaleMode] = useState<GeometryScaleMode>("world");
  const [presetAnalyses, setPresetAnalyses] = useState<PresetAnalysis[]>([]);
  const [presetError, setPresetError] = useState<string | null>(null);
  const [presetLoading, setPresetLoading] = useState(true);
  const initialSensitivityKey = manifest.design_parameters.some(
    (definition) => definition.key === "wing_sweep_deg",
  ) ? "wing_sweep_deg" : manifest.design_parameters[0]?.key ?? "";
  const [sensitivityKey, setSensitivityKey] = useState(initialSensitivityKey);
  const [sensitivityAnalyses, setSensitivityAnalyses] = useState<SensitivityAnalysis[]>([]);
  const [sensitivityError, setSensitivityError] = useState<string | null>(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(true);
  const geometryCondition = useMemo(() => initialConditionValues(manifest), [manifest]);
  const presetId = selectedPresetId ?? manifest.default_preset_id ?? manifest.presets[0]?.preset_id;
  const sensitivityDefinition = manifest.design_parameters.find(
    (definition) => definition.key === sensitivityKey,
  ) ?? manifest.design_parameters[0];

  useEffect(() => {
    const controller = new AbortController();
    setPresetLoading(true);
    setPresetError(null);
    setPresetAnalyses([]);
    Promise.all(manifest.presets.map(async (preset) => ({
      presetId: preset.preset_id,
      label: preset.label,
      analysis: await requestAnalysis(
        apiBaseUrl,
        manifest,
        preset.preset_id,
        initialDesignValues(manifest, preset.preset_id),
        geometryCondition,
        controller.signal,
      ),
    })))
      .then((analyses) => {
        setPresetAnalyses(analyses);
        setPresetLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setPresetLoading(false);
        setPresetError(reason instanceof Error ? reason.message : "视觉对比分析失败");
      });
    return () => controller.abort();
  }, [apiBaseUrl, geometryCondition, manifest]);

  useEffect(() => {
    if (!presetId || !sensitivityDefinition) return;
    const controller = new AbortController();
    const baseDesign = initialDesignValues(manifest, presetId);
    const defaultValue = parameterDefault(sensitivityDefinition, manifest, presetId);
    const cases = [
      { id: "minimum" as const, label: "Minimum", value: sensitivityDefinition.minimum },
      { id: "default" as const, label: "Default", value: defaultValue },
      { id: "maximum" as const, label: "Maximum", value: sensitivityDefinition.maximum },
    ];
    setSensitivityLoading(true);
    setSensitivityError(null);
    setSensitivityAnalyses([]);
    Promise.all(cases.map(async (entry) => ({
      ...entry,
      analysis: await requestAnalysis(
        apiBaseUrl,
        manifest,
        presetId,
        { ...baseDesign, [sensitivityDefinition.key]: entry.value },
        geometryCondition,
        controller.signal,
      ),
    })))
      .then((analyses) => {
        setSensitivityAnalyses(analyses);
        setSensitivityLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setSensitivityLoading(false);
        setSensitivityError(reason instanceof Error ? reason.message : "参数敏感性分析失败");
      });
    return () => controller.abort();
  }, [apiBaseUrl, geometryCondition, manifest, presetId, sensitivityDefinition]);

  const presetReference = useMemo(
    () => sharedReference(presetAnalyses.map((entry) => entry.analysis), scaleMode, view),
    [presetAnalyses, scaleMode, view],
  );
  const sensitivityReference = useMemo(
    () => sharedReference(sensitivityAnalyses.map((entry) => entry.analysis), "world", view),
    [sensitivityAnalyses, view],
  );

  return (
    <section
      id="round5-comparison-panel"
      className={styles.panel}
      aria-labelledby="round5-comparison-title"
      data-view={view}
      data-scale-mode={scaleMode}
    >
      <header className={styles.header}>
        <div>
          <span>ROUND 5 · VISUAL VALIDATION</span>
          <h2 id="round5-comparison-title">三类构型联动比较</h2>
          <p>三个画布共享视角；统一米制模式锁定相同画幅，机长归一模式只比较轮廓。</p>
        </div>
        <div className={styles.toolbarStack}>
          <div className={styles.toolbar} role="toolbar" aria-label="对比视角">
            {VIEW_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={view === option.id}
                onClick={() => setView(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className={styles.toolbar} role="toolbar" aria-label="对比尺度">
            {SCALE_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={scaleMode === option.id}
                onClick={() => setScaleMode(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {presetError ? <p className={styles.error} role="alert">{presetError}</p> : null}
      <div className={styles.previewGrid} aria-busy={presetLoading}>
        {(presetAnalyses.length > 0 ? presetAnalyses : manifest.presets).map((entry) => {
          const analysis = "analysis" in entry ? entry.analysis : null;
          const label = entry.label;
          return (
            <article className={styles.previewCard} key={"presetId" in entry ? entry.presetId : entry.preset_id}>
              <div className={styles.cardHeading}>
                <strong>{label}</strong>
                <span>
                  {analysis
                    ? `${formatNumber(analysis.geometry_metrics.fuselage_length_m, 1)} m L · ${formatNumber(analysis.geometry_metrics.span_m, 1)} m b`
                    : "正在生成…"}
                </span>
              </div>
              <ParametricAircraftPreview
                geometry={analysis?.geometry_state ?? null}
                view={view}
                scaleMode={scaleMode}
                sharedReferenceSize={presetReference}
                showViewControls={false}
                showScaleControls={false}
                interactive={false}
                className={styles.miniPreview}
              />
            </article>
          );
        })}
      </div>

      <section
        id="round5-sensitivity-panel"
        className={styles.sensitivity}
        aria-labelledby="round5-sensitivity-title"
      >
        <div className={styles.sensitivityHeading}>
          <div>
            <span>PARAMETER SENSITIVITY · MIN / DEFAULT / MAX</span>
            <h3 id="round5-sensitivity-title">几何参数敏感性</h3>
          </div>
          <label>
            <span>选择参数</span>
            <select
              aria-label="参数敏感性选择"
              value={sensitivityDefinition?.key ?? ""}
              onChange={(event) => setSensitivityKey(event.target.value)}
            >
              {manifest.design_parameters.map((definition) => (
                <option key={definition.key} value={definition.key}>
                  {definition.label} · {definition.key}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className={styles.sensitivityNote}>
          当前显示 {sensitivityDefinition?.label ?? "—"}；三幅图固定为同一米制画幅，所有 manifest 几何参数均可逐项检查。
        </p>
        {sensitivityError ? <p className={styles.error} role="alert">{sensitivityError}</p> : null}
        <div className={styles.previewGrid} aria-busy={sensitivityLoading}>
          {(sensitivityAnalyses.length > 0 ? sensitivityAnalyses : [
            { id: "minimum" as const, label: "Minimum", value: sensitivityDefinition?.minimum ?? 0 },
            { id: "default" as const, label: "Default", value: sensitivityDefinition?.default ?? 0 },
            { id: "maximum" as const, label: "Maximum", value: sensitivityDefinition?.maximum ?? 0 },
          ]).map((entry) => {
            const analysis = "analysis" in entry ? entry.analysis : null;
            return (
              <article className={styles.previewCard} key={entry.id}>
                <div className={styles.cardHeading}>
                  <strong>{entry.label}</strong>
                  <span>
                    {formatNumber(entry.value, 3)} {sensitivityDefinition?.unit || ""}
                  </span>
                </div>
                <ParametricAircraftPreview
                  geometry={analysis?.geometry_state ?? null}
                  view={view}
                  scaleMode="world"
                  sharedReferenceSize={sensitivityReference}
                  showViewControls={false}
                  showScaleControls={false}
                  interactive={false}
                  className={styles.miniPreview}
                />
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}
