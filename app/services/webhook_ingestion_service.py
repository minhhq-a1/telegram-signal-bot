from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, TelegramRoute
from app.core.logging import logger
from app.domain.schemas import ErrorResponse, TradingViewWebhookPayload, WebhookAcceptedResponse
from app.repositories.config_repo import ConfigRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.filter_result_repo import FilterResultRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.telegram_repo import TelegramRepository
from app.repositories.webhook_event_repo import WebhookEventRepository
from app.services.auth_service import AuthService
from app.services.filter_engine import FilterEngine
from app.services.message_renderer import MessageRenderer
from app.services.signal_normalizer import SignalNormalizer
from app.services.telegram_notifier import TelegramNotifier


@dataclass
class WebhookServiceResult:
    status_code: int
    body: WebhookAcceptedResponse | ErrorResponse
    is_error: bool = False


class WebhookIngestionService:
    def __init__(
        self,
        db: Session,
        notifier: TelegramNotifier,
        webhook_repo_cls: type[WebhookEventRepository] = WebhookEventRepository,
        signal_repo_cls: type[SignalRepository] = SignalRepository,
        filter_repo_cls: type[FilterResultRepository] = FilterResultRepository,
        decision_repo_cls: type[DecisionRepository] = DecisionRepository,
        telegram_repo_cls: type[TelegramRepository] = TelegramRepository,
        config_repo_cls: type[ConfigRepository] = ConfigRepository,
        market_event_repo_cls: type[MarketEventRepository] = MarketEventRepository,
    ) -> None:
        self.db = db
        self.notifier = notifier
        self.webhook_repo = webhook_repo_cls(db)
        self.signal_repo = signal_repo_cls(db)
        self.filter_repo = filter_repo_cls(db)
        self.decision_repo = decision_repo_cls(db)
        self.telegram_repo = telegram_repo_cls(db)
        self.config_repo = config_repo_cls(db)
        self.market_repo = market_event_repo_cls(db)

    async def ingest(self, raw_body_text: str, source_ip: str | None, headers: dict[str, Any]) -> WebhookServiceResult:
        payload_dict = self._parse_json(raw_body_text, source_ip, headers)
        if isinstance(payload_dict, WebhookServiceResult):
            return payload_dict

        payload = self._validate_payload(payload_dict, source_ip, headers)
        if isinstance(payload, WebhookServiceResult):
            return payload

        is_authed = AuthService.validate_secret(payload.secret)
        auth_status = AuthStatus.OK if is_authed else AuthStatus.INVALID_SECRET

        webhook_event = self.webhook_repo.create(
            {
                "source_ip": source_ip,
                "http_headers": headers,
                "raw_body": payload.model_dump(mode="json"),
                "is_valid_json": True,
                "auth_status": auth_status.value,
            }
        )

        if not is_authed:
            self.webhook_repo.mark_auth_failure(webhook_event.id, "Invalid shared secret")
            self.db.commit()
            return self._error_result(
                401,
                ErrorResponse(
                    error_code="INVALID_SECRET",
                    message="Webhook authentication failed",
                ),
            )

        existing_signal = self.signal_repo.find_by_signal_id(payload.signal_id)
        if existing_signal:
            self.db.commit()
            return self._accepted_result(payload.signal_id, DecisionType.DUPLICATE)

        norm_data = SignalNormalizer.normalize(webhook_event.id, payload)

        try:
            with self.db.begin_nested():
                signal_obj = self.signal_repo.create(norm_data)
        except IntegrityError as exc:
            existing_signal = self.signal_repo.find_by_signal_id(payload.signal_id)
            if existing_signal is None:
                raise exc

            logger.warning(
                "signal_insert_race_detected",
                extra={"signal_id": payload.signal_id, "existing_row_id": existing_signal.id},
            )
            self.db.commit()
            return self._accepted_result(payload.signal_id, DecisionType.DUPLICATE)

        config = self.config_repo.get_signal_bot_config()
        engine = FilterEngine(config, self.signal_repo, self.market_repo)
        filter_result = engine.run(norm_data)

        signal_obj.server_score = filter_result.server_score

        self.filter_repo.bulk_insert(
            [
                {
                    "rule_code": result.rule_code,
                    "rule_group": result.rule_group,
                    "result": result.result.value,
                    "severity": result.severity.value,
                    "score_delta": result.score_delta,
                    "details": result.details,
                }
                for result in filter_result.filter_results
            ],
            signal_obj.id,
        )

        self.decision_repo.create(
            {
                "signal_row_id": signal_obj.id,
                "decision": filter_result.final_decision.value,
                "decision_reason": filter_result.decision_reason,
                "telegram_route": filter_result.route.value,
            }
        )

        self.db.commit()

        await self._notify_and_log(norm_data, signal_obj.id, filter_result, config)

        self.db.commit()
        return self._accepted_result(payload.signal_id, filter_result.final_decision)

    def _parse_json(
        self,
        raw_body_text: str,
        source_ip: str | None,
        headers: dict[str, Any],
    ) -> dict[str, Any] | WebhookServiceResult:
        try:
            return json.loads(raw_body_text)
        except json.JSONDecodeError:
            self.webhook_repo.create(
                {
                    "source_ip": source_ip,
                    "http_headers": headers,
                    "raw_body": {"_raw_body_text": raw_body_text},
                    "is_valid_json": False,
                    "auth_status": AuthStatus.MISSING.value,
                    "error_message": "INVALID_JSON: Request body is not valid JSON",
                }
            )
            self.db.commit()
            return self._error_result(
                400,
                ErrorResponse(
                    error_code="INVALID_JSON",
                    message="Request body is not valid JSON",
                ),
            )

    def _validate_payload(
        self,
        payload_dict: dict[str, Any],
        source_ip: str | None,
        headers: dict[str, Any],
    ) -> TradingViewWebhookPayload | WebhookServiceResult:
        try:
            return TradingViewWebhookPayload.model_validate(payload_dict)
        except ValidationError as exc:
            first_error = exc.errors()[0]
            error_loc = ".".join(str(part) for part in first_error.get("loc", ()))
            error_msg = first_error["msg"]
            if error_loc:
                error_message = f"INVALID_SCHEMA: {error_loc}: {error_msg}"
            else:
                error_message = f"INVALID_SCHEMA: {error_msg}"

            self.webhook_repo.create(
                {
                    "source_ip": source_ip,
                    "http_headers": headers,
                    "raw_body": payload_dict if isinstance(payload_dict, dict) else {"payload": payload_dict},
                    "is_valid_json": True,
                    "auth_status": AuthStatus.MISSING.value,
                    "error_message": error_message,
                }
            )
            self.db.commit()
            return self._error_result(
                400,
                ErrorResponse(
                    error_code="INVALID_SCHEMA",
                    message="Request body does not match webhook schema",
                ),
            )

    async def _notify_and_log(self, norm_data: dict[str, Any], signal_row_id: str, filter_result: Any, config: dict[str, Any]) -> None:
        msg_text = None
        route_to_send = None

        if filter_result.final_decision == DecisionType.PASS_MAIN:
            msg_text = MessageRenderer.render_main(norm_data, filter_result.server_score)
            route_to_send = TelegramRoute.MAIN
        elif filter_result.final_decision == DecisionType.PASS_WARNING:
            reasons = [result.rule_code for result in filter_result.filter_results if result.result.value == "WARN"]
            reason_str = ", ".join(reasons) if reasons else "Warning rules triggered"
            msg_text = MessageRenderer.render_warning(norm_data, filter_result.server_score, reason_str)
            route_to_send = TelegramRoute.WARN
        elif filter_result.final_decision == DecisionType.REJECT and config.get("log_reject_to_admin"):
            msg_text = MessageRenderer.render_reject_admin(norm_data, filter_result.decision_reason)
            route_to_send = TelegramRoute.ADMIN

        if not msg_text or not route_to_send:
            return

        route_value = route_to_send.value
        status, response, error_detail = await self.notifier.notify(route_value, msg_text)
        chat_id = self.notifier.resolve_chat_id(route_value) or "N/A"
        status_value = status if isinstance(status, str) else status.value
        sent_at = datetime.now(timezone.utc) if status_value == DeliveryStatus.SENT.value else None

        telegram_message_id = None
        if response:
            telegram_message_id = str(
                response.get("_telegram_message_id") or response.get("result", {}).get("message_id") or ""
            )
            if telegram_message_id == "":
                telegram_message_id = None

        self.telegram_repo.create(
            {
                "signal_row_id": signal_row_id,
                "route": route_value,
                "chat_id": str(chat_id),
                "message_text": msg_text,
                "telegram_message_id": telegram_message_id,
                "delivery_status": status_value,
                "error_log": error_detail,
                "sent_at": sent_at,
            }
        )

    def _accepted_result(self, signal_id: str, decision: DecisionType) -> WebhookServiceResult:
        return WebhookServiceResult(
            status_code=200,
            body=WebhookAcceptedResponse(
                signal_id=signal_id,
                decision=decision,
                timestamp=datetime.now(timezone.utc),
            ),
        )

    def _error_result(self, status_code: int, error: ErrorResponse) -> WebhookServiceResult:
        return WebhookServiceResult(status_code=status_code, body=error, is_error=True)
