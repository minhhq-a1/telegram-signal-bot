from enum import Enum

class SignalSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class DecisionType(str, Enum):
    PENDING = "PENDING"
    PASS_MAIN = "PASS_MAIN"
    PASS_WARNING = "PASS_WARNING"
    REJECT = "REJECT"
    DUPLICATE = "DUPLICATE"

class TelegramRoute(str, Enum):
    MAIN = "MAIN"
    WARN = "WARN"
    ADMIN = "ADMIN"
    NONE = "NONE"

class RuleResult(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

class RuleSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class AuthStatus(str, Enum):
    OK = "OK"
    INVALID_SECRET = "INVALID_SECRET"
    MISSING = "MISSING"
