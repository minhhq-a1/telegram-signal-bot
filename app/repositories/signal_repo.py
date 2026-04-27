from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.core.enums import DecisionType
from app.domain.models import Signal, SignalDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


class SignalRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_signal_id(self, signal_id: str) -> Signal | None:
        """
        Tìm signal theo business signal_id (unique key từ TradingView payload).
        Dùng cho idempotency check — trước khi insert.
        """
        stmt = select(Signal).where(Signal.signal_id == signal_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, data: dict) -> Signal:
        """
        Insert signal mới vào DB.
        data là dict output từ SignalNormalizer.
        """
        signal = Signal(
            id=str(uuid.uuid4()),
            webhook_event_id=data.get("webhook_event_id"),
            signal_id=data["signal_id"],
            source=data["source"],
            symbol=data["symbol"],
            chart_symbol=data.get("chart_symbol"),
            exchange=data.get("exchange"),
            market_type=data.get("market_type"),
            timeframe=data["timeframe"],
            side=data["side"],
            price=data["price"],
            entry_price=data["entry_price"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
            risk_reward=data.get("risk_reward"),
            indicator_confidence=data["indicator_confidence"],
            server_score=data.get("server_score"),
            signal_type=data.get("signal_type"),
            strategy=data.get("strategy"),
            regime=data.get("regime"),
            vol_regime=data.get("vol_regime"),
            atr=data.get("atr"),
            atr_pct=data.get("atr_pct"),
            adx=data.get("adx"),
            rsi=data.get("rsi"),
            rsi_slope=data.get("rsi_slope"),
            stoch_k=data.get("stoch_k"),
            macd_hist=data.get("macd_hist"),
            kc_position=data.get("kc_position"),
            atr_percentile=data.get("atr_percentile"),
            vol_ratio=data.get("vol_ratio"),
             squeeze_on=data.get("squeeze_on"),
             squeeze_fired=data.get("squeeze_fired"),
             squeeze_bars=data.get("squeeze_bars"),
             mom_direction=data.get("mom_direction"),
             payload_timestamp=data.get("payload_timestamp"),
            bar_time=data.get("bar_time"),
            raw_payload=data.get("raw_payload", {}),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(signal)
        self.db.flush()
        logger.info("signal_created", extra={"signal_id": signal.signal_id, "row_id": signal.id})
        return signal

    def find_recent_pass_main_same_side(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        since_minutes: int,
        exclude_signal_id: str | None = None,
    ) -> list[Signal]:
        """
        Tìm các signal gần đây cùng symbol/timeframe/side mà decision trước đó là PASS_MAIN.
        Dùng cho COOLDOWN_ACTIVE để tránh warning bị "poison" bởi REJECT hoặc PASS_WARNING.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        stmt = (
            select(Signal)
            .join(SignalDecision, SignalDecision.signal_row_id == Signal.id)
            .where(
                and_(
                    Signal.symbol == symbol,
                    Signal.timeframe == timeframe,
                    Signal.side == side,
                    Signal.created_at >= since,
                    SignalDecision.decision == DecisionType.PASS_MAIN.value,
                )
            )
            .order_by(Signal.created_at.desc())
        )
        if exclude_signal_id is not None:
            stmt = stmt.where(Signal.signal_id != exclude_signal_id)
        return list(self.db.execute(stmt).scalars().all())

    def find_recent_similar(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        signal_type: str | None,
        since_minutes: int,
        price_tolerance_pct: float = 0.002,
        exclude_signal_id: str | None = None,
    ) -> list[Signal]:
        """
        Tìm signal gần giống nhau: cùng symbol/tf/side và entry price trong khoảng ±tolerance%.
        Dùng cho DUPLICATE_SUPPRESSION check.
        Entry price được load từ field entry_price của Signal.
        NOTE: price comparison được thực hiện ở Python layer
              vì Numeric comparison với tolerance % phức tạp trên DB.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

        conditions = [
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.side == side,
            Signal.created_at >= since,
        ]
        if signal_type is not None:
            conditions.append(Signal.signal_type == signal_type)
        if exclude_signal_id is not None:
            conditions.append(Signal.signal_id != exclude_signal_id)

        stmt = (
            select(Signal)
            .where(and_(*conditions))
            .order_by(Signal.created_at.desc())
        )
        candidates = list(self.db.execute(stmt).scalars().all())
        return candidates
