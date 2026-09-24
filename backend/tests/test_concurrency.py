"""동시성 회귀 테스트 (PostgreSQL 전용 — SQLite는 행 잠금이 없다).

실행(README 참고):
    STUDY_INVEST_TEST_DATABASE_URL=postgresql+psycopg://study:study@localhost/study_invest_test \\
    pytest
"""

from __future__ import annotations

import random
import threading
import time as time_mod
from collections.abc import Callable, Iterator
from datetime import date, datetime, time
from typing import Any

import pytest
from conftest import PNG, TEST_DB_URL
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from study_invest.config import PoolSpec
from study_invest.db import Base, make_engine, make_session_factory
from study_invest.event_calendar import EventCalendar
from study_invest.models import (
    AuditLog,
    CertStatus,
    Holding,
    Order,
    OrderStatus,
    Participant,
    SettlementLog,
    Side,
    StudyCertification,
)
from study_invest.params import KST, EventParams
from study_invest.services import auth, certification, market, trading
from study_invest.services.common import DomainError, market_day

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL.startswith("postgresql"), reason="PostgreSQL 전용(행·advisory 잠금)"
)

CAL = EventCalendar()
D1, D2 = date(2026, 10, 6), date(2026, 10, 7)
NO_LIMIT = EventParams(daily_buy_limit_ratio=1.0)


def at(d: date, h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime.combine(d, time(h, m, s), KST)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = make_engine(PoolSpec("test", TEST_DB_URL, size=20))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    Base.metadata.drop_all(engine)
    engine.dispose()


def setup_participant(factory: sessionmaker[Session], name: str = "alice") -> int:
    with factory() as s:
        p, _ = auth.register(s, name, name, "password123", at(D1, 8), CAL)
        if market_day(s, D1) is None:
            market.open_day(s, D1, at(D1, 9), CAL)
        s.commit()
        return p.id


def run_together(*fns: Callable[[], Any]) -> list[Any]:
    """스레드로 동시에 실행하고 결과(또는 예외)를 돌려준다."""
    barrier = threading.Barrier(len(fns))
    results: list[Any] = [None] * len(fns)

    def wrap(i: int, fn: Callable[[], Any]) -> None:
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # 결과로 검사
            results[i] = exc

    threads = [threading.Thread(target=wrap, args=(i, f)) for i, f in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def buy(
    factory: sessionmaker[Session], pid: int, code: str, qty: int, params: EventParams = NO_LIMIT
) -> Callable[[], OrderStatus]:
    def fn() -> OrderStatus:
        with factory() as s:
            me = s.get(Participant, pid)  # 인증 의존성처럼 잠금 전에 미리 읽음
            assert me is not None
            _ = me.holdings
            time_mod.sleep(0.05)
            order = trading.place_order(s, me, code, Side.BUY, qty, at(D1, 10), CAL, params)
            s.commit()
            return order.status

    return fn


class TestOrders:
    def test_no_lost_update(self, factory: sessionmaker[Session]) -> None:
        pid = setup_participant(factory)
        buy(factory, pid, "SAMSU", 1)()
        statuses = run_together(*(buy(factory, pid, "SAMSU", 2) for _ in range(2)))
        assert statuses == [OrderStatus.FILLED] * 2
        with factory() as s:
            me = s.get(Participant, pid)
            holding = s.get(Holding, (pid, "SAMSU"))
            assert me is not None and holding is not None
            assert me.cash == 1_000_000 - 75_000 - 2 * 150_000
            assert (holding.quantity, holding.cost) == (5, 375_000)

    def test_first_buy_race_creates_one_holding(self, factory: sessionmaker[Session]) -> None:
        pid = setup_participant(factory)
        statuses = run_together(*(buy(factory, pid, "LB", 3) for _ in range(4)))
        assert statuses == [OrderStatus.FILLED] * 4
        with factory() as s:
            holding = s.get(Holding, (pid, "LB"))
            assert holding is not None and holding.quantity == 12

    def test_buy_limit_not_bypassed(self, factory: sessionmaker[Session]) -> None:
        pid = setup_participant(factory)  # 한도 400,000
        statuses = run_together(*(buy(factory, pid, "SAMSU", 4, EventParams()) for _ in range(2)))
        assert sorted(statuses) == [OrderStatus.FILLED, OrderStatus.REJECTED]

    def test_many_concurrent_orders_keep_cash_consistent(
        self, factory: sessionmaker[Session]
    ) -> None:
        pid = setup_participant(factory)
        run_together(*(buy(factory, pid, code, 1) for code in ("SAMSU", "MIRAE", "LB") * 6))
        with factory() as s:
            me = s.get(Participant, pid)
            assert me is not None
            spent = s.scalar(
                select(func.sum(Order.amount)).where(Order.status == OrderStatus.FILLED)
            )
            assert me.cash == 1_000_000 - int(spent or 0)


class TestSettlementBoundary:
    def test_inflight_order_is_included(self, factory: sessionmaker[Session]) -> None:
        pid = setup_participant(factory)
        flushed = threading.Event()

        def order() -> OrderStatus:
            with factory() as s:
                me = s.get(Participant, pid)
                assert me is not None
                o = trading.place_order(
                    s, me, "LB", Side.BUY, 20, at(D1, 17, 59, 59), CAL, EventParams()
                )
                flushed.set()
                time_mod.sleep(0.5)  # 느린 요청: 정산이 이 사이에 시작된다
                s.commit()
                return o.status

        def settle() -> int:
            flushed.wait(5)
            with factory() as s:
                market.settle_day(s, D1, at(D1, 18), CAL, random.Random(1))
                s.commit()
                log = s.scalars(select(SettlementLog)).one()
                return int(next(x["buy_amount"] for x in log.stocks if x["code"] == "LB"))

        status, lb_amount = run_together(order, settle)
        assert status == OrderStatus.FILLED
        assert lb_amount == 280_000  # 진행 중이던 주문이 집계에 포함됨

    def test_order_after_settlement_started_is_rejected(
        self, factory: sessionmaker[Session]
    ) -> None:
        pid = setup_participant(factory)
        locked = threading.Event()

        def settle() -> None:
            with factory() as s:
                market.settle_day(s, D1, at(D1, 18), CAL, random.Random(1))
                locked.set()
                time_mod.sleep(0.5)  # 정산 트랜잭션이 잠금을 쥔 채 진행 중
                s.commit()

        def order() -> tuple[OrderStatus, str | None]:
            locked.wait(5)
            with factory() as s:
                me = s.get(Participant, pid)
                assert me is not None
                o = trading.place_order(
                    s, me, "LB", Side.BUY, 1, at(D1, 17, 59, 59), CAL, EventParams()
                )
                s.commit()
                return o.status, o.reject_reason

        _, (status, reason) = run_together(settle, order)
        assert (status, reason) == (OrderStatus.REJECTED, "MARKET_CLOSED")


class TestUniqueConflicts:
    def test_duplicate_certification_is_409_not_500(
        self, factory: sessionmaker[Session], tmp_path: Any
    ) -> None:
        pid = setup_participant(factory)

        def submit() -> str:
            with factory() as s:
                me = s.get(Participant, pid)
                assert me is not None
                certification.submit(
                    s, me, PNG, at(D1, 12), CAL, EventParams(), tmp_path, 10_000_000
                )
                time_mod.sleep(0.2)
                s.commit()
                return "ok"

        results = run_together(submit, submit)
        codes = sorted(r if isinstance(r, str) else getattr(r, "code", repr(r)) for r in results)
        assert codes == ["ALREADY_CERTIFIED", "ok"]
        with factory() as s:
            assert s.scalar(select(func.count()).select_from(StudyCertification)) == 1

    def test_duplicate_registration_is_domain_error(self, factory: sessionmaker[Session]) -> None:
        def register(nickname: str) -> Callable[[], str]:
            def fn() -> str:
                with factory() as s:
                    auth.register(s, "same@corp", nickname, "password123", at(D1, 8), CAL)
                    time_mod.sleep(0.2)
                    s.commit()
                    return "ok"

            return fn

        results = run_together(register("one"), register("two"))
        assert sorted(r if isinstance(r, str) else r.code for r in results) == [
            "IDENTITY_TAKEN",
            "ok",
        ]
        assert all(isinstance(r, str | DomainError) for r in results)


class TestSchedulers:
    def test_parallel_run_due_does_not_error(self, factory: sessionmaker[Session]) -> None:
        pid = setup_participant(factory)
        with factory() as s:
            s.add(
                StudyCertification(
                    participant_id=pid,
                    target_date=D1,
                    image_path=None,
                    image_content_type="image/png",
                    image_hash="x",
                    status=CertStatus.APPROVED,
                    submitted_at=at(D1, 12),
                )
            )
            s.commit()
        for now in (at(D1, 18, 1), at(D2, 9)):
            outs = run_together(
                *(
                    (lambda n=now: market.run_due(factory, n, CAL, random.SystemRandom()))
                    for _ in range(4)
                )
            )
            flat = [r for out in outs for r in out]
            assert not [r for r in flat if isinstance(r, dict)], flat  # 오류 없음
            assert len(flat) == 1  # 정확히 한 번 실행
        with factory() as s:
            assert s.scalar(select(func.count()).select_from(SettlementLog)) == 1
            assert (
                s.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.action == "reward.pay")
                )
                == 1
            )


