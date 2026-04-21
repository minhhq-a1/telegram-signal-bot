from typing import Optional
import secrets
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    @staticmethod
    def validate_secret(secret: Optional[str]) -> bool:
        """
        Xác thực secret key từ payload của TradingView.
        Sử dụng secrets.compare_digest để tránh timing attack.
        """
        if not secret:
            logger.warning("auth_failed_missing_secret")
            return False
            
        is_valid = secrets.compare_digest(secret, settings.tradingview_shared_secret)
        if not is_valid:
            logger.warning("auth_failed_invalid_secret")
            
        return is_valid
