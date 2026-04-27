# V1.1 Changelog

**Released:** 2026-04-27

## Added

- **Strategy-specific validation** cho SHORT_SQUEEZE, SHORT_V73, LONG_V73.
  - Hard rules: `SQ_NO_FIRED`, `SQ_BAD_MOM_DIRECTION`, `SQ_BAD_VOL_REGIME`, `SQ_BAD_STRATEGY_NAME`, `S_BASE_BAD_STRATEGY_NAME`, `L_BASE_BAD_STRATEGY_NAME` → FAIL → REJECT.
  - Quality floors: RSI, Stoch, KC position → WARN → PASS_WARNING.
- **Backend rescoring engine** với config-driven bonus/penalty table (`app/services/rescoring_engine.py`).
- **`RR_PROFILE_MATCH` rule** cho target-band RR validation (±10%).
- **Reject code taxonomy** (`app/services/reject_codes.py`): central `RejectCode` enum + `rule_code_to_reject_code()` mapping.
- **`POST /api/v1/signals/{id}/reverify`** endpoint + `signal_reverify_results` table.
- **`GET /api/v1/analytics/reject-stats`** aggregation với `group_by=signal_type,reject_code`.
- Admin reject Telegram messages now include `RejectCode:` line.

## Changed

- **`MIN_RR_REQUIRED`** giữ nguyên lower-bound check (không đổi).
- **`RR_PROFILE_MATCH`** dùng WARN (pilot) thay vì FAIL.
- **`BACKEND_SCORE_THRESHOLD`** dùng WARN MEDIUM (pilot) thay vì FAIL — giữ boolean-gate routing.
- **`FilterEngine.run()`** adds Phase 2.5 (strategy validation) và Phase 3c/3d (rescoring + profile match).
- Default `score_pass_threshold = 75`, `rr_tolerance_pct = 0.10`.

## Unchanged / Deferred

- SOFT_PASS decision type — not in V1.1.
- Position-state risk gate — not in V1.1.
- User profile aggressive/conservative mode — not in V1.1.
- Cooldown-as-reject — still WARN-only.
- SOFT_PASS — not in V1.1.

## Bug Fix

- Fixed `duplicate_price_tolerance_pct` typo in `docs/FILTER_RULES.md:459`: `0.2` → `0.002`.

## Pilot Policy (2 tuần đầu)

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `SQ_NO_FIRED` | HIGH | FAIL | REJECT |
| `SQ_BAD_MOM_DIRECTION` | HIGH | FAIL | REJECT |
| `SQ_BAD_VOL_REGIME` | HIGH | FAIL | REJECT |
| `SQ_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `S_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `L_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| All quality floor WARNs | MEDIUM | WARN | PASS_WARNING |
| `RR_PROFILE_MATCH` | MEDIUM | WARN | PASS_WARNING |
| `BACKEND_SCORE_THRESHOLD` | MEDIUM | WARN | PASS_WARNING |

**Sau 2 tuần:** review `reject-stats` + score distribution → quyết định có tăng threshold hoặc đổi WARN → FAIL.
