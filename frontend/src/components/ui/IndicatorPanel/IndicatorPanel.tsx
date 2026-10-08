import { useId, useMemo, useRef, type CSSProperties, type PointerEvent } from 'react';
import { cx } from '../../../lib/cx';
import {
  CHART_PAD,
  definedValues,
  linePath,
  niceTicks,
  pointerIndex,
  useMeasuredWidth,
  xPosition,
} from '../LineChart/chartGeometry';
import styles from './IndicatorPanel.module.css';

export interface PanelLine {
  id: string;
  label: string;
  values: Array<number | null>;
  /** Any CSS color; use a `var(--chart-N)` token or `var(--color-ink)`. */
  color: string;
  dashed?: boolean;
}

export interface PanelBars {
  id: string;
  label: string;
  /** Bars rise from zero; positive values wear the market "up" color, negative the "down" color. */
  values: Array<number | null>;
}

export interface PanelGuide {
  value: number;
  /** Tick text for the guide, e.g. "70". */
  label?: string;
}

export interface IndicatorPanelProps {
  title: string;
  /** One muted line explaining how to read it. */
  description?: string;
  /** x categories, one per point — the same list the price chart uses so columns line up. */
  x: string[];
  lines?: PanelLine[];
  bars?: PanelBars;
  /** Horizontal reference lines (e.g. RSI 30 / 70). */
  guides?: PanelGuide[];
  /** Shaded value ranges (e.g. RSI above 70). */
  zones?: Array<{ from: number; to: number }>;
  /** Fixed y domain; otherwise fitted to the data (and to 0 when `zero` is set). */
  domain?: readonly [number, number];
  /** Draw and include the zero baseline. */
  zero?: boolean;
  height?: number;
  formatValue: (v: number) => string;
  formatTick?: (v: number) => string;
  formatX?: (x: string) => string;
  /** Shown instead of the plot until at least one value exists, e.g. "6일째부터 표시됩니다". */
  emptyNote?: string;
  /** Print first/middle/last x labels under this panel (use on the bottom one). */
  showXAxis?: boolean;
  activeIndex?: number | null;
  onActiveChange?: (index: number | null) => void;
  className?: string;
}

const PLOT_H = 88;

/** Mark with a flat baseline and a 4px rounded data end. */
function barPath(x: number, w: number, yBase: number, yTip: number): string {
  const r = Math.min(4, w / 2, Math.abs(yTip - yBase));
  const x0 = x - w / 2;
  const x1 = x + w / 2;
  if (Math.abs(yTip - yBase) < 0.5) return `M${x0},${yBase} H${x1}`;
  if (yTip < yBase) {
    return `M${x0},${yBase} V${yTip + r} Q${x0},${yTip} ${x0 + r},${yTip} H${x1 - r} Q${x1},${yTip} ${x1},${yTip + r} V${yBase} Z`;
  }
  return `M${x0},${yBase} V${yTip - r} Q${x0},${yTip} ${x0 + r},${yTip} H${x1 - r} Q${x1},${yTip} ${x1},${yTip - r} V${yBase} Z`;
}

/**
 * A short indicator plot that sits under the price chart on the same x positions (RSI, MACD,
 * daily change). Hover/pointer position is shared through `activeIndex`, and the header doubles as
 * the legend: each series has a line key, its name and its value at the hovered (else latest) day.
 */
