-- Migration 005: Repair V1.1 config idempotency after immutable 003 restore.
--
-- Migration 003 was already applied in production, so its checksum must remain
-- immutable. This migration carries forward the per-key idempotent config repair
-- that was briefly introduced by editing 003.

-- rr_tolerance_pct
UPDATE system_configs
SET config_value = config_value || jsonb_build_object('rr_tolerance_pct', 0.10)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'rr_tolerance_pct');

-- rr_target_by_type
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

-- score_pass_threshold
UPDATE system_configs
SET config_value = config_value || jsonb_build_object('score_pass_threshold', 75)
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'score_pass_threshold');

-- strategy_thresholds
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

-- rescoring
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
