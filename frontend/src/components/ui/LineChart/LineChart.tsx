import { useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react';
import { cx } from '../../../lib/cx';
import { direction, formatNumber } from '../../../lib/format';
import {
  CHART_PAD as PAD,
  compactWon,
  definedValues,
  linePath,
  niceTicks,
  pointerIndex,
  useMeasuredWidth,
  xPosition,
} from './chartGeometry';
import styles from './LineChart.module.css';

export interface ChartPoint {
  x: string;
  y: number;
}

/** A line drawn over the price line (moving average, …). `values` lines up index-for-index with `points`. */
export interface ChartOverlay {
  id: string;
  label: string;
  values: Array<number | null>;
  /** Any CSS color; use a `var(--chart-N)` token so light/dark stay in tokens.css. */
  color: string;
  /** Legend text while no value exists yet, e.g. "5일째부터". */
  emptyNote?: string;
}

/** A shaded band between two series (Bollinger bands, …). */
export interface ChartBand {
  id: string;
  label: string;
  upper: Array<number | null>;
  lower: Array<number | null>;
  emptyNote?: string;
}

export interface LineChartProps {
  points: ChartPoint[];
  /** Accessible summary, e.g. "삼수전자 가격 이력". */
  label: string;
  height?: number;
  formatY?: (y: number) => string;
  formatX?: (x: string) => string;
  /** Force a color; default is by overall direction (last vs first). */
  tone?: 'up' | 'down' | 'flat';
  /** Show hover crosshair + tooltip (default true). */
  interactive?: boolean;
  /** Extra lines over the price line. With any overlay or band a legend row (with values) appears. */
  overlays?: ChartOverlay[];
  bands?: ChartBand[];
  /** Name of the main line in the legend. */
  seriesLabel?: string;
  /** Controlled hover/keyboard position, so panels under the chart can follow the same x. */
  activeIndex?: number | null;
  onActiveChange?: (index: number | null) => void;
  className?: string;
}

const NO_OVERLAYS: ChartOverlay[] = [];
const NO_BANDS: ChartBand[] = [];

/** Closed polygons for each run of indices where both edges of a band exist. */
function bandPaths(band: ChartBand, xAt: (i: number) => number, yAt: (v: number) => number): string[] {
  const runs: number[][] = [];
  let run: number[] = [];
  band.upper.forEach((u, i) => {
    if (u != null && band.lower[i] != null) run.push(i);
    else if (run.length) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length) runs.push(run);
  return runs
    .filter((r) => r.length > 1)
    .map((r) => {
      const top = r.map((i) => `${xAt(i).toFixed(1)},${yAt(band.upper[i] as number).toFixed(1)}`);
      const bottom = [...r].reverse().map((i) => `${xAt(i).toFixed(1)},${yAt(band.lower[i] as number).toFixed(1)}`);
      return `M${top.join(' L')} L${bottom.join(' L')} Z`;
    });
}

/** Responsive SVG line chart on a graph-paper plot area, with optional indicator overlays. */
export function LineChart({
  points,
  label,
  height = 240,
  formatY = (y) => `${formatNumber(y)}원`,
  formatX = (x) => x,
  tone,
  interactive = true,
  overlays,
  bands,
  seriesLabel = '시작가',
  activeIndex,
  onActiveChange,
  className,
}: LineChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const width = useMeasuredWidth(wrapRef);
  const [innerActive, setInnerActive] = useState<number | null>(null);
  const controlled = activeIndex !== undefined;
  const active = controlled ? activeIndex : innerActive;
  const setActive = (i: number | null) => {
    if (!controlled) setInnerActive(i);
    onActiveChange?.(i);
  };
  const titleId = useId();
  const lines = overlays ?? NO_OVERLAYS;
  const shades = bands ?? NO_BANDS;

  const first = points[0];
  const last = points[points.length - 1];
  const dir = tone ?? (first && last && points.length > 1 ? direction(last.y - first.y) : 'flat');

  const geo = useMemo(() => {
    const ys = definedValues(
      points.map((p) => p.y),
      ...lines.map((o) => o.values),
      ...shades.flatMap((b) => [b.upper, b.lower]),
    );
    const ticks = niceTicks(Math.min(...ys, Infinity), Math.max(...ys, -Infinity));
    const yMin = ticks[0] ?? 0;
    const yMax = ticks[ticks.length - 1] ?? yMin;
    const plotW = width - PAD.left - PAD.right;
    const plotH = height - PAD.top - PAD.bottom;
    const xAt = (i: number) => xPosition(i, points.length, plotW);
    const yAt = (v: number) => PAD.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;
    const path = linePath(
      points.map((p) => p.y),
      xAt,
      yAt,
    );
    const overlayPaths = lines.map((o) => linePath(o.values, xAt, yAt));
    const bandShapes = shades.map((b) => bandPaths(b, xAt, yAt));
    const bandEdges = shades.map((b) => [linePath(b.upper, xAt, yAt), linePath(b.lower, xAt, yAt)] as const);
    // Graph-paper minor grid: ~24px cells.
    const cols = Math.max(1, Math.round(plotW / 24));
    const rows = Math.max(1, Math.round(plotH / 24));
    return { ticks, plotW, plotH, xAt, yAt, path, overlayPaths, bandShapes, bandEdges, cols, rows };
  }, [points, lines, shades, width, height]);

  if (!first || !last) {
    return (
      <div ref={wrapRef} className={cx(styles.wrap, styles.empty, className)} style={{ height }}>
        아직 가격 이력이 없습니다.
      </div>
    );
  }

  const xLabelIdx = Array.from(
    new Set(
      points.length <= 1
        ? [0]
        : width < 420
          ? [0, points.length - 1]
          : [0, Math.floor((points.length - 1) / 2), points.length - 1],
    ),
  );

  const onPointer = (e: PointerEvent<SVGSVGElement>) => {
    if (!interactive) return;
    setActive(pointerIndex(e.clientX, e.currentTarget.getBoundingClientRect(), width, points.length));
  };

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!interactive) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const cur = active ?? points.length - 1;
      setActive(Math.min(points.length - 1, Math.max(0, cur + (e.key === 'ArrowRight' ? 1 : -1))));
    } else if (e.key === 'Escape') {
      setActive(null);
    }
  };

  // Legend/readout position: the hovered point, else the latest one.
  const at = active != null && active < points.length ? active : points.length - 1;
  const lastDefined = (values: Array<number | null>) => values.findLast((v) => v != null) ?? null;
  const summary = [
    `${label}: ${formatX(first.x)} ${formatY(first.y)}에서 ${formatX(last.x)} ${formatY(last.y)}`,
    ...lines.map((o) => {
      const v = lastDefined(o.values);
      return v == null ? null : `${o.label} ${formatY(v)}`;
    }),
  ]
    .filter(Boolean)
    .join(', ');
  const a = active != null ? points[active] : null;
  const showLegend = lines.length > 0 || shades.length > 0;
  // Narrow screens skip the per-series rows: the legend row above the chart already shows the hovered values.
  const compact = width < 420;
  const tipRows = compact ? [] : lines.filter((o) => active != null && o.values[active] != null);
  const tipBands = compact
    ? []
    : shades.filter((b) => active != null && b.upper[active] != null && b.lower[active] != null);
  // A tall tooltip sits beside the crosshair (on the emptier side) instead of covering the lines at that day.
  const sideTip = tipRows.length + tipBands.length > 0;
  const tipRight = active != null && geo.xAt(active) < PAD.left + geo.plotW / 2;

  return (
    <div ref={wrapRef} className={cx(styles.wrap, styles[dir], className)}>
      {showLegend && (
        <ul className={styles.legend} aria-label="차트 범례">
          <li className={styles.legendItem}>
            <span className={cx(styles.key, styles.keyLine, styles.keyPrice)} aria-hidden="true" />
            <span className={styles.legendName}>{seriesLabel}</span>
            <span className={styles.legendValue}>{formatY((points[at] ?? last).y)}</span>
          </li>
          {lines.map((o) => {
            const v = o.values[at];
            return (
              <li key={o.id} className={styles.legendItem}>
                <span
                  className={cx(styles.key, styles.keyLine)}
                  style={{ '--key-color': o.color } as CSSProperties}
                  aria-hidden="true"
                />
                <span className={styles.legendName}>{o.label}</span>
                <span className={cx(styles.legendValue, v == null && styles.legendEmpty)}>
                  {v != null ? formatY(v) : (o.emptyNote ?? '—')}
                </span>
              </li>
            );
          })}
          {shades.map((b) => {
            const u = b.upper[at];
            const l = b.lower[at];
            return (
              <li key={b.id} className={styles.legendItem}>
                <span className={cx(styles.key, styles.keyBand)} aria-hidden="true" />
                <span className={styles.legendName}>{b.label}</span>
                <span className={cx(styles.legendValue, (u == null || l == null) && styles.legendEmpty)}>
                  {u != null && l != null ? `${formatY(l)} ~ ${formatY(u)}` : (b.emptyNote ?? '—')}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <div className={styles.plot}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-labelledby={titleId}
          tabIndex={interactive ? 0 : undefined}
          className={styles.svg}
          onPointerMove={onPointer}
          onPointerDown={onPointer}
          onPointerLeave={() => setActive(null)}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          <title id={titleId}>{summary}</title>
          <g className={styles.minorGrid}>
            {Array.from({ length: geo.cols + 1 }, (_, i) => {
              const x = PAD.left + (i / geo.cols) * geo.plotW;
              return <line key={`c${i}`} x1={x} x2={x} y1={PAD.top} y2={PAD.top + geo.plotH} />;
            })}
            {Array.from({ length: geo.rows + 1 }, (_, i) => {
              const y = PAD.top + (i / geo.rows) * geo.plotH;
              return <line key={`r${i}`} x1={PAD.left} x2={PAD.left + geo.plotW} y1={y} y2={y} />;
            })}
          </g>
          <g className={styles.axis}>
            {geo.ticks.map((t) => (
              <g key={t}>
                <line
                  className={styles.majorGrid}
                  x1={PAD.left}
                  x2={PAD.left + geo.plotW}
                  y1={geo.yAt(t)}
                  y2={geo.yAt(t)}
                />
                <text x={PAD.left - 8} y={geo.yAt(t)} dy="0.32em" textAnchor="end">
                  {compactWon(t)}
                </text>
              </g>
            ))}
            {xLabelIdx.map((i) => {
              const p = points[i];
              if (!p) return null;
              return (
                <text
                  key={i}
                  x={geo.xAt(i)}
                  y={height - 8}
                  textAnchor={
                    points.length <= 1 ? 'middle' : i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'
                  }
                >
                  {formatX(p.x)}
                </text>
              );
            })}
          </g>
          {shades.map((b, bi) => (
            <g key={b.id}>
              {geo.bandShapes[bi]?.map((d, k) => <path key={k} d={d} className={styles.band} />)}
              <path d={geo.bandEdges[bi]?.[0]} className={styles.bandEdge} />
              <path d={geo.bandEdges[bi]?.[1]} className={styles.bandEdge} />
            </g>
          ))}
          {lines.map((o, oi) => (
            <path key={o.id} d={geo.overlayPaths[oi]} className={styles.overlay} style={{ stroke: o.color }} />
          ))}
          {points.length > 1 && <path d={geo.path} className={styles.line} />}
          <circle cx={geo.xAt(points.length - 1)} cy={geo.yAt(last.y)} r={4} className={styles.dot} />
          {a && active != null && (
            <g>
              <line
                className={styles.crosshair}
                x1={geo.xAt(active)}
                x2={geo.xAt(active)}
                y1={PAD.top}
                y2={PAD.top + geo.plotH}
              />
              {lines.map((o) => {
                const v = o.values[active];
                return v == null ? null : (
                  <circle
                    key={o.id}
                    cx={geo.xAt(active)}
                    cy={geo.yAt(v)}
                    r={4}
                    className={styles.overlayDot}
                    style={{ fill: o.color }}
                  />
                );
              })}
              <circle cx={geo.xAt(active)} cy={geo.yAt(a.y)} r={5} className={styles.dot} />
            </g>
          )}
        </svg>
        {a && active != null && (
          <div
            className={cx(styles.tooltip, sideTip && (tipRight ? styles.tooltipRight : styles.tooltipLeft))}
            role="status"
            style={
              sideTip
                ? { left: geo.xAt(active) + (tipRight ? 14 : -14), top: PAD.top + 4 }
                : { left: Math.min(Math.max(geo.xAt(active), 70), width - 70), top: Math.max(geo.yAt(a.y) - 12, 0) }
            }
          >
            <span className={styles.tooltipX}>{formatX(a.x)}</span>
            <span className={styles.tooltipY}>{formatY(a.y)}</span>
            {tipRows.map((o) => (
              <span key={o.id} className={styles.tooltipRow}>
                <span
                  className={cx(styles.key, styles.keyLine)}
                  style={{ '--key-color': o.color } as CSSProperties}
                  aria-hidden="true"
                />
                <span className={styles.tooltipValue}>{formatY(o.values[active] as number)}</span>
                <span className={styles.tooltipName}>{o.label}</span>
              </span>
            ))}
            {tipBands.map((b) => (
              <span key={b.id} className={styles.tooltipRow}>
                <span className={cx(styles.key, styles.keyBand)} aria-hidden="true" />
                <span className={styles.tooltipValue}>
                  {formatY(b.lower[active] as number)} ~ {formatY(b.upper[active] as number)}
                </span>
                <span className={styles.tooltipName}>{b.label}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
