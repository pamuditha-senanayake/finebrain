# test_stages.py: one contract test per Lane A stage, fed from the golden refund runs s2 and s3.
# Uses: app/pipeline/stages_*.py, app/pipeline/fakes.py, tests/golden.py.
import pytest

from app.pipeline import fakes, stages_govern, stages_intake, stages_normalize, stages_reason, stages_record, stages_retrieve, stages_route
from app.pipeline.contracts_reason import ContextBundle, ContextQuery, ProposedAction
from app.pipeline.contracts_run import GovernanceVerdict, RunRecord
from app.pipeline.adapters import seeded
from app.pipeline.contracts_signal import Principal, TaskRequest
from app.pipeline.store_chunks import MemoryChunks
from app.pipeline.store_graph import MemoryGraph
from tests.golden import NOW, SEED, golden, raw_sample, recorded_answer

# Config
AGENT = Principal.model_validate(SEED["agents"]["agent_refund_worker"])
ROUTING = stages_route.read_routing(seeded(MemoryGraph(SEED["tenant_id"]), SEED))
PERSONAL_VALUES = {
    "s2": ["Nimal Perera", "nimal.perera@example.lk", "+94 77 123 4567"],
    "s3": ["Dilani Fernando", "dilani.f@example.lk", "199012345678", "+94 71 987 6543"],
}


# --- Helpers

def retrieve(query: ContextQuery, knowledge: list[dict]):
    """S5 over these knowledge items, with fake embeddings and rerank."""
    chunks = MemoryChunks()
    for item, vector in zip(knowledge, fakes.fake_embed([item["text"] for item in knowledge])):
        chunks.add(item, vector)
    return stages_retrieve.retrieve(query, chunks, fakes.fake_embed, fakes.fake_rerank, SEED["people"], fakes.make_id_maker(), NOW)


def run_intake(key: str, seen: set[str] | None = None):
    """S1 then S2 on one raw sample. Returns the store, the vault and the signal."""
    store, vault = {}, {}
    k1 = stages_intake.capture(raw_sample(key), SEED["tenant_id"], store, NOW)
    signal = stages_normalize.normalize(k1, "evt_raw", SEED["tenant_id"], store, vault, seen if seen is not None else set(), fakes.make_id_maker())
    return store, vault, signal


def run_govern(run_key: str, principal: Principal = AGENT, citations: list[str] | None = None):
    """S7 on golden K3, K4 bundle and K5 inputs."""
    action = ProposedAction.model_validate(golden(run_key, "ProposedAction"))
    if citations is not None:
        action = action.model_copy(update={"citations": citations})
    return stages_govern.govern(
        TaskRequest.model_validate(golden(run_key, "TaskRequest")), action,
        ContextBundle.model_validate(golden(run_key, "ContextBundle")), principal,
        SEED["refund_policy"], SEED["payments"], SEED["cluster_id"], NOW, fakes.make_id_maker(),
    )


# --- S1 and S2

@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s1_capture_matches_golden(run_key):
    store = {}
    k1 = stages_intake.capture(raw_sample(run_key), SEED["tenant_id"], store, NOW)
    expected = golden(run_key, "RawSignalEnvelope")
    assert (k1.raw_sha256, k1.size_bytes, k1.raw_object_uri) == (expected["raw_sha256"], expected["size_bytes"], expected["raw_object_uri"])
    assert k1.headers_subset == expected["headers_subset"]
    assert store[k1.raw_object_uri] == raw_sample(run_key)["raw_body"].encode()


def test_s1_bad_signature_stores_nothing():
    store = {}
    with pytest.raises(stages_intake.CaptureRejected):
        stages_intake.capture({**raw_sample("s2"), "signature_ok": False}, SEED["tenant_id"], store, NOW)
    assert store == {}


@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s2_masks_personal_data(run_key):
    _, vault, signal = run_intake(run_key)
    expected = golden(run_key, "Signal")
    assert not [value for value in PERSONAL_VALUES[run_key] if value in signal.text_masked]
    assert set(vault.values()) == set(PERSONAL_VALUES[run_key])
    assert len(signal.pii_tokens) == len(expected["pii_tokens"])
    assert (signal.subject.model_dump(), signal.sensitivity, signal.dedup_key) == (expected["subject"], expected["sensitivity"], expected["dedup_key"])
    assert {(e.type, e.value_or_token) for e in signal.entities} == {(e["type"], e["value_or_token"]) for e in expected["entities"]}


def test_s2_drops_redelivery():
    seen: set[str] = set()
    run_intake("s2", seen)
    _, _, duplicate = run_intake("s5", seen)
    assert duplicate is None


# --- S3, S5 and S6

@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s3_routes_refunds(run_key):
    _, _, signal = run_intake(run_key)
    task, _ = stages_route.route(signal, ROUTING, None, fakes.make_id_maker(), NOW)
    expected = golden(run_key, "TaskRequest")
    assert (task.activity_id, task.agent_id, task.base_criticality) == (expected["activity_id"], expected["agent_id"], expected["base_criticality"])
    assert task.skill_ref.model_dump() == expected["skill_ref"]


def test_s3_leaves_invoice_chat_unrouted():
    _, _, signal = run_intake("s4")
    assert stages_route.route(signal, ROUTING, None, fakes.make_id_maker(), NOW) == (None, "below_threshold")


