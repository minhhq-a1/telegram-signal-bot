from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import logger
from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, TelegramRoute
from app.domain.schemas import TradingViewWebhookPayload, WebhookAcceptedResponse, ErrorResponse
from app.repositories.webhook_event_repo import WebhookEventRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.filter_result_repo import FilterResultRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.telegram_repo import TelegramRepository
from app.repositories.config_repo import ConfigRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.services.auth_service import AuthService
from app.services.signal_normalizer import SignalNormalizer
from app.services.filter_engine import FilterEngine
from app.services.message_renderer import MessageRenderer
from app.services.telegram_notifier import TelegramNotifier

router = APIRouter(tags=["webhooks"])

@router.post("/api/v1/webhooks/tradingview", response_model=WebhookAcceptedResponse)
async def handle_tradingview_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    # Init Repositories
    webhook_repo = WebhookEventRepository(db)
    signal_repo = SignalRepository(db)
    filter_repo = FilterResultRepository(db)
    decision_repo = DecisionRepository(db)
    telegram_repo = TelegramRepository(db)
    config_repo = ConfigRepository(db)
    market_repo = MarketEventRepository(db)
    notifier = TelegramNotifier()

    raw_body_bytes = await request.body()
    raw_body_text = raw_body_bytes.decode("utf-8", errors="replace")

    try:
        payload_dict = json.loads(raw_body_text)
    except json.JSONDecodeError:
        webhook_repo.create(
            {
                "source_ip": request.client.host if request.client else None,
                "http_headers": dict(request.headers),
                "raw_body": {"_raw_body_text": raw_body_text},
                "is_valid_json": False,
                "auth_status": AuthStatus.MISSING.value,
                "error_message": "INVALID_JSON: Request body is not valid JSON",
            }
        )
        db.commit()
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error_code="INVALID_JSON",
                message="Request body is not valid JSON",
            ).model_dump(mode="json"),
        )

    try:
        payload = TradingViewWebhookPayload.model_validate(payload_dict)
    except ValidationError as exc:
        webhook_repo.create(
            {
                "source_ip": request.client.host if request.client else None,
                "http_headers": dict(request.headers),
                "raw_body": payload_dict if isinstance(payload_dict, dict) else {"payload": payload_dict},
                "is_valid_json": True,
                "auth_status": AuthStatus.MISSING.value,
                "error_message": f"INVALID_SCHEMA: {exc.errors()[0]['msg']}",
            }
        )
        db.commit()
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error_code="INVALID_SCHEMA",
                message="Request body does not match webhook schema",
            ).model_dump(mode="json"),
        )
    # 0. Generate signal_id if missing (Deterministic for idempotency)
    if not payload.signal_id:
        # We use symbol, timeframe, signal, and price to create a unique fingerprint
        payload.signal_id = f"{payload.symbol}-{payload.timeframe}-{payload.signal}-{payload.price}"

    # 1. Validate Auth (using AuthService + secrets.compare_digest)
    is_authed = AuthService.validate_secret(payload.secret)
    auth_status = AuthStatus.OK if is_authed else AuthStatus.INVALID_SECRET

    # 2. Store Raw Webhook Event (Audit-first)
    webhook_event = webhook_repo.create({
        "source_ip": request.client.host if request.client else None,
        "http_headers": dict(request.headers),
        "raw_body": payload.model_dump(mode="json"),
        "is_valid_json": True,
        "auth_status": auth_status.value
    })

    if not is_authed:
        webhook_repo.mark_auth_failure(webhook_event.id, "Invalid shared secret")
        db.commit()
        return JSONResponse(
            status_code=401,
            content=ErrorResponse(
                error_code="INVALID_SECRET",
                message="Webhook authentication failed",
            ).model_dump(mode="json"),
        )

    # 3. Idempotency Check
    existing_signal = signal_repo.find_by_signal_id(payload.signal_id)
    if existing_signal:
        db.commit()
        return WebhookAcceptedResponse(
            signal_id=payload.signal_id,
            decision=DecisionType.DUPLICATE,
            timestamp=datetime.now(timezone.utc),
        )

    # 4. Normalize Signal
    norm_data = SignalNormalizer.normalize(webhook_event.id, payload)

    # 5. Create Signal Entry (Persist before notify)
    signal_obj = signal_repo.create(norm_data)

    # 6. Run Filter Engine
    config = config_repo.get_signal_bot_config()
    engine = FilterEngine(config, signal_repo, market_repo)
    filter_result = engine.run(norm_data)

    # 7. Update Signal with Score
    signal_obj.server_score = filter_result.server_score

    # 8. Store Filter Results
    filter_repo.bulk_insert(
        [{"rule_code": r.rule_code, "rule_group": r.rule_group, "result": r.result.value, 
          "severity": r.severity.value, "score_delta": r.score_delta, "details": r.details} 
         for r in filter_result.filter_results],
        signal_obj.id
    )

    # 9. Store Decision
    decision_repo.create({
        "signal_row_id": signal_obj.id,
        "decision": filter_result.final_decision.value,
        "decision_reason": filter_result.decision_reason,
        "telegram_route": filter_result.route.value
    })

    # COMMIT LẦN 1: Lưu trạng thái DB trước khi ra internet
    db.commit()

    # 10. Pass/Warning/Reject Logic -> Telegram
    msg_text = None
    route_to_send = None

    if filter_result.final_decision == DecisionType.PASS_MAIN:
        msg_text = MessageRenderer.render_main(norm_data, filter_result.server_score)
        route_to_send = TelegramRoute.MAIN
    elif filter_result.final_decision == DecisionType.PASS_WARNING:
        # Collect warning reasons
        reasons = [r.rule_code for r in filter_result.filter_results if r.result.value == "WARN"]
        reason_str = ", ".join(reasons) if reasons else "Warning rules triggered"
        msg_text = MessageRenderer.render_warning(norm_data, filter_result.server_score, reason_str)
        route_to_send = TelegramRoute.WARN
    elif filter_result.final_decision == DecisionType.REJECT and config.get("log_reject_to_admin"):
        msg_text = MessageRenderer.render_reject_admin(norm_data, filter_result.decision_reason)
        route_to_send = TelegramRoute.ADMIN
    
    if msg_text and route_to_send:
        # Notify
        route_value = route_to_send.value
        status, response, error_detail = await notifier.notify(route_value, msg_text)
        chat_id = notifier.resolve_chat_id(route_value) or "N/A"
        status_value = status if isinstance(status, str) else status.value
        sent_at = datetime.now(timezone.utc) if status_value == DeliveryStatus.SENT.value else None
        telegram_message_id = None
        if response:
            telegram_message_id = str(response.get("_telegram_message_id") or response.get("result", {}).get("message_id") or "")
            if telegram_message_id == "":
                telegram_message_id = None
        
        # Log Telegram Message
        telegram_repo.create({
            "signal_row_id": signal_obj.id,
            "route": route_value,
            "chat_id": str(chat_id),
            "message_text": msg_text,
            "telegram_message_id": telegram_message_id,
            "delivery_status": status_value,
            "error_log": error_detail,
            "sent_at": sent_at,
        })

    # 11. Final Commit (Lưu log Telegram)
    db.commit()

    return WebhookAcceptedResponse(
        signal_id=payload.signal_id,
        decision=filter_result.final_decision,
        timestamp=datetime.now(timezone.utc)
    )
