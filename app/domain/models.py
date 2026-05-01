from __future__ import annotations
from datetime import datetime, timezone
from typing import List
from sqlalchemy import String, Numeric, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.enums import SignalSide, DecisionType, RuleResult, RuleSeverity, DeliveryStatus, TelegramRoute, AuthStatus

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    http_headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_body: Mapped[dict] = mapped_column(JSON)
    is_valid_json: Mapped[bool] = mapped_column(default=True)
    auth_status: Mapped[AuthStatus] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    webhook_event_id: Mapped[str | None] = mapped_column(ForeignKey("webhook_events.id"), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True)
    source: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    chart_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    side: Mapped[SignalSide] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Numeric(18, 8))
    entry_price: Mapped[float] = mapped_column(Numeric(18, 8))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    indicator_confidence: Mapped[float] = mapped_column(Numeric(6, 4))
    server_score: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    signal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    regime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vol_regime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    atr: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    atr_pct: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    adx: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    rsi: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    rsi_slope: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    stoch_k: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    macd_hist: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    kc_position: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    atr_percentile: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    vol_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    squeeze_on: Mapped[bool | None] = mapped_column(nullable=True)
    squeeze_fired: Mapped[bool | None] = mapped_column(nullable=True)
    squeeze_bars: Mapped[int | None] = mapped_column(nullable=True)
    mom_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bar_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    filter_results: Mapped[List["SignalFilterResult"]] = relationship(back_populates="signal")
    decision: Mapped["SignalDecision"] = relationship(back_populates="signal")
    telegram_messages: Mapped[List["TelegramMessage"]] = relationship(back_populates="signal")
    outcomes: Mapped[List["SignalOutcome"]] = relationship(back_populates="signal")
    reverify_results: Mapped[List["SignalReverifyResult"]] = relationship(back_populates="signal")

class SignalFilterResult(Base):
    __tablename__ = "signal_filter_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str] = mapped_column(ForeignKey("signals.id"))
    rule_code: Mapped[str] = mapped_column(String(64))
    rule_group: Mapped[str] = mapped_column(String(64))
    result: Mapped[RuleResult] = mapped_column(String(16))
    severity: Mapped[RuleSeverity] = mapped_column(String(16))
    score_delta: Mapped[float] = mapped_column(Numeric(6, 4))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    signal: Mapped["Signal"] = relationship(back_populates="filter_results")

class SignalDecision(Base):
    __tablename__ = "signal_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str] = mapped_column(ForeignKey("signals.id"), unique=True)
    decision: Mapped[DecisionType] = mapped_column(String(32))
    decision_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_route: Mapped[TelegramRoute | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    signal: Mapped["Signal"] = relationship(back_populates="decision")

class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    chat_id: Mapped[str] = mapped_column(String(50))
    route: Mapped[TelegramRoute] = mapped_column(String(20))
    message_text: Mapped[str] = mapped_column(String)
    telegram_message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(String(20))
    error_log: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    signal: Mapped["Signal"] = relationship(back_populates="telegram_messages")

# FUTURE: SignalOutcome will be populated when trade outcome tracking is implemented
# (e.g. via PnL reporting, trade closed events from the broker).
# The relationship is already wired; insert logic will be added in a follow-up PR.
class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), unique=True)
    outcome_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_win: Mapped[bool | None] = mapped_column(nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    max_favorable_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    max_adverse_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    mfe_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    mae_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    signal: Mapped["Signal"] = relationship(back_populates="outcomes")

class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    config_value: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SystemConfigAuditLog(Base):
    __tablename__ = "system_config_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(128))
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict] = mapped_column(JSON)
    changed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SignalReverifyResult(Base):
    __tablename__ = "signal_reverify_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    original_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reverify_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reverify_score: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    reject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    score_items: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    filter_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    signal: Mapped["Signal"] = relationship(back_populates="reverify_results")


class MarketEvent(Base):
    __tablename__ = "market_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    impact: Mapped[str] = mapped_column(String(20)) # HIGH, MEDIUM, LOW
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MarketContextSnapshot(Base):
    __tablename__ = "market_context_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(16))
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    backend_regime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    backend_vol_regime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ema_fast: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    ema_mid: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    ema_slow: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    atr_pct: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    raw_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
