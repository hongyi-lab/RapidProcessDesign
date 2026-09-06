import type { ConvergencePoint } from "./rapidDesignModel";
import { formatNumber } from "./rapidDesignModel";
import styles from "./rapid-design.module.css";

function formatCompact(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 100000) return value.toExponential(1);
  if (magnitude >= 1000) return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  if (magnitude >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function PolarChart({
  title,
  unit,
  alpha,
  values,
  baselineAlpha,
  baselineValues,
}: {
  title: string;
  unit: string;
  alpha: number[];
  values: number[];
  baselineAlpha?: number[];
  baselineValues?: number[];
}) {
  const width = 480;
  const height = 188;
  const left = 48;
  const right = 14;
  const top = 14;
  const bottom = 34;
  const currentPoints = alpha
    .map((x, index) => ({ x, y: values[index] }))
    .filter((point): point is { x: number; y: number } => Number.isFinite(point.x) && Number.isFinite(point.y));
  const baselinePoints = (baselineAlpha ?? [])
    .map((x, index) => ({ x, y: baselineValues?.[index] }))
    .filter((point): point is { x: number; y: number } => Number.isFinite(point.x) && Number.isFinite(point.y));
  const allPoints = [...currentPoints, ...baselinePoints];

  if (currentPoints.length < 2) {
    return <div className={styles.chartEmpty}>Waiting for aerodynamic data</div>;
  }

  let minimumX = Math.min(...allPoints.map((point) => point.x));
  let maximumX = Math.max(...allPoints.map((point) => point.x));
  let minimumY = Math.min(...allPoints.map((point) => point.y));
  let maximumY = Math.max(...allPoints.map((point) => point.y));
  if (minimumX === maximumX) {
    minimumX -= 1;
    maximumX += 1;
  }
  if (minimumY === maximumY) {
    minimumY -= 1;
    maximumY += 1;
  }
  const yPadding = (maximumY - minimumY) * 0.06;
  minimumY -= yPadding;
  maximumY += yPadding;

  const xPosition = (value: number) =>
    left + ((value - minimumX) / (maximumX - minimumX)) * (width - left - right);
  const yPosition = (value: number) =>
    top + ((maximumY - value) / (maximumY - minimumY)) * (height - top - bottom);
  const points = (series: Array<{ x: number; y: number }>) =>
    series.map((point) => `${xPosition(point.x)},${yPosition(point.y)}`).join(" ");
  const yTicks = [0, 0.5, 1].map((fraction) => minimumY + fraction * (maximumY - minimumY));
  const xTicks = [minimumX, (minimumX + maximumX) / 2, maximumX];

  return (
    <figure className={styles.chartCard}>
      <figcaption>
        <strong>{title}</strong>
        <span>{unit}</span>
      </figcaption>
      <svg
        className={styles.polarChart}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title} by angle of attack`}
      >
        {yTicks.map((tick) => (
          <g key={`y-${tick}`}>
            <line
              x1={left}
              x2={width - right}
              y1={yPosition(tick)}
              y2={yPosition(tick)}
              className={styles.gridLine}
            />
            <text x={left - 7} y={yPosition(tick) + 3} textAnchor="end">
              {formatCompact(tick)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <text key={`x-${tick}`} x={xPosition(tick)} y={height - 10} textAnchor="middle">
            {formatCompact(tick)}°
          </text>
        ))}
        <line
          x1={left}
          x2={left}
          y1={top}
          y2={height - bottom}
          className={styles.axisLine}
        />
        <line
          x1={left}
          x2={width - right}
          y1={height - bottom}
          y2={height - bottom}
          className={styles.axisLine}
        />
        {baselinePoints.length > 1 && (
          <polyline points={points(baselinePoints)} className={styles.baselineLine} />
        )}
        <polyline points={points(currentPoints)} className={styles.currentLine} />
      </svg>
    </figure>
  );
}

export function ConvergenceChart({ points }: { points: ConvergencePoint[] }) {
  if (points.length < 2) {
    return <div className={styles.chartEmpty}>Run the optimizer to view convergence</div>;
  }
  const width = 520;
  const height = 126;
  const padding = 14;
  const values = points.map((point) => point.takeoff_mass_kg);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = Math.max(1, maximum - minimum);
  const polyline = points
    .map((point, index) => {
      const x = padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2);
      const y = padding + ((maximum - point.takeoff_mass_kg) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className={styles.convergenceChart}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Takeoff mass convergence">
        <line
          x1={padding}
          x2={width - padding}
          y1={height - padding}
          y2={height - padding}
          className={styles.axisLine}
        />
        <polyline points={polyline} className={styles.currentLine} />
      </svg>
      <span>{formatNumber(maximum)} kg</span>
      <strong>{formatNumber(values.at(-1))} kg</strong>
    </div>
  );
}
