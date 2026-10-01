import type { RankingEntry } from '../api/types';

/** `total`: total-assets rank. `return`: return-rate rank. */
export type RankingSort = 'total' | 'return';

/**
 * Entries in the chosen order. The server already sorts by total-assets rank; for the
 * return view, sort by return rank (ties fall back to total-assets rank).
 */
export function sortRanking(entries: RankingEntry[], by: RankingSort): RankingEntry[] {
  if (by === 'total') return entries;
  return [...entries].sort((a, b) => a.return_rank - b.return_rank || a.rank - b.rank);
}
