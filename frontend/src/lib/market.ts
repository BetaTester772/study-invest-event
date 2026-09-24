import type { EventInfo } from '../api/types';
import { formatDay } from './format';

export type MarketPhase = 'before_event' | 'after_event' | 'holiday' | 'pre_open' | 'open' | 'settling' | 'settled';

export interface MarketSummary {
  phase: MarketPhase;
  /** Short headline sentence. */
  headline: string;
  /** One or two plain sentences explaining what happens next. */
  detail: string;
  /** Can orders be placed right now (server's view). */
  canTrade: boolean;
  /** 1-based index of today among operating days, or null. */
  dayNumber: number | null;
}

/** Turn the server's EventInfo into plain-language market status copy. */
export function describeMarket(event: EventInfo): MarketSummary {
  const { market, today, operating_days: days } = event;
  const idx = days.indexOf(today);
  const dayNumber = idx >= 0 ? idx + 1 : null;
  const isLastDay = idx === days.length - 1;
  const roundText = market.round
    ? `오늘은 ${market.round}회차 정산일이에요.`
    : isLastDay
      ? '오늘이 마지막 운영일이라 마감 뒤에는 가격이 바뀌지 않아요.'
      : '';

  if (today < event.start) {
    return {
      phase: 'before_event',
      headline: '이벤트 시작 전이에요',
      detail: `${formatDay(event.start)} ${market.opens_at}에 첫 장이 열려요.`,
      canTrade: false,
      dayNumber: null,
    };
  }
  if (today > event.end) {
    return {
      phase: 'after_event',
      headline: '이벤트가 끝났어요',
      detail: '최종 순위를 랭킹에서 확인해 보세요.',
      canTrade: false,
      dayNumber: null,
    };
  }
  if (!event.is_operating_day) {
    return {
      phase: 'holiday',
      headline: '오늘은 장이 쉬어요',
      detail: '다음 운영일 09:00에 다시 열려요.',
      canTrade: false,
      dayNumber,
    };
  }
  if (market.is_open) {
    return {
      phase: 'open',
      headline: '장이 열려 있어요',
      detail: `${market.closes_at}에 마감하고 정산해요. ${roundText}`.trim(),
      canTrade: true,
      dayNumber,
    };
  }
  if (!market.day_opened) {
    return {
      phase: 'pre_open',
      headline: '곧 장이 열려요',
      detail: `${market.opens_at}에 오늘 시작가를 공시하고 주문을 받아요. ${roundText}`.trim(),
      canTrade: false,
      dayNumber,
    };
  }
  if (market.day_settled) {
    return {
      phase: 'settled',
      headline: '오늘 장이 마감됐어요',
      detail: isLastDay
        ? '마지막 정산까지 끝났어요. 최종 순위를 확인해 보세요.'
        : `정산이 끝났어요. 내일 ${market.opens_at}에 새 시작가로 열려요.`,
      canTrade: false,
      dayNumber,
    };
  }
  return {
    phase: 'settling',
    headline: '오늘 장이 마감됐어요',
    detail: isLastDay ? '마지막 날 장이 끝났어요.' : '정산 중이에요. 곧 다음 운영일 시작가가 정해져요.',
    canTrade: false,
    dayNumber,
  };
}
