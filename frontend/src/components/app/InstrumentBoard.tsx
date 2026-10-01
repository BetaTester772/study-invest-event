import { Link } from 'react-router-dom';
import type { Instrument } from '../../api';
import { Money, PriceChange, Skeleton } from '../ui';
import { KindBadge } from './badges';
import styles from './InstrumentBoard.module.css';

const DEFAULT_NOTES: Record<string, string> = {
  BYUNG: '매일 확률로 크게 오르거나 내려요.',
};

function Row({ ins, note }: { ins: Instrument; note?: string }) {
  return (
    <li>
      <Link to={`/instruments/${ins.code}`} className={styles.row}>
        <span className={styles.name}>
          <span className={styles.title}>{ins.name}</span>
          <span className={styles.alias}>{ins.alias}</span>
        </span>
        <span className={styles.kind}>
          <KindBadge kind={ins.kind} />
          {note && <span className={styles.note}>{note}</span>}
        </span>
        <span className={styles.price}>
          <Money value={ins.price} display="md" />
        </span>
        <span className={styles.change}>
          <PriceChange rate={ins.change_rate} pill />
        </span>
      </Link>
    </li>
  );
}

/**
 * The quote board: stocks as one list, the coin set apart below.
 * Each whole row is a link to the instrument page. `notes` maps code → short note.
 */
export function InstrumentBoard({
  instruments,
  loading,
  notes = DEFAULT_NOTES,
}: {
  instruments?: Instrument[];
  loading?: boolean;
  notes?: Record<string, string>;
}) {
  if (loading && !instruments) {
    return (
      <div className={styles.board} aria-busy="true">
        <ul className={styles.list}>
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className={styles.skeletonRow}>
              <Skeleton width="40%" height="1.5rem" />
              <Skeleton width="6rem" height="1.5rem" />
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const list = instruments ?? [];
  const stocks = list.filter((i) => i.kind === 'stock');
  const coins = list.filter((i) => i.kind === 'coin');
  return (
    <div className={styles.board}>
      <div className={styles.head} aria-hidden="true">
        <span>종목</span>
        <span className={styles.headKind}>구분</span>
        <span className={styles.headRight}>오늘 시작가</span>
        <span className={styles.headRight}>전일 대비</span>
      </div>
      <ul className={styles.list} aria-label="주식">
        {stocks.map((ins) => (
          <Row key={ins.code} ins={ins} note={notes[ins.code]} />
        ))}
      </ul>
      {coins.length > 0 && (
        <ul className={`${styles.list} ${styles.coins}`} aria-label="코인">
          {coins.map((ins) => (
            <Row key={ins.code} ins={ins} note={notes[ins.code]} />
          ))}
        </ul>
      )}
    </div>
  );
}