export function IndicatorPanel({
  title,
  description,
  x,
  lines = [],
  bars,
  guides = [],
  zones = [],
  domain,
  zero,
  height,
  formatValue,
  formatTick,
  formatX = (v) => v,
  emptyNote,
  showXAxis,
  activeIndex,
  onActiveChange,
  className,
}: IndicatorPanelProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const width = useMeasuredWidth(wrapRef);
  const titleId = useId();
  const count = x.length;
  const pad = { ...CHART_PAD, top: 8, bottom: showXAxis ? 24 : 6 };
  const svgHeight = height ?? pad.top + PLOT_H + pad.bottom;
  const plotH = svgHeight - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;

  const geo = useMemo(() => {
    const values = definedValues(...lines.map((l) => l.values), bars?.values);
    // The zero baseline widens the domain but is not data: a panel with only zero has nothing to show.
    const fitted = zero ? [...values, 0] : values;
    const ticks = domain
      ? [domain[0], domain[1]]
      : niceTicks(Math.min(...fitted, Infinity), Math.max(...fitted, -Infinity), 2);
    const yMin = domain ? domain[0] : (ticks[0] ?? 0);
    const yMax = domain ? domain[1] : (ticks[ticks.length - 1] ?? yMin);
    const xAt = (i: number) => xPosition(i, count, plotW);
    const yAt = (v: number) =>
      pad.top + plotH - ((Math.min(yMax, Math.max(yMin, v)) - yMin) / (yMax - yMin || 1)) * plotH;
    const paths = lines.map((l) => linePath(l.values, xAt, yAt));
    const spacing = count > 1 ? plotW / (count - 1) : plotW;
    const barW = Math.max(2, Math.min(24, spacing * 0.6));
    return { values, ticks, yMin, yMax, xAt, yAt, paths, barW };
  }, [lines, bars, domain, zero, count, plotW, plotH, pad.top]);

  const hasData = geo.values.length > 0;
  const at = activeIndex != null && activeIndex < count ? activeIndex : count - 1;
  const lastIndex = (vals: Array<number | null>) => vals.findLastIndex((v) => v != null);
  const readout = (vals: Array<number | null>): number | null => {
    const v = vals[at];
    if (activeIndex != null) return v ?? null;
    const i = lastIndex(vals);
    return i < 0 ? null : (vals[i] ?? null);
  };

  const onPointer = (e: PointerEvent<SVGSVGElement>) => {
    onActiveChange?.(pointerIndex(e.clientX, e.currentTarget.getBoundingClientRect(), width, count));
  };

  const xLabelIdx = Array.from(
    new Set(count <= 1 ? [0] : width < 420 ? [0, count - 1] : [0, Math.floor((count - 1) / 2), count - 1]),
  );
  const summaryParts = [
    ...lines.map((l) => {
      const v = readout(l.values);
      return v == null ? null : `${l.label} ${formatValue(v)}`;
    }),
    bars
      ? readout(bars.values) == null
        ? null
        : `${bars.label} ${formatValue(readout(bars.values) as number)}`
      : null,
  ].filter(Boolean);
  const summary = `${title}${summaryParts.length ? `: ${summaryParts.join(', ')}` : ''}`;
  const tick = formatTick ?? formatValue;
  const zeroY = zero && geo.yMin <= 0 && geo.yMax >= 0 ? geo.yAt(0) : null;

  return (
    <section ref={wrapRef} className={cx(styles.panel, className)} aria-labelledby={titleId}>
      <header className={styles.head}>
        <h4 id={titleId} className={styles.title}>
          {title}
        </h4>
        <ul className={styles.legend}>
          {lines.map((l) => {
            const v = readout(l.values);
            return (
              <li key={l.id} className={styles.legendItem}>
                <span
                  className={cx(styles.key, l.dashed && styles.keyDashed)}
                  style={{ '--key-color': l.color } as CSSProperties}
                  aria-hidden="true"
                />
                <span className={styles.legendName}>{l.label}</span>
                <span className={cx(styles.legendValue, v == null && styles.legendEmpty)}>
                  {v == null ? '—' : formatValue(v)}
                </span>
              </li>
            );
          })}
          {bars && (
            <li className={styles.legendItem}>
              <span className={cx(styles.key, styles.keyBars)} aria-hidden="true" />
              <span className={styles.legendName}>{bars.label}</span>
              <span className={cx(styles.legendValue, readout(bars.values) == null && styles.legendEmpty)}>
                {readout(bars.values) == null ? '—' : formatValue(readout(bars.values) as number)}
              </span>
            </li>
          )}
        </ul>
        {description && <p className={styles.description}>{description}</p>}
      </header>
      {!hasData ? (
        <div className={styles.empty} style={{ height: plotH }}>
          {emptyNote ?? '아직 값을 계산할 데이터가 모자랍니다.'}
        </div>
      ) : (
        <svg
          width={width}
          height={svgHeight}
          viewBox={`0 0 ${width} ${svgHeight}`}
          role="img"
          aria-label={summary}
          className={styles.svg}
          onPointerMove={onPointer}
          onPointerDown={onPointer}
          onPointerLeave={() => onActiveChange?.(null)}
        >
          {zones.map((z, i) => {
            const y0 = geo.yAt(Math.max(z.from, z.to));
            const y1 = geo.yAt(Math.min(z.from, z.to));
            return (
              <rect key={i} className={styles.zone} x={pad.left} y={y0} width={plotW} height={Math.max(0, y1 - y0)} />
            );
          })}
          <g className={styles.axis}>
            {geo.ticks.map((t) => (
              <g key={t}>
                <line className={styles.grid} x1={pad.left} x2={pad.left + plotW} y1={geo.yAt(t)} y2={geo.yAt(t)} />
                <text x={pad.left - 8} y={geo.yAt(t)} dy="0.32em" textAnchor="end">
                  {tick(t)}
                </text>
              </g>
            ))}
            {guides.map((g) => (
              <g key={g.value}>
                <line
                  className={styles.guide}
                  x1={pad.left}
                  x2={pad.left + plotW}
                  y1={geo.yAt(g.value)}
                  y2={geo.yAt(g.value)}
                />
                {g.label != null && (
                  <text x={pad.left - 8} y={geo.yAt(g.value)} dy="0.32em" textAnchor="end">
                    {g.label}
                  </text>
                )}
              </g>
            ))}
            {showXAxis &&
              xLabelIdx.map((i) => (
                <text
                  key={i}
                  x={geo.xAt(i)}
                  y={svgHeight - 6}
                  textAnchor={count <= 1 ? 'middle' : i === 0 ? 'start' : i === count - 1 ? 'end' : 'middle'}
                >
                  {formatX(x[i] ?? '')}
                </text>
              ))}
          </g>
          {zeroY != null && <line className={styles.zero} x1={pad.left} x2={pad.left + plotW} y1={zeroY} y2={zeroY} />}
          {bars?.values.map((v, i) => {
            if (v == null) return null;
            const base = geo.yAt(0 >= geo.yMin && 0 <= geo.yMax ? 0 : geo.yMin);
            return (
              <path
                key={i}
                d={barPath(geo.xAt(i), geo.barW, base, geo.yAt(v))}
                className={cx(
                  styles.bar,
                  v >= 0 ? styles.barUp : styles.barDown,
                  activeIndex === i && styles.barActive,
                )}
              />
            );
          })}
          {lines.map((l, i) => (
            <path
              key={l.id}
              d={geo.paths[i]}
              className={cx(styles.line, l.dashed && styles.lineDashed)}
              style={{ stroke: l.color }}
            />
          ))}
          {activeIndex != null && activeIndex < count && (
            <g>
              <line
                className={styles.crosshair}
                x1={geo.xAt(activeIndex)}
                x2={geo.xAt(activeIndex)}
                y1={pad.top}
                y2={pad.top + plotH}
              />
              {lines.map((l) => {
                const v = l.values[activeIndex];
                return v == null ? null : (
                  <circle
                    key={l.id}
                    cx={geo.xAt(activeIndex)}
                    cy={geo.yAt(v)}
                    r={4}
                    className={styles.dot}
                    style={{ fill: l.color }}
                  />
                );
              })}
            </g>
          )}
        </svg>
      )}
    </section>
  );
}
