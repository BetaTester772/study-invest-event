import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { cx } from '../../../lib/cx';
import { direction, formatNumber } from '../../../lib/format';
import styles from './LineChart.module.css';

export interface ChartPoint {
  x: string;
  y: number;
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
  className?: string;
}

const PAD = { top: 16, right: 16, bottom: 28, left: 64 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.05, 1);
    min -= pad;
    max += pad;
  }
  const span = max - min;
  const rough = span / count;
  const mag = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

function compactWon(y: number): string {
  if (Math.abs(y) >= 10000) {
    const man = y / 10000;
    return `${formatNumber(man, Number.isInteger(man) ? 0 : 1)}만`;
  }
  return formatNumber(y);
}

/** Responsive single-series SVG line chart on a graph-paper plot area. */
export function LineChart({
  points,
  label,
  height = 240,
  formatY = (y) => `${formatNumber(y)}원`,
  formatX = (x) => x,
  tone,
  interactive = true,
  className,
}: LineChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  const titleId = useId();

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(240, Math.floor(el.getBoundingClientRect().width) || 640));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const first = points[0];
  const last = points[points.length - 1];
  const dir = tone ?? (first && last && points.length > 1 ? direction(last.y - first.y) : 'flat');

  const geo = useMemo(() => {
    const ys = points.map((p) => p.y);
    const ticks = niceTicks(Math.min(...ys, Infinity), Math.max(...ys, -Infinity));
    const yMin = ticks[0] ?? 0;
    const yMax = ticks[ticks.length - 1] ?? yMin;
    const plotW = width - PAD.left - PAD.right;
    const plotH = height - PAD.top - PAD.bottom;
    const xAt = (i: number) => PAD.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
    const yAt = (v: number) => PAD.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;
    const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(p.y).toFixed(1)}`).join(' ');
    // Graph-paper minor grid: ~24px cells.
    const cols = Math.max(1, Math.round(plotW / 24));
    const rows = Math.max(1, Math.round(plotH / 24));
    return { ticks, plotW, plotH, xAt, yAt, path, cols, rows };
  }, [points, width, height]);

  if (!first || !last) {
    return (
      <div ref={wrapRef} className={cx(styles.wrap, styles.empty, className)} style={{ height }}>
        아직 가격 이력이 없어요.
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
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    const t = points.length <= 1 ? 0 : Math.round(((x - PAD.left) / geo.plotW) * (points.length - 1));
    setActive(Math.min(points.length - 1, Math.max(0, t)));
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

  const summary = `${label}: ${formatX(first.x)} ${formatY(first.y)}에서 ${formatX(last.x)} ${formatY(last.y)}`;
  const a = active != null ? points[active] : null;

  return (
    <div ref={wrapRef} className={cx(styles.wrap, styles[dir], className)}>
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
            <circle cx={geo.xAt(active)} cy={geo.yAt(a.y)} r={5} className={styles.dot} />
          </g>
        )}
      </svg>
      {a && active != null && (
        <div
          className={styles.tooltip}
          role="status"
          style={{
            left: Math.min(Math.max(geo.xAt(active), 70), width - 70),
            top: Math.max(geo.yAt(a.y) - 12, 0),
          }}
        >
          <span className={styles.tooltipX}>{formatX(a.x)}</span>
          <span className={styles.tooltipY}>{formatY(a.y)}</span>
        </div>
      )}
    </div>
  );
}
