# test_commons.py: step 13e slice 6, the shared commons. A collection is stored once, read only; a tenant that links to it
# finds it beside its own knowledge and Ask cites it as Commons with its official source; a tenant that does not link sees
# none; a tenant's forgetting never touches it; on Postgres two tenants read the same single copy.
# Uses: app/pipeline/commons.py, stages_retrieve.py, adapters.py, api/ask.py, tests/test_api.py, test_forget.py.
import uuid

import pytest

from app.pipeline import commons, fakes, orchestrate, stages_retrieve, store_postgres
from app.pipeline.contracts_reason import ContextQuery
from app.pipeline.contracts_signal import Principal
from app.pipeline.store_chunks_pg import PostgresChunks
from tests.golden import NOW, SEED
from tests.test_api import FOUNDER, TENANT, hq  # noqa: F401  (hq links lk_tax_labour, as Finebase HQ does)

# Config
NEEDS_POSTGRES = pytest.mark.skipif(not store_postgres.database_is_up(), reason="no Postgres on localhost:5433")
VAT = "commons_lk_tax_labour_vat_rate"
ASKED = "What is the VAT rate in Sri Lanka?"


def ask(client, question: str = ASKED) -> dict:
    return client.post(f"/api/t/{TENANT}/ask", json={"question": question}, headers={"x-persona": FOUNDER}).json()


def search(lane, question: str = ASKED, shared=None) -> list[str]:
    query = ContextQuery(run_id="r1", principal=Principal(type="human", id=FOUNDER, capabilities=["kb.read"], tier="L1"), on_behalf_of=None,
                         query_text=question, branch="main", top_k=8, max_tokens=4000)
    bundle, _ = stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, NOW,
                                         lane.commons if shared is None else shared)
    return [item.item_id for item in bundle.items]


# --- A collection

def test_a_collection_is_public_about_no_one_and_points_to_its_source():
    items = commons.items_of("lk_tax_labour")
    assert len(items) == 6 and {i["sensitivity"] for i in items} == {"public"} and all(not i["entity_ids"] for i in items)
    assert next(i for i in items if i["item_id"] == VAT)["source"] == {"document_id": "commons:lk_tax_labour", "uri": "https://www.ird.gov.lk"}


# --- Linking

def test_a_linked_tenant_finds_it_and_ask_cites_it_as_commons(hq):
    client, lane, _ = hq
    assert VAT in search(lane)
    cited = {c["id"]: c for c in ask(client)["citations"]}
    assert cited[VAT]["label"].startswith("Commons · Sri Lanka VAT") and cited[VAT]["href"] == "https://www.ird.gov.lk"


def test_a_tenant_that_does_not_link_sees_none():
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)  # the golden seed links nothing
    assert lane.commons == [] and not [item for item in search(lane) if item.startswith("commons_")]


def test_a_tenants_forgetting_never_touches_the_commons(hq):
    _, lane, _ = hq
    before = lane.commons[0].known([VAT])
    for layer_store in ("chunks", "graph", "object_store"):
        assert lane.commons[0] is not getattr(lane, layer_store)  # no forgetting layer can reach it
    assert lane.commons[0].known([VAT]) == before == {VAT}


# --- One copy on Postgres

@NEEDS_POSTGRES
def test_two_tenants_read_the_same_single_copy():
    connection = store_postgres.connect()
    shared = PostgresChunks(connection, f"test_commons_{uuid.uuid4().hex[:8]}")  # stands in for commons:lk_tax_labour
    commons.load(shared, fakes.fake_embed, "lk_tax_labour")
    lanes = [orchestrate.build_lane({**SEED, "tenant_id": f"test_{name}_{uuid.uuid4().hex[:6]}"}, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
             for name in ("first", "second")]
    assert all(VAT in search(lane, shared=[shared]) for lane in lanes)
    stored = connection.execute("SELECT count(*) FROM chunks WHERE tenant_id = %s", (shared.tenant_id,)).fetchone()[0]
    assert stored == 6  # once, however many tenants read it
