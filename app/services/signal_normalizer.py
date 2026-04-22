from app.domain.schemas import TradingViewWebhookPayload


class SignalNormalizer:
    @staticmethod
    def normalize(webhook_event_id: str, payload: TradingViewWebhookPayload) -> dict:
        """
        Chuẩn hóa payload đầu vào thành dictionary tương thích với SignalRepository.create()
        Đồng thời tính toán Risk/Reward ratio.
        """
        side = "LONG" if payload.signal.lower() == "long" else "SHORT"
        
        # Risk / Reward Calculation
        risk_reward = None
        m = payload.metadata
        if m:
            entry = m.entry
            tp = m.take_profit
            sl = m.stop_loss
            
            if side == "LONG":
                risk = entry - sl
                reward = tp - entry
            else:  # SHORT
                risk = sl - entry
                reward = entry - tp
                
            if risk > 0:
                risk_reward = round(reward / risk, 4)

        # Convert to raw dictionary
        raw_payload = payload.model_dump(mode="json")
        
        return {
            "webhook_event_id": webhook_event_id,
            "signal_id": payload.signal_id,
            "source": payload.source,
            "symbol": payload.symbol,
            "chart_symbol": payload.chart_symbol,
            "exchange": payload.exchange,
            "market_type": payload.market_type,
            "timeframe": payload.timeframe,
            "side": side,
            "price": payload.price,
            "entry_price": m.entry if m else None,
            "take_profit": m.take_profit if m else None,
            "stop_loss": m.stop_loss if m else None,
            "risk_reward": risk_reward,
            "indicator_confidence": payload.confidence,
            "raw_payload": raw_payload,
            
            # Metadata fields
            "signal_type": payload.metadata.signal_type if payload.metadata else None,
            "strategy": payload.metadata.strategy if payload.metadata else None,
            "regime": payload.metadata.regime if payload.metadata else None,
            "vol_regime": payload.metadata.vol_regime if payload.metadata else None,
            
            # Indicators
            "atr": payload.metadata.atr if payload.metadata else None,
            "atr_pct": payload.metadata.atr_pct if payload.metadata else None,
            "adx": payload.metadata.adx if payload.metadata else None,
            "rsi": payload.metadata.rsi if payload.metadata else None,
            "rsi_slope": payload.metadata.rsi_slope if payload.metadata else None,
            "stoch_k": payload.metadata.stoch_k if payload.metadata else None,
            "macd_hist": payload.metadata.macd_hist if payload.metadata else None,
            "kc_position": payload.metadata.kc_position if payload.metadata else None,
            "atr_percentile": payload.metadata.atr_percentile if payload.metadata else None,
            "vol_ratio": payload.metadata.vol_ratio if payload.metadata else None,
            
            # Squeeze indicators
            "squeeze_on": payload.metadata.squeeze_on if payload.metadata else None,
            "squeeze_fired": payload.metadata.squeeze_fired if payload.metadata else None,
            "squeeze_bars": payload.metadata.squeeze_bars if payload.metadata else None,
            
            # Timestamps
            "payload_timestamp": payload.timestamp,
            "bar_time": payload.bar_time,
        }
