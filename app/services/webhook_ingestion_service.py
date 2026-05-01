from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, TelegramRoute
from app.core.logging import logger
from app.core.redaction import redact_sensitive_payload
from app.domain.schemas import ErrorResponse, TradingViewWebhookPayload, WebhookAcceptedResponse
from app.repositories.config_repo import ConfigRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.filter_result_repo import FilterResultRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.telegram_repo import TelegramRepository
from app.repositories.webhook_event_repo import WebhookEventRepository
from app.repositories.outcome_repo import OutcomeRepository
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
    notification_job: NotificationJob | None = None


@dataclass
class NotificationJob:
    signal_row_id: str
    route: str
    message_text: str


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
        self.telegram_repo_cls = telegram_repo_cls
        self.telegram_repo = telegram_repo_cls(db)
        self.outcome_repo = OutcomeRepository(db)
        self.config_repo = config_repo_cls(db)
        self.market_repo = market_event_repo_cls(db)
        self.background_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=db.get_bind(),
        )

    async def ingest(self, raw_body_text: str, source_ip: str | None, headers: dict[str, Any]) -> WebhookServiceResult:
        started_at = datetime.now(timezone.utc)
        correlation_id = self._resolve_correlation_id(headers)

        payload_dict = self._parse_json(raw_body_text, source_ip, headers, correlation_id)
        if isinstance(payload_dict, WebhookServiceResult):
            return payload_dict

        payload = self._validate_payload(payload_dict, source_ip, headers, correlation_id)
        if isinstance(payload, WebhookServiceResult):
            return payload

        is_authed = AuthService.validate_secret(payload.secret)
        auth_status = AuthStatus.OK if is_authed else AuthStatus.INVALID_SECRET

        webhook_event = self.webhook_repo.create(
            {
                "correlation_id": correlation_id,
                "source_ip": source_ip,
                "http_headers": redact_sensitive_payload(headers),
                "raw_body": redact_sensitive_payload(payload.model_dump(mode="json")),
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
        norm_data["correlation_id"] = correlation_id

        try:
            with self.db.begin_nested():
                signal_obj = self.signal_repo.create(norm_data)
        except IntegrityError as exc:
            existing_signal = self.signal_repo.find_by_signal_id(payload.signal_id)
            if existing_signal is None:
                raise exc

            logger.warning(
                "signal_insert_race_detected",
                extra={
                    "signal_id": payload.signal_id,
                    "existing_row_id": existing_signal.id,
                    "correlation_id": correlation_id,
                },
            )
            self.db.commit()
            return self._accepted_result(payload.signal_id, DecisionType.DUPLICATE)

        config = self.config_repo.get_signal_bot_config()
        config_version = 1
        get_with_version = getattr(self.config_repo, "get_signal_bot_config_with_version", None)
        if callable(get_with_version):
            try:
                _config_with_version, config_version = get_with_version()
                # Preserve monkeypatched get_signal_bot_config() behavior in tests/callers
                # while still recording version when available from the repository.
            except Exception:
                config_version = 1
        engine = FilterEngine(config, self.signal_repo, self.market_repo)
        filter_result = engine.run(norm_data)

        signal_obj.server_score = filter_result.server_score
        signal_obj.config_version = config_version

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

        if config.get("auto_create_open_outcomes") and filter_result.final_decision in (
            DecisionType.PASS_MAIN,
            DecisionType.PASS_WARNING,
        ):
            self.outcome_repo.create_open_from_signal(signal_obj)

        notification_job = self._build_notification_job(norm_data, signal_obj.id, filter_result, config)
        self.db.commit()
        self._log_pipeline_summary(
            correlation_id=correlation_id,
            signal_id=payload.signal_id,
            filter_result=filter_result,
            started_at=started_at,
            notification_enqueued=notification_job is not None,
        )
        return self._accepted_result(payload.signal_id, filter_result.final_decision, notification_job)

    def _parse_json(
        self,
        raw_body_text: str,
        source_ip: str | None,
        headers: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any] | WebhookServiceResult:
        try:
            return json.loads(raw_body_text)
        except json.JSONDecodeError:
            self.webhook_repo.create(
                {
                    "correlation_id": correlation_id,
                    "source_ip": source_ip,
                    "http_headers": redact_sensitive_payload(headers),
                    "raw_body": {"_raw_body_text": "***REDACTED***"},
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
        correlation_id: str,
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
                    "correlation_id": correlation_id,
                    "source_ip": source_ip,
                    "http_headers": redact_sensitive_payload(headers),
                    "raw_body": redact_sensitive_payload(payload_dict) if isinstance(payload_dict, dict) else {"payload": "***REDACTED***"},
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

    def _resolve_correlation_id(self, headers: dict[str, Any]) -> str:
        for key, value in headers.items():
            if str(key).lower() != "x-correlation-id":
                continue
            correlation_id = str(value).strip()
            if correlation_id and len(correlation_id) <= 64:
                return correlation_id
            break
        return str(uuid.uuid4())

    def _log_pipeline_summary(
        self,
        correlation_id: str,
        signal_id: str,
        filter_result: Any,
        started_at: datetime,
        notification_enqueued: bool,
    ) -> None:
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        failed_rules = [
            result.rule_code
            for result in filter_result.filter_results
            if result.result.value == "FAIL"
        ]
        warn_rules = [
            result.rule_code
            for result in filter_result.filter_results
            if result.result.value == "WARN"
        ]
        logger.info(
            "webhook_pipeline_completed",
            extra={
                "event": "webhook_pipeline_completed",
                "correlation_id": correlation_id,
                "signal_id": signal_id,
                "decision": filter_result.final_decision.value,
                "route": filter_result.route.value,
                "failed_rules": failed_rules,
                "warn_rules": warn_rules,
                "duration_ms": duration_ms,
                "notification_enqueued": notification_enqueued,
            },
        )

    def _build_notification_job(
        self,
        norm_data: dict[str, Any],
        signal_row_id: str,
        filter_result: Any,
        config: dict[str, Any],
    ) -> NotificationJob | None:
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
            from app.services.reject_codes import rule_code_to_reject_code

            first_fail = next(
                (r for r in filter_result.filter_results if r.result.value == "FAIL"),
                None,
            )
            reject_code = rule_code_to_reject_code(first_fail.rule_code) if first_fail else None
            msg_text = MessageRenderer.render_reject_admin(
                norm_data, filter_result.decision_reason, reject_code=reject_code
            )
            route_to_send = TelegramRoute.ADMIN

        if not msg_text or not route_to_send:
            return None

        return NotificationJob(
            signal_row_id=signal_row_id,
            route=route_to_send.value,
            message_text=msg_text,
        )

    async def deliver_notification(self, notification_job: NotificationJob) -> None:
        status: str | None = None
        response: dict | None = None
        error_detail: str | None = None

        try:
            status, response, error_detail = await self.notifier.notify(
                notification_job.route,
                notification_job.message_text,
            )
        except Exception as e:
            # Always log to audit even if Telegram call fails.
            # Set FAILED status so the row satisfies the DB constraint.
            error_detail = f"{type(e).__name__}: {e}"
            status = DeliveryStatus.FAILED.value
            logger.warning(
                "telegram_notify_raised",
                extra={"signal_row_id": notification_job.signal_row_id, "error": str(e)},
            )

        db = self.background_session_factory()
        try:
            telegram_repo = self.telegram_repo_cls(db)
            chat_id = self.notifier.resolve_chat_id(notification_job.route) or "N/A"
            status_value: str = status if isinstance(status, str) else (
                status.value if status else DeliveryStatus.FAILED.value
            )
            sent_at = datetime.now(timezone.utc) if status_value == DeliveryStatus.SENT.value else None

            telegram_message_id = None
            if response:
                telegram_message_id = str(
                    response.get("_telegram_message_id")
                    or response.get("result", {}).get("message_id")
                    or ""
                )
                if telegram_message_id == "":
                    telegram_message_id = None

            telegram_repo.create(
                {
                    "signal_row_id": notification_job.signal_row_id,
                    "route": notification_job.route,
                    "chat_id": str(chat_id),
                    "message_text": notification_job.message_text,
                    "telegram_message_id": telegram_message_id,
                    "delivery_status": status_value,
                    "error_log": error_detail,
                    "sent_at": sent_at,
                }
            )
            db.commit()
            logger.info(
                "telegram_message_log_created",
                extra={"signal_row_id": notification_job.signal_row_id, "status": status_value},
            )
        except Exception:
            db.rollback()
            logger.exception(
                "telegram_delivery_log_failed",
                extra={"signal_row_id": notification_job.signal_row_id, "route": notification_job.route},
            )
        finally:
            db.close()

    def _accepted_result(
        self,
        signal_id: str,
        decision: DecisionType,
        notification_job: NotificationJob | None = None,
    ) -> WebhookServiceResult:
        return WebhookServiceResult(
            status_code=200,
            body=WebhookAcceptedResponse(
                signal_id=signal_id,
                decision=decision,
                timestamp=datetime.now(timezone.utc),
            ),
            notification_job=notification_job,
        )

    def _error_result(self, status_code: int, error: ErrorResponse) -> WebhookServiceResult:
        return WebhookServiceResult(status_code=status_code, body=error, is_error=True)
