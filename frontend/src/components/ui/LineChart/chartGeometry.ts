import { useEffect, useState, type RefObject } from 'react';
import { formatNumber } from '../../../lib/format';

/** Shared plot padding so a price chart and the indicator panels under it line up on the same x. */
export const CHART_PAD = { top: 16, right: 16, bottom: 28, left: 64 };

/** Round-number y ticks covering [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
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

/** Axis label for won amounts: 75,000 → `7.5만`. */
export function compactWon(y: number): string {
  if (Math.abs(y) >= 10000) {
    const man = y / 10000;
    return `${formatNumber(man, Number.isInteger(man) ? 0 : 1)}만`;
  }
  return formatNumber(y);
}

/** Observe an element's width (falls back to `fallback` where ResizeObserver is missing, e.g. jsdom). */
export function useMeasuredWidth(ref: RefObject<HTMLElement | null>, fallback = 640): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(240, Math.floor(el.getBoundingClientRect().width) || fallback));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, fallback]);
  return width;
}

/** x position of the i-th of `count` points across a plot of width `plotW` (left padding included). */
export function xPosition(i: number, count: number, plotW: number): number {
  return CHART_PAD.left + (count <= 1 ? plotW / 2 : (i / (count - 1)) * plotW);
}

/** Nearest point index for a pointer at `clientX` over an svg `rect` drawn `width` units wide. */
export function pointerIndex(clientX: number, rect: DOMRect, width: number, count: number): number {
  const plotW = width - CHART_PAD.left - CHART_PAD.right;
  const x = ((clientX - rect.left) / (rect.width || width)) * width;
  const t = count <= 1 ? 0 : Math.round(((x - CHART_PAD.left) / plotW) * (count - 1));
  return Math.min(count - 1, Math.max(0, t));
}

/** Values of every non-null entry across several series, for fitting a y domain. */
export function definedValues(...series: ReadonlyArray<ReadonlyArray<number | null> | undefined>): number[] {
  const out: number[] = [];
  for (const s of series) {
    if (!s) continue;
    for (const v of s) if (v != null && Number.isFinite(v)) out.push(v);
  }
  return out;
}

/** Path through the defined stretches of a series; a null breaks the line instead of drawing to zero. */
export function linePath(
  values: ReadonlyArray<number | null>,
  xAt: (i: number) => number,
  yAt: (v: number) => number,
): string {
  let d = '';
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? 'L' : 'M'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)} `;
    pen = true;
  });
  return d.trim();
}
