from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.domain.models import Signal
from app.domain.schemas import SignalDetailResponse, SignalReverifyHistoryResponse, SignalOutcomeSchema
from app.api.dependencies import require_dashboard_auth
from app.api.rate_limiter import limiter
from app.repositories.signal_repo import SignalRepository
from app.repositories.config_repo import ConfigRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.repositories.reverify_repo import ReverifyRepository
from app.services.filter_engine import FilterEngine
from app.services.reject_codes import rule_code_to_reject_code

router = APIRouter(tags=["signals"])


def _build_reverify_signal_dict(signal: Signal) -> tuple[dict, list[str]]:
    def _float(col):
        v = getattr(signal, col, None)
        return float(v) if v is not None else None

    required = ("entry_price", "risk_reward", "indicator_confidence")
    missing = [f for f in required if getattr(signal, f, None) is None]

    return {
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "side": signal.side.value if hasattr(signal.side, "value") else signal.side,
        "price": float(signal.price),
        "entry_price": float(signal.entry_price),
        "stop_loss": float(signal.stop_loss) if signal.stop_loss is not None else None,
        "take_profit": float(signal.take_profit) if signal.take_profit is not None else None,
        "risk_reward": float(signal.risk_reward) if signal.risk_reward is not None else None,
        "indicator_confidence": float(signal.indicator_confidence) if signal.indicator_confidence is not None else None,
        "signal_type": signal.signal_type,
        "strategy": signal.strategy,
        "regime": signal.regime,
        "vol_regime": signal.vol_regime,
        "atr": _float("atr"),
        "atr_pct": _float("atr_pct"),
        "adx": _float("adx"),
        "rsi": _float("rsi"),
        "rsi_slope": _float("rsi_slope"),
        "stoch_k": _float("stoch_k"),
        "macd_hist": _float("macd_hist"),
        "kc_position": _float("kc_position"),
        "atr_percentile": _float("atr_percentile"),
        "vol_ratio": _float("vol_ratio"),
        "squeeze_on": signal.squeeze_on,
        "squeeze_fired": signal.squeeze_fired,
        "squeeze_bars": signal.squeeze_bars,
        "mom_direction": signal.mom_direction,
        "payload_timestamp": signal.payload_timestamp,
        "bar_time": signal.bar_time,
    }, missing


