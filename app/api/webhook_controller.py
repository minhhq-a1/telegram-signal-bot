from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.schemas import WebhookAcceptedResponse, ErrorResponse
from app.repositories.webhook_event_repo import WebhookEventRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.filter_result_repo import FilterResultRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.telegram_repo import TelegramRepository
from app.repositories.config_repo import ConfigRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.services.telegram_notifier import TelegramNotifier
from app.services.webhook_ingestion_service import WebhookIngestionService
from app.core.config import settings
from app.api.rate_limiter import limiter

router = APIRouter(tags=["webhooks"])

@router.post(
    "/api/v1/webhooks/tradingview",
    responses={
        200: {"model": WebhookAcceptedResponse, "description": "Signal accepted and processed"},
        400: {"model": ErrorResponse, "description": "Invalid JSON, schema validation error, or invalid secret"},
        409: {"model": ErrorResponse, "description": "Duplicate signal (already processed)"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit(lambda: f"{settings.webhook_rate_limit}/minute")
async def handle_tradingview_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw_body_bytes = await request.body()
    raw_body_text = raw_body_bytes.decode("utf-8", errors="replace")
    service = WebhookIngestionService(
        db=db,
        notifier=TelegramNotifier(),
        webhook_repo_cls=WebhookEventRepository,
        signal_repo_cls=SignalRepository,
        filter_repo_cls=FilterResultRepository,
        decision_repo_cls=DecisionRepository,
        telegram_repo_cls=TelegramRepository,
        config_repo_cls=ConfigRepository,
        market_event_repo_cls=MarketEventRepository,
    )
    result = await service.ingest(
        raw_body_text=raw_body_text,
        source_ip=request.client.host if request.client else None,
        headers=dict(request.headers),
    )

    if result.is_error:
        return JSONResponse(
            status_code=result.status_code,
            content=result.body.model_dump(mode="json"),
        )

    if result.notification_job is not None:
        print(f"DEBUG: notification_job route={result.notification_job.route}, len={len(result.notification_job.message_text)}")
        background_tasks.add_task(service.deliver_notification, result.notification_job)

    return result.body