class TestRewardsShareTheParticipantLock:
    def test_reward_payment_waits_for_an_inflight_order(
        self, factory: sessionmaker[Session]
    ) -> None:
        """보상 지급은 주문과 같은 참가자 잠금을 거친다: 주문 트랜잭션이 끝날 때까지 기다린다.

        이미 병더리움을 가진 참가자라 보상은 기존 보유 행 UPDATE다(새 행 INSERT라면 FK 검사가
        참가자 행을 잠가 우연히 기다리게 되므로, 잠금 누락을 드러내지 못한다).
        """
        pid = setup_participant(factory)
        with factory() as s:
            s.add(Holding(participant_id=pid, code="BYUNG", quantity=2, cost=0))
            s.add(
                StudyCertification(
                    participant_id=pid,
                    target_date=D1,
                    image_path=None,
                    image_content_type="image/png",
                    image_hash="r",
                    status=CertStatus.APPROVED,
                    submitted_at=at(D1, 12),
                )
            )
            s.commit()
        locked = threading.Event()
        timeline: list[str] = []

        def order() -> None:
            with factory() as s:
                me = s.get(Participant, pid)
                assert me is not None
                trading.place_order(s, me, "LB", Side.BUY, 1, at(D1, 17), CAL, EventParams())
                locked.set()
                time_mod.sleep(0.5)
                timeline.append("order-commit")
                s.commit()

        def reward() -> None:
            locked.wait(5)
            with factory() as s:
                certification.pay_rewards(s, D2, at(D2, 9), EventParams())
                timeline.append("reward-done")
                s.commit()

        run_together(order, reward)
        assert timeline == ["order-commit", "reward-done"]
        with factory() as s:
            coin = s.get(Holding, (pid, "BYUNG"))
            lb = s.get(Holding, (pid, "LB"))
            assert coin is not None and coin.quantity == 3
            assert lb is not None and lb.quantity == 1
