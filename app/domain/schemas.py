from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Any, Literal
from datetime import datetime
from app.core.enums import SignalSide, DecisionType, RuleResult, RuleSeverity, DeliveryStatus

class SignalMetadata(BaseModel):
    # Trade parameters (required in payload contract)
    entry: float
    stop_loss: float
    take_profit: float
    
    # Indicators
    atr: float | None = None
    atr_pct: float | None = None
    adx: float | None = None
    rsi: float | None = None
    rsi_slope: float | None = None
    stoch_k: float | None = None
    macd_hist: float | None = None
    kc_position: float | None = None
    atr_percentile: float | None = None
    vol_ratio: float | None = None
    
    # Signal classification
    signal_type: str | None = None
    strategy: str | None = None
    regime: str | None = None
    vol_regime: str | None = None
    
    # Squeeze indicators
    squeeze_on: int | None = None
    squeeze_fired: int | None = None
    squeeze_bars: int | None = None
    
    # Metadata
    strategy_name: str | None = None
    strategy_version: str | None = None
    indicators: list[str] = Field(default_factory=list)
    volume_24h: float | None = None
    expected_wr: str | None = None
    bar_confirmed: bool | None = None

class TradingViewWebhookPayload(BaseModel):
    # Core identifying fields
    signal_id: str | None = Field(None, description="Unique ID from TradingView. If missing, bot will generate one.")
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    
    # Signal data
    signal: Literal["long", "short"]
    price: float = Field(..., gt=0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    
    # Optional top-level fields
    timestamp: datetime | None = None
    bar_time: datetime | None = None
    chart_symbol: str | None = None
    exchange: str | None = None
    market_type: str | None = None
    payload_version: str | None = None
    secret: str | None = None  # Auth secret (handled at controller layer)
    
    # Extra data
    metadata: SignalMetadata

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v.strip().upper()

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v.strip().lower()

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v.strip()

class WebhookAcceptedResponse(BaseModel):
    status: str = "accepted"
    signal_id: str
    decision: DecisionType
    timestamp: datetime

class FilterResultSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule_code: str
    result: RuleResult
    severity: RuleSeverity
    score_delta: float
    details: dict[str, Any] | None = None

class TelegramMessageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel_type: str = Field(validation_alias="route", serialization_alias="channel_type")
    chat_id: str
    message_text: str
    delivery_status: DeliveryStatus
    sent_at: datetime | None = None

class SignalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signal_id: str
    side: SignalSide
    symbol: str
    timeframe: str
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    indicator_confidence: float
    server_score: float | None = None
    signal_type: str | None = None
    strategy: str | None = None
    regime: str | None = None
    vol_regime: str | None = None
    created_at: datetime

class DecisionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    decision: DecisionType
    decision_reason: str
    telegram_route: str
    created_at: datetime

class SignalDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    signal_id: str
    signal: SignalSchema
    decision: DecisionSchema | None = None
    filter_results: list[FilterResultSchema] = Field(default_factory=list)
    telegram_messages: list[TelegramMessageSchema] = Field(default_factory=list)

class ErrorResponse(BaseModel):
    status: str = "rejected"
    error_code: str
    message: str