@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s5_bundle_holds_what_s6_cites(run_key):
    query = ContextQuery.model_validate(golden(run_key, "ContextQuery"))
    bundle, _ = retrieve(query, SEED["knowledge"])
    item_ids = {item.item_id for item in bundle.items}
    assert set(golden(run_key, "ProposedAction")["citations"]) <= item_ids
    assert len([item_id for item_id in item_ids if item_id.startswith("item_payment")]) == 1


def test_s5_counts_restricted_items_as_denied():
    query = ContextQuery.model_validate(golden("s2", "ContextQuery"))
    current = next(item for item in SEED["knowledge"] if item["item_id"] == "item_policy_window")
    secret = {**current, "item_id": "item_secret", "sensitivity": "restricted"}
    bundle, _ = retrieve(query, SEED["knowledge"] + [secret])
    assert bundle.denied_count == 1 and "item_secret" not in {item.item_id for item in bundle.items}


@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s6_wraps_the_model_answer(run_key):
    expected = golden(run_key, "ProposedAction")
    call, calls = fakes.make_recorded_caller({expected["arguments"]["payment_ref"]: recorded_answer(run_key)})
    bundle = ContextBundle.model_validate(golden(run_key, "ContextBundle"))
    task, request = TaskRequest.model_validate(golden(run_key, "TaskRequest")), golden(run_key, "Signal")["text_masked"]
    action = stages_reason.propose(task, bundle, request, SEED["skills"][0], call, expected["run_id"], expected["step_id"], SEED["cluster_id"])
    assert action.model_dump(mode="json") == expected
    prompt = calls[0]["messages"][0]["content"]
    assert len(calls) == 1 and all(f'id="{item.item_id}"' in prompt for item in bundle.items)


# --- S7 and S8

@pytest.mark.parametrize("run_key", ["s2", "s3"])
def test_s7_verdict_matches_golden(run_key):
    _, decision, verdict = run_govern(run_key)
    expected = golden(run_key, "GovernanceVerdict")
    assert decision.decision == "allow"
    assert (verdict.criticality, verdict.criticality_reasons, verdict.route) == (expected["criticality"], expected["criticality_reasons"], expected["route"])
    assert [result.passed for result in verdict.policy_results] == [result["passed"] for result in expected["policy_results"]]
    assert (verdict.required_approvers.model_dump() if verdict.required_approvers else None) == expected["required_approvers"]


def test_s7_blocks_without_capability():
    _, decision, verdict = run_govern("s2", principal=AGENT.model_copy(update={"capabilities": ["kb.read"]}))
    assert (decision.decision, verdict.route) == ("deny", "block")


def test_s7_escalates_when_a_citation_is_made_up():
    _, _, verdict = run_govern("s2", citations=["item_made_up"])
    assert verdict.route == "escalate"


def test_s8_opens_one_approval_for_s3():
    _, _, verdict = run_govern("s3")
    approval = stages_govern.request_approval(ProposedAction.model_validate(golden("s3", "ProposedAction")), verdict, fakes.make_id_maker(), NOW)
    expected = golden("s3", "ApprovalRequest")
    assert (approval.criticality, approval.dri_id, approval.evidence_refs) == (expected["criticality"], expected["dri_id"], expected["evidence_refs"])
    assert approval.expires_at > approval.due_at


# --- S9 and S10

def test_s9_pays_once_on_retry():
    gateway, seen = fakes.make_fake_gateway()
    action = ProposedAction.model_validate(golden("s2", "ProposedAction"))
    verdict = GovernanceVerdict.model_validate(golden("s2", "GovernanceVerdict"))
    first, second = (stages_record.act(action, verdict, None, SEED["tenant_id"], gateway, fakes.make_id_maker(), NOW) for _ in range(2))
    assert first.status == "succeeded" and first.external_ref == second.external_ref and len(seen) == 1
    assert first.idempotency_key == golden("s2", "ActionResult")["idempotency_key"]


def test_s9_refuses_an_unapproved_action():
    gateway, seen = fakes.make_fake_gateway()
    with pytest.raises(stages_record.NotCleared):
        stages_record.act(ProposedAction.model_validate(golden("s3", "ProposedAction")), GovernanceVerdict.model_validate(golden("s3", "GovernanceVerdict")), None, SEED["tenant_id"], gateway, fakes.make_id_maker(), NOW)
    assert seen == {}


@pytest.mark.parametrize("run_key, approval_id", [("s2", None), ("s3", "apr_s3_0001")])
def test_s10_closes_the_run(run_key, approval_id):
    expected = golden(run_key, "RunRecord")
    steps = RunRecord.model_validate(expected).steps
    run, event = stages_record.record(TaskRequest.model_validate(golden(run_key, "TaskRequest")), ProposedAction.model_validate(golden(run_key, "ProposedAction")), steps, expected["outcome"], approval_id, SEED, NOW, NOW)
    assert (run.outcome, run.cost.model_dump(), run.human_touch) == (expected["outcome"], expected["cost"], expected["human_touch"])
    assert (event.type, event.id) == (golden(run_key, "UiEvent")["type"], golden(run_key, "UiEvent")["id"])