def _extract_reverify_metadata(result):
    from app.core.enums import RuleResult

    all_results = result.filter_results
    first_fail = next((r for r in all_results if r.result == RuleResult.FAIL), None)
    reject_code = rule_code_to_reject_code(first_fail.rule_code) if first_fail else None
    score_item = next((r for r in all_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"), None)
    score_value: float | None = None
    score_items: list | None = None
    if score_item and score_item.details:
        score_value = score_item.details.get("score")
        score_items = score_item.details.get("items")
    return all_results, reject_code, score_value, score_items


@router.get("/api/v1/signals/{signal_id}", response_model=SignalDetailResponse)
async def get_signal_detail(signal_id: str, db: Session = Depends(get_db), _auth: None = Depends(require_dashboard_auth)):
    # Eager load các quan hệ để tránh N+1 query
    stmt = (
        select(Signal)
        .where(Signal.signal_id == signal_id)
        .options(
            joinedload(Signal.decision),
            joinedload(Signal.filter_results),
            joinedload(Signal.telegram_messages),
            joinedload(Signal.outcomes),
        )
    )

    signal = db.execute(stmt).scalars().unique().one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    return {
        "signal_id": signal.signal_id,
        "signal": signal,
        "decision": signal.decision,
        "filter_results": signal.filter_results,
        "telegram_messages": signal.telegram_messages,
        "outcomes": signal.outcomes,
    }


@router.post("/api/v1/signals/{signal_id}/reverify")
@limiter.limit("30/minute")
def reverify_signal(
    request: Request,
    signal_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Non-mutating replay of the filter + strategy pipeline.

    Schema-drift resilience (Finding #2 fix):
    - Pipeline input is built entirely from persisted signal columns (DB snapshot),
      NOT from raw_payload. This ensures legacy/invalid payload shapes do not
      affect replay outcomes.
    - Returns explicit 422 with clear detail when required persisted fields are missing.
    """
    # 1. Find signal
    signal_repo = SignalRepository(db)
    signal = signal_repo.find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    # 2. Get original decision
    decision_repo = DecisionRepository(db)
    original = decision_repo.find_by_signal_row_id(signal.id)
    original_decision = original.decision if original else "UNKNOWN"

    signal_dict, missing = _build_reverify_signal_dict(signal)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "missing_required_persisted_fields",
                "missing_fields": missing,
                "message": (
                    "Cannot reverify: required persisted signal fields are missing. "
                    "This may indicate a schema migration issue or incomplete data."
                ),
            },
        )

    # 4. Run filter engine with current config
    config_repo = ConfigRepository(db)
    config = config_repo.get_signal_bot_config()
    engine = FilterEngine(config, signal_repo, MarketEventRepository(db))
    result = engine.run(signal_dict)

    all_results, reject_code, score_value, score_items = _extract_reverify_metadata(result)

    # 8. Persist reverify result (non-mutating audit log)
    ReverifyRepository(db).create({
        "signal_row_id": signal.id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code.value if hasattr(reject_code, "value") else reject_code,
        "decision_reason": result.decision_reason,
        "score_items": score_items,
        "filter_results": [r.to_dict() for r in all_results],
    })
    db.commit()

    return {
        "signal_id": signal_id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code.value if hasattr(reject_code, "value") else reject_code,
        "decision_reason": result.decision_reason,
    }


@router.post("/api/v1/signals/reverify/batch")
@limiter.limit("10/minute")
def reverify_signals_batch(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    days = int(payload.get("days", 30))
    limit = int(payload.get("limit", 500))
    if limit > 1000:
        raise HTTPException(status_code=400, detail={"error_code": "BATCH_LIMIT_EXCEEDED", "message": "limit must be <= 1000"})

    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(Signal).options(joinedload(Signal.decision)).where(Signal.created_at >= since).order_by(Signal.created_at.desc()).limit(limit)

    decision_filter = payload.get("decision") or []
    signal_type_filter = payload.get("signal_type") or []
    if decision_filter:
        stmt = stmt.join(SignalDecision, SignalDecision.signal_row_id == Signal.id).where(SignalDecision.decision.in_(decision_filter))
    if signal_type_filter:
        stmt = stmt.where(Signal.signal_type.in_(signal_type_filter))

    signals = list(db.execute(stmt).scalars().unique().all())
    signal_repo = SignalRepository(db)
    config = ConfigRepository(db).get_signal_bot_config()
    engine = FilterEngine(config, signal_repo, MarketEventRepository(db))
    persist_results = bool(payload.get("persist_results", True))

    summary: dict[str, int] = {}
    results = []
    changed_decisions = 0

    for signal in signals:
        signal_dict, missing = _build_reverify_signal_dict(signal)
        if missing:
            continue

        original_decision = signal.decision.decision if signal.decision else "UNKNOWN"
        result = engine.run(signal_dict)
        changed = original_decision != result.final_decision.value
        if changed:
            changed_decisions += 1
            key = f"{original_decision}->{result.final_decision.value}"
            summary[key] = summary.get(key, 0) + 1

        all_results, reject_code, score_value, score_items = _extract_reverify_metadata(result)
        if persist_results:
            ReverifyRepository(db).create({
                "signal_row_id": signal.id,
                "original_decision": original_decision,
                "reverify_decision": result.final_decision.value,
                "reverify_score": score_value,
                "reject_code": reject_code.value if hasattr(reject_code, "value") else reject_code,
                "decision_reason": result.decision_reason,
                "score_items": score_items,
                "filter_results": [r.to_dict() for r in all_results],
            })

        results.append({
            "signal_id": signal.signal_id,
            "original_decision": original_decision,
            "reverify_decision": result.final_decision.value,
            "changed": changed,
            "decision_reason": result.decision_reason,
        })

    if persist_results:
        db.commit()

    return {
        "requested": limit,
        "processed": len(results),
        "changed_decisions": changed_decisions,
        "summary": summary,
        "results": results,
    }

@router.get(
    "/api/v1/signals/{signal_id}/reverify-results",
    response_model=SignalReverifyHistoryResponse,
)
def get_reverify_results(
    signal_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    signal_repo = SignalRepository(db)
    signal = signal_repo.find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    rows = ReverifyRepository(db).list_for_signal(signal.id)
    return {
        "signal_id": signal.signal_id,
        "count": len(rows),
        "results": rows,
    }
