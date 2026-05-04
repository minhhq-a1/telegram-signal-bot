import pytest
from sqlalchemy import select, update, insert
from app.domain.models import Signal, SignalDecision, SignalFilterResult

pytestmark = pytest.mark.integration


def _seed_reject(db_session, sig, rule_code, severity="HIGH"):
    """Mark a signal as REJECT with one FAIL filter result."""
    import uuid
    db_session.execute(
        update(SignalDecision)
        .where(SignalDecision.signal_row_id == sig.id)
        .values(decision="REJECT", decision_reason=rule_code)
    )
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code=rule_code,
        rule_group="test",
        result="FAIL",
        severity=severity,
        score_delta=0.0,
        details={"reject_code": rule_code},
    ))
    db_session.commit()


def _seed_fail_rule(db_session, sig, rule_code, severity="HIGH"):
    """Add an extra FAIL filter result to an already-rejected signal."""
    import uuid
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code=rule_code,
        rule_group="test",
        result="FAIL",
        severity=severity,
        score_delta=0.0,
        details={"reject_code": rule_code},
    ))
    db_session.commit()


class TestRejectStatsEndpoint:
    def test_reject_stats_groups_by_signal_type_and_code(self, client, db_session, make_stored_signal):
        """Buckets correctly aggregate by signal_type + reject_code."""
        for _ in range(2):
            sig = make_stored_signal(signal_type="SHORT_SQUEEZE")
            _seed_reject(db_session, sig, "SQ_NO_FIRED")

        sig = make_stored_signal(signal_type="LONG_V73")
        _seed_reject(db_session, sig, "BACKEND_SCORE_THRESHOLD")

        resp = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code", headers={"Authorization": "Bearer test-dash-token"})
        assert resp.status_code == 200
        body = resp.json()
        buckets = {(b["signal_type"], b["reject_code"]): b["count"] for b in body["buckets"]}
        assert buckets[("SHORT_SQUEEZE", "SQ_NO_FIRED")] == 2
        assert buckets[("LONG_V73", "BACKEND_SCORE_TOO_LOW")] == 1

    def test_reject_stats_counts_one_primary_per_signal(self, client, db_session, make_stored_signal):
        """
        A signal with multiple FAIL rules is counted only once, under its
        primary (earliest created_at → earliest id) FAIL rule.

        Regression test for Finding #1: deterministic tie-breaking.
        """
        sig = make_stored_signal(signal_type="SHORT_SQUEEZE")
        _seed_reject(db_session, sig, "SQ_NO_FIRED")
        _seed_fail_rule(db_session, sig, "SQ_BAD_VOL_REGIME")
        _seed_fail_rule(db_session, sig, "SQ_BAD_MOM_DIRECTION")

        resp = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code", headers={"Authorization": "Bearer test-dash-token"})
        assert resp.status_code == 200
        body = resp.json()
        buckets = {(b["signal_type"], b["reject_code"]): b["count"] for b in body["buckets"]}
        assert buckets[("SHORT_SQUEEZE", "SQ_NO_FIRED")] == 1
        # The other FAILs must NOT appear as separate buckets
        assert ("SHORT_SQUEEZE", "SQ_BAD_VOL_REGIME") not in buckets
        assert ("SHORT_SQUEEZE", "SQ_BAD_MOM_DIRECTION") not in buckets

    def test_reject_stats_deterministic_same_severity(self, client, db_session, make_stored_signal):
        """
        When two FAILs share the same severity (e.g., both HIGH), the
        tie-breaker (created_at ASC → id ASC) always picks the same primary.
        Run the query twice and verify stable output.
        """
        sig = make_stored_signal(signal_type="SHORT_SQUEEZE")
        _seed_reject(db_session, sig, "SQ_NO_FIRED", severity="HIGH")
        _seed_fail_rule(db_session, sig, "SQ_BAD_MOM_DIRECTION", severity="HIGH")

        resp1 = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code", headers={"Authorization": "Bearer test-dash-token"})
        resp2 = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code", headers={"Authorization": "Bearer test-dash-token"})

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Stable bucket assignment across two identical queries
        assert resp1.json()["buckets"] == resp2.json()["buckets"]

    def test_reject_stats_fallback_total_rejects(self, client, db_session, make_stored_signal):
        """Without group_by, returns total reject count."""
        for _ in range(3):
            sig = make_stored_signal()
            _seed_reject(db_session, sig, "MIN_RR_REQUIRED")

        resp = client.get("/api/v1/analytics/reject-stats", headers={"Authorization": "Bearer test-dash-token"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rejects"] == 3
        assert body["buckets"] == []
