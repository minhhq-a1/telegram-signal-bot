-- Migration 003: v1.1 Upgrade — Reverify table + config defaults
-- Created: 2026-04-26

-- 1. Bảng reverify results (non-mutating audit log)
CREATE TABLE IF NOT EXISTS signal_reverify_results (
    id                 VARCHAR(36) PRIMARY KEY,
    signal_row_id      VARCHAR(36) NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    original_decision  VARCHAR(32) NOT NULL,
    reverify_decision  VARCHAR(32) NOT NULL,
    reverify_score     NUMERIC(6,2),
    reject_code        VARCHAR(64),
    decision_reason    TEXT,
    score_items        JSONB,
    filter_results    JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_reverify_signal_row_id
    ON signal_reverify_results(signal_row_id, created_at DESC);

-- 2. Add mom_direction to persisted signals.
-- Pine sends int (-1/0/1); nullable keeps backward compatibility for old rows.
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS mom_direction INTEGER;

-- 3. Seed V1.1 config keys vào DB (deep-merge với existing config)
-- Chỉ thêm keys mới, không ghi đè keys cũ.
-- Split into per-key UPDATEs so that a partial migration (e.g. missing only
-- 'rescoring') gets completed without re-applying already-present keys.
-- This also fixes the prior idempotency gap: checking only 'strategy_thresholds'
-- skipped the entire block if that key existed but 'rescoring' was missing.

-- 3a. rr_tolerance_pct
UPDATE system_configs
SET config_value = config_value || jsonb_build_object('rr_tolerance_pct', 0.10)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'rr_tolerance_pct');

-- 3b. rr_target_by_type
UPDATE system_configs
SET config_value = config_value || jsonb_build_object(
    'rr_target_by_type', jsonb_build_object(
        'SHORT_SQUEEZE', 2.5,
        'SHORT_V73', 1.67,
        'LONG_V73', 1.67
    )
)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'rr_target_by_type');

-- 3c. score_pass_threshold
UPDATE system_configs
SET config_value = config_value || jsonb_build_object('score_pass_threshold', 75)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'score_pass_threshold');

-- 3d. strategy_thresholds
UPDATE system_configs
SET config_value = config_value || jsonb_build_object(
    'strategy_thresholds', jsonb_build_object(
        'SHORT_SQUEEZE', jsonb_build_object(
            'rsi_min', 35, 'rsi_slope_max', -2, 'kc_position_max', 0.55, 'atr_pct_min', 0.20
        ),
        'SHORT_V73', jsonb_build_object('rsi_min', 60, 'stoch_k_min', 70),
        'LONG_V73', jsonb_build_object('rsi_max', 35, 'stoch_k_max', 20)
    )
)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'strategy_thresholds');

-- 3e. rescoring
UPDATE system_configs
SET config_value = config_value || jsonb_build_object(
    'rescoring', jsonb_build_object(
        'SHORT_SQUEEZE', jsonb_build_object(
            'base', 70,
            'bonuses', jsonb_build_object(
                'vol_regime_breakout_imminent', 8, 'regime_weak_trend_down', 6,
                'regime_strong_trend_down', 8, 'mom_direction_neg1', 5,
                'squeeze_bars_ge_4', 3, 'squeeze_bars_ge_6', 5,
                'rsi_ge_40', 4, 'rsi_slope_le_neg4', 4,
                'atr_percentile_ge_70', 3, 'kc_position_le_040', 3, 'confidence_ge_090', 3
            ),
            'penalties', jsonb_build_object(
                'regime_strong_trend_up', -15, 'regime_weak_trend_up', -8,
                'rsi_lt_35', -8, 'atr_pct_lt_020', -8, 'atr_pct_gt_150', -5
            )
        ),
        'SHORT_V73', jsonb_build_object(
            'base', 72,
            'bonuses', jsonb_build_object(
                'rsi_ge_70', 5, 'stoch_ge_85', 5,
                'rsi_slope_le_neg4', 4, 'regime_trend_down', 6, 'confidence_ge_090', 3
            ),
            'penalties', jsonb_build_object(
                'regime_strong_trend_up', -15, 'vol_ranging_high', -6, 'atr_pct_lt_020', -6
            )
        ),
        'LONG_V73', jsonb_build_object(
            'base', 72,
            'bonuses', jsonb_build_object(
                'rsi_le_25', 5, 'stoch_le_10', 5,
                'rsi_slope_ge_2', 4, 'regime_trend_up', 6, 'confidence_ge_090', 3
            ),
            'penalties', jsonb_build_object(
                'regime_strong_trend_down', -15, 'vol_ranging_high', -6, 'atr_pct_lt_020', -6
            )
        )
    )
)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'rescoring');

-- 4. Composite index for analytics reject-stats query.
-- Covers (signal_row_id, result, severity) used in the primary_fail_subq.
CREATE INDEX IF NOT EXISTS idx_signal_filter_result_signal_result_severity
    ON signal_filter_results(signal_row_id, result, severity);
