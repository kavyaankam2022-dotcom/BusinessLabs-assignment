from datetime import datetime, timedelta, timezone

from app.schemas import EscalationCreate, EscalationResolve, ExpertKnowledgeRevision
from app.store import KnowledgeStore


class FixedEmbedder:
    def encode(self, text):
        return [1.0, 0.0]


def test_escalation_creates_pending_evaluation_case_and_scoped_answer(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    store.initialize()
    escalation_id = store.create_escalation(EscalationCreate(
        question="How do I reset the account password?",
        reason="No documentation matched the question.",
        customer_id="customer-42",
        evidence=[{"url": "https://example.test/help", "excerpt": "No matching procedure."}],
    ))

    cases = store.evaluation_cases()
    version = store.resolve_escalation(
        escalation_id,
        EscalationResolve(
            answer="Use the account recovery screen.",
            reviewed_by="support-lead",
            applicability="customer_specific",
            customer_id="customer-42",
            supporting_evidence=[{"excerpt": "Confirmed for this customer's account."}],
        ),
        [1.0, 0.0],
    )

    assert cases[0]["question"] == "How do I reset the account password?"
    assert cases[0]["status"] == "pending"
    assert version == 1
    assert store.search("reset password", FixedEmbedder(), 5) == []
    scoped = store.search("reset password", FixedEmbedder(), 5, "customer-42")
    assert len(scoped) == 1
    assert "Use the account recovery screen" in scoped[0]["excerpt"]


def test_expert_answer_revisions_preserve_versions_and_replace_active_record(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    store.initialize()
    escalation_id = store.create_escalation(EscalationCreate(
        question="Which recovery page applies?",
        reason="Needs product expert review.",
    ))
    knowledge_id = f"expert-{escalation_id}"
    store.resolve_escalation(
        escalation_id,
        EscalationResolve(
            answer="Use the legacy recovery page.",
            reviewed_by="reviewer-one",
            applicability="general",
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        ),
        [1.0, 0.0],
    )

    revision = store.revise_expert_knowledge(
        knowledge_id,
        ExpertKnowledgeRevision(
            answer="Use the current recovery page.",
            reviewed_by="reviewer-two",
            applicability="general",
        ),
        [1.0, 0.0],
    )

    versions = store.expert_knowledge_versions(knowledge_id)
    assert revision == 2
    assert [item["version"] for item in versions] == [1, 2]
    assert [item["active"] for item in versions] == [0, 1]
    current = store.search("recovery page", FixedEmbedder(), 5)
    assert len(current) == 1
    assert "current recovery page" in current[0]["excerpt"]


def test_expired_expert_answer_is_not_retrieved(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    store.initialize()
    escalation_id = store.create_escalation(EscalationCreate(
        question="Can this customer use feature X?",
        reason="Account-specific entitlement is not documented.",
        customer_id="customer-7",
    ))
    store.resolve_escalation(
        escalation_id,
        EscalationResolve(
            answer="Feature X is enabled for this account.",
            reviewed_by="reviewer",
            applicability="customer_specific",
            customer_id="customer-7",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ),
        [1.0, 0.0],
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE chunks SET expires_at=? WHERE source_type='expert'",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),),
        )

    assert store.search("feature X account", FixedEmbedder(), 5, "customer-7") == []


def test_ingestion_report_is_persisted_in_status(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    store.initialize()
    run_id = store.start_ingestion_run("daily")
    report = {"added": 2, "updated": 1, "removed": 3, "unchanged": 8, "failed": 1}

    store.finish_ingestion_run(run_id, "completed", report=report)

    latest = store.ingestion_status()["recent_runs"][0]
    assert latest["id"] == run_id
    assert latest["trigger"] == "daily"
    assert latest["report"] == report


def test_evaluation_case_review_records_actual_result(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    store.initialize()
    escalation_id = store.create_escalation(EscalationCreate(
        question="Does the dashboard support CSV export?",
        reason="No supporting documentation was retrieved.",
    ))

    assert store.mark_evaluation_case(
        escalation_id,
        {"status": "insufficient_evidence", "sources": []},
        True,
        "evaluator",
    )
    reviewed = store.evaluation_cases(status="reviewed")
    assert reviewed[0]["actual_result"]["status"] == "insufficient_evidence"
    assert reviewed[0]["passed"] == 1
    assert reviewed[0]["reviewed_by"] == "evaluator"