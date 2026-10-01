import { describe, expect, it } from 'vitest';
import type { RankingEntry } from '../../api/types';
import { sortRanking } from '../ranking';

function entry(nickname: string, rank: number, return_rank: number): RankingEntry {
  return {
    rank,
    nickname,
    total_assets: 0,
    principal: 1_000_000,
    profit: 0,
    return_rate: 0,
    return_rank,
    certified_days: 0,
    streak: 0,
  };
}

// Server order: by total-assets rank. alice has the most assets (rewards) but the
// return ranking differs.
const entries = [entry('alice', 1, 2), entry('carol', 2, 1), entry('bob', 3, 3), entry('dan', 3, 2)];

describe('sortRanking', () => {
  it('keeps the server order for total assets', () => {
    expect(sortRanking(entries, 'total')).toBe(entries);
  });

  it('orders by return rank, ties by total-assets rank, without mutating', () => {
    expect(sortRanking(entries, 'return').map((e) => e.nickname)).toEqual(['carol', 'alice', 'dan', 'bob']);
    expect(entries.map((e) => e.nickname)).toEqual(['alice', 'carol', 'bob', 'dan']);
  });
});
