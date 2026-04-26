from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone, timedelta

class MessageRenderer:
    _FOOTER = "Powered by Telegram Signal Bot V1"

    @staticmethod
    def _format_number(num) -> str:
        """Format price với 2 decimals và thousand separator."""
        if num is None:
            return "N/A"
        if isinstance(num, (int, float)):
             return f"{num:,.2f}"
        return "N/A"
        
    @staticmethod
    def _format_conf(conf) -> str:
        if conf is None:
             return "N/A"
        if isinstance(conf, (int, float)):
             return f"{round(conf * 100)}%"
        return "N/A"

    @staticmethod
    def _get_time_str(signal: dict) -> str:
        # Timezone ICT (UTC+7)
        # Using server time or payload time if bar_time or payload_timestamp is unavailable, we use current time.
        # But `bar_time` or `payload_timestamp` if they are datetime objects, they should be UTC.
        # We'll use datetime.now(timezone.utc) as a fallback
        dt = signal.get("bar_time") or signal.get("payload_timestamp") or datetime.now(timezone.utc)
        if isinstance(dt, datetime):
            ict_dt = dt + timedelta(hours=7)
            return ict_dt.strftime("%H:%M ICT")
        return "N/A"

    @staticmethod
    def _append_footer(text: str) -> str:
        return f"{text}\n\n{MessageRenderer._FOOTER}"

    @staticmethod
    def render_main(signal: dict, score: float) -> str:
        side = signal.get("side", "").upper()
        symbol = signal.get("symbol", "UNKNOWN")
        tf = signal.get("timeframe", "UNKNOWN")
        icon = "🟢" if side == "LONG" else "🔴"

        entry = MessageRenderer._format_number(signal.get("entry_price"))
        sl = MessageRenderer._format_number(signal.get("stop_loss"))
        tp = MessageRenderer._format_number(signal.get("take_profit"))
        rr = signal.get("risk_reward")
        rr_str = f"{rr:.2f}" if isinstance(rr, (int, float)) else "N/A"
        
        conf = MessageRenderer._format_conf(signal.get("indicator_confidence"))
        score_str = MessageRenderer._format_conf(score)

        typ = signal.get("signal_type", "N/A") or "N/A"
        trend = signal.get("regime", "N/A") or "N/A"
        vol = signal.get("vol_regime", "N/A") or "N/A"

        rsi = signal.get("rsi")
        rsi_str = f"{rsi:.1f}" if isinstance(rsi, (int, float)) else "N/A"
        slope = signal.get("rsi_slope")
        slope_str = f"{slope:.1f}" if isinstance(slope, (int, float)) else "N/A"
        stoch = signal.get("stoch_k")
        stoch_str = f"{stoch:.1f}" if isinstance(stoch, (int, float)) else "N/A"
        adx = signal.get("adx")
        adx_str = f"{adx:.1f}" if isinstance(adx, (int, float)) else "N/A"
        atr_pct = signal.get("atr_pct")
        atr_str = f"{atr_pct:.3f}" if isinstance(atr_pct, (int, float)) else "N/A"
        
        time_str = MessageRenderer._get_time_str(signal)
        source = signal.get("source", "N/A")

        return MessageRenderer._append_footer(f"""{icon} {symbol} {side} | {tf}
Entry: {entry}
SL: {sl}
TP: {tp}
RR: {rr_str}
Conf: {conf} | Score: {score_str}

Type: {typ}
Trend: {trend}
Vol: {vol}

RSI: {rsi_str} | Slope: {slope_str}
StochK: {stoch_str} | ADX: {adx_str}
ATR%: {atr_str}

Status: PASSED ✅
Time: {time_str}
Source: {source}""")

    @staticmethod
    def render_warning(signal: dict, score: float, reason: str) -> str:
        side = signal.get("side", "").upper()
        symbol = signal.get("symbol", "UNKNOWN")
        tf = signal.get("timeframe", "UNKNOWN")
        signal_id = signal.get("signal_id", "UNKNOWN")

        rr = signal.get("risk_reward")
        rr_str = f"{rr:.2f}" if isinstance(rr, (int, float)) else "N/A"
        conf = MessageRenderer._format_conf(signal.get("indicator_confidence"))
        score_str = MessageRenderer._format_conf(score)
        
        trend = signal.get("regime", "N/A") or "N/A"
        vol = signal.get("vol_regime", "N/A") or "N/A"

        return MessageRenderer._append_footer(f"""🟡 WARNING | {symbol} {side} | {tf}
Reason: {reason}
Conf: {conf} | Score: {score_str}
RR: {rr_str}
Trend: {trend}
Vol: {vol}
Signal ID: {signal_id}""")

    @staticmethod
    def render_reject_admin(
        signal: dict, reason: str, reject_code: str | None = None
    ) -> str:
        side = signal.get("side", "").upper()
        symbol = signal.get("symbol", "UNKNOWN")
        tf = signal.get("timeframe", "UNKNOWN")
        signal_id = signal.get("signal_id", "UNKNOWN")
        code_line = f"\nRejectCode: {reject_code}" if reject_code else ""

        return MessageRenderer._append_footer(f"""⛔ REJECTED | {symbol} {side} | {tf}{code_line}
Reason: {reason}
Signal ID: {signal_id}""")
