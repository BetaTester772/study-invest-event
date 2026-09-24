import { describe, expect, it } from 'vitest';
import {
  direction,
  formatBytes,
  formatChange,
  formatDay,
  formatDayShort,
  formatNumber,
  formatPercent,
  formatQuantity,
  formatWon,
  withObjectParticle,
} from '../format';

describe('formatWon', () => {
  it('formats integer won with thousands separators', () => {
    expect(formatWon(1234500)).toBe('1,234,500원');
    expect(formatWon(0)).toBe('0원');
  });

  it('shows sign only when asked, minus always', () => {
    expect(formatWon(5000, { sign: true })).toBe('+5,000원');
    expect(formatWon(-5000)).toBe('-5,000원');
    expect(formatWon(-5000, { sign: true })).toBe('-5,000원');
    expect(formatWon(0, { sign: true })).toBe('0원');
  });

  it('rounds non-integers', () => {
    expect(formatWon(999.6)).toBe('1,000원');
  });
});

describe('formatPercent', () => {
  it('converts a decimal rate to percent with 2 digits', () => {
    expect(formatPercent(0.12)).toBe('12.00%');
    expect(formatPercent(-0.3)).toBe('-30.00%');
    expect(formatPercent(0.12345, { digits: 1 })).toBe('12.3%');
  });

  it('adds + with sign option', () => {
    expect(formatPercent(0.05, { sign: true })).toBe('+5.00%');
    expect(formatPercent(0, { sign: true })).toBe('0.00%');
  });
});

describe('formatChange', () => {
  it('uses Korean market arrows', () => {
    expect(formatChange(0.12)).toBe('▲ 12.00%');
    expect(formatChange(-0.035)).toBe('▼ 3.50%');
    expect(formatChange(0)).toBe('0.00%');
    expect(formatChange(null)).toBe('—');
  });

  it('treats values that round to zero as flat', () => {
    expect(formatChange(0.00001)).toBe('0.00%');
  });
});

describe('direction', () => {
  it('classifies sign', () => {
    expect(direction(1)).toBe('up');
    expect(direction(-1)).toBe('down');
    expect(direction(0)).toBe('flat');
    expect(direction(null)).toBe('flat');
  });
});

describe('misc formatters', () => {
  it('formats numbers, quantities, days and bytes', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
    expect(formatNumber(0.5, 2)).toBe('0.50');
    expect(formatQuantity(3)).toBe('3주');
    expect(formatQuantity(2, 'coin')).toBe('2개');
    expect(formatDay('2026-10-06')).toBe('10월 6일 (화)');
    expect(formatDay('2026-10-16', { weekday: false })).toBe('10월 16일');
    expect(formatDay(null)).toBe('—');
    expect(formatDayShort('2026-10-06')).toBe('10.06');
    expect(formatBytes(10 * 1024 * 1024)).toBe('10.0MB');
  });
});

describe('withObjectParticle', () => {
  it('chooses 을/를 by final consonant', () => {
    expect(withObjectParticle('시세')).toBe('시세를');
    expect(withObjectParticle('가격 이력')).toBe('가격 이력을');
    expect(withObjectParticle('ABC')).toBe('ABC를');
  });
});
