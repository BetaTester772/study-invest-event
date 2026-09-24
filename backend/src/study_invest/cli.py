"""운영 CLI: 배치(cron)·시뮬레이터·개인정보 삭제.

study-invest run-due                  # 현재 시각에 밀린 09:00/18:00 배치 실행(cron 1분 간격 권장)
study-invest open --day 2026-10-06
study-invest settle --day 2026-10-06
study-invest simulate --paths 100000 --seed 42 [--use-price-cap]
study-invest purge-images [--force]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Sequence
from datetime import date, datetime

from .config import Settings
from .db import make_engine, make_session_factory
from .event_calendar import EventCalendar, to_kst
from .params import KST
from .services import certification, market
from .services.common import DomainError, get_params
from .simulator import format_report
from .simulator import run as run_simulation


def _print(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="study-invest", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-due", help="시각이 된 배치를 실행")
    for name in ("open", "settle"):
        p = sub.add_parser(name, help=f"{name} 배치 실행")
        p.add_argument("--day", type=date.fromisoformat, default=None)
    sim = sub.add_parser("simulate", help="F-13 코인 경로 시뮬레이션")
    sim.add_argument("--paths", type=int, default=10_000)
    sim.add_argument("--rounds", type=int, default=10)
    sim.add_argument("--seed", type=int, default=None)
    sim.add_argument("--use-price-cap", action="store_true")
    sim.add_argument("--defaults", action="store_true", help="DB 대신 기본 파라미터 사용")
    purge = sub.add_parser("purge-images", help="이벤트 종료 후 인증 사진 삭제")
    purge.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    now = datetime.now(KST)
    calendar = EventCalendar()
    rng = random.SystemRandom()

    if args.command == "simulate" and args.defaults:
        print(
            format_report(
                run_simulation(args.paths, args.rounds, args.seed, args.use_price_cap, None)
            )
        )
        return 0

    factory = make_session_factory(make_engine(settings.batch_pool))  # 배치 전용 풀
    if args.command == "run-due":
        results = market.run_due(factory, now, calendar, rng)
        _print([r.__dict__ if isinstance(r, market.BatchResult) else r for r in results])
        return 1 if any(isinstance(r, dict) and "error" in r for r in results) else 0

    with factory() as s:
        try:
            if args.command == "simulate":
                report = run_simulation(
                    args.paths, args.rounds, args.seed, args.use_price_cap, get_params(s)
                )
                print(format_report(report))
                return 0
            if args.command == "purge-images":
                count = certification.purge_images(
                    s, settings.upload_dir, now, calendar, force=args.force
                )
                s.commit()
                print(f"삭제한 인증 사진: {count}건")
                return 0
            day = args.day or to_kst(now).date()
            if args.command == "open":
                result = market.open_day(s, day, now, calendar)
            else:
                result = market.settle_day(s, day, now, calendar, rng)
            s.commit()
            _print(result.__dict__)
            return 0
        except DomainError as exc:
            s.rollback()
            print(f"[{exc.code}] {exc.message}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
