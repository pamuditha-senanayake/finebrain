# seed_memory.py: gives a live workspace twelve weeks of realistic living memory, so the page and the drift checks have
# history to work on. Steady work in every area; refunds whose usual path loses its share in the latest week (skill drift);
# refunds made by hand past the window spiking (policy drift); a few new ways of working still waiting for a person. Each
# trace is triaged as the consumer does, then the drift night runs. The workspace's own night (the Distiller, or Run now)
# then sends each drift's fix to an L1 user. Safe to run twice: traces and counts are kept once.
# Run from backend/:  uv run python scripts/seed_memory.py --tenant <tenant_id>   (needs Postgres)
#   or              HQ_TENANT_FILE=hq_tenant.json uv run python scripts/seed_memory.py --hq   (the Finebase HQ workspace itself)
# Uses: stages_memory.py, stages_memory_drift.py, store_traces.py, store_patterns.py, store_drift.py, store_graph.py, store_postgres.py, api/hq.py (load_hq).
import random
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, ".")
from app.api.hq import load_hq
from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_drift as drift
from app.pipeline import stages_memory_flow as flow
from app.pipeline import store_postgres
from app.pipeline.contracts_memory import TraceRecord
from app.pipeline.contracts_signal import VersionRef
from app.pipeline.stages_learn import week_of, zone_of
from app.pipeline.store_drift import PostgresDrift
from app.pipeline.store_graph import PostgresGraph
from app.pipeline.store_patterns import PostgresPatterns
from app.pipeline.store_traces import PostgresTraces

# Config
WEEKS = 12
PER_WEEK = 90
SKILL = "skill_refund_handling"
POLICY = "policy_refund"
USUAL = ["context_read", "action_proposed", "access_allowed", "refund_issued"]
NEW_PATH = ["context_read", "plan_checked", "action_proposed", "access_allowed", "refund_issued", "customer_told"]  # the latest week: two steps more
STEADY = {"finance": ("skill_billing_answers", ["invoice_read", "reply_drafted", "reply_sent"]), "operations": (None, ["meeting_read", "tasks_assigned"]),
          "sales": (None, ["lead_read", "quote_sent"]), "legal": (None, ["obligation_read", "evidence_checked"])}
NEW_WAYS = [("product", ["page_read", "copy_changed"]), ("general", ["vendor_read", "po_raised", "invoice_filed"])]


class Outbox:
    """K18 and K19 from this script stay here; the workspace's night sends each drift on (memory_fixes.sync)."""

    def publish(self, topic, event_type, payload, producer, cause=None):
        return None


def trace(tenant: str, n: int, area: str, skill: str | None, steps: list[str], at: datetime, policies: list, check: str = "within", why=None) -> TraceRecord:
    ref = VersionRef(id=skill, version=1, branch="main", commit_id="seed") if skill else None
    return TraceRecord(trace_id=f"tr-seed-{n}", tenant_id=tenant, area=area, source="finebrain" if skill or area != "customer_care" else "outside", started_at=at,
                       ended_at=at, input_ref=f"seed-{n}", steps=steps, policies=policies, skill=ref, access=[], outcome="resolved", decided_by="auto by policy",
                       why=why or [], policy_check=check, run_id=None)


def week_of_work(tenant: str, week: int, now: datetime, generator: random.Random, graph, start: int) -> list[TraceRecord]:
    """One week's traces; the latest week (week 0) carries both drifts and the new ways of working. Each refund is held to
    the refund policy in force that day, read from the graph, as the live pipeline does."""
    latest, made, n = week == 0, [], start
    # The latest week runs from this Monday until now, so all of it lands in the week the drift checks read last
    span = max(60, int((now - datetime.combine(week_of(now, "UTC"), datetime.min.time(), timezone.utc)).total_seconds() // 60)) if latest else 60 * 24 * 6
    for _ in range(PER_WEEK):
        at = now - timedelta(weeks=week, minutes=generator.randint(0, span))
        version = memory.policy_version_at(graph, POLICY, at)
        policies, window = [memory.trace_policy(version)], version["window_days"]
        roll = generator.random()
        if roll < 0.45:  # refunds by the skill: the usual path, until the latest week moves to a new one
            path = NEW_PATH if latest and generator.random() < 0.7 else USUAL
            made.append(trace(tenant, n, "customer_care", SKILL, path, at, policies, why=["Inside the refund window and under the automatic limit"]))
        elif roll < 0.55:  # refunds by hand: now and then past the window, then a spike
            late = generator.random() < (0.85 if latest else 0.08)
            days = generator.randint(window + 4, window + 14) if late else generator.randint(3, window - 2)
            made.append(trace(tenant, n, "customer_care", None, ["refund_by_hand"], at, policies, "outside" if late else "within", [f"{days} days since purchase, window is {window}"]))
        else:
            area = generator.choice(list(STEADY))
            made.append(trace(tenant, n, area, STEADY[area][0], STEADY[area][1], at, []))
        n += 1
    if latest:
        for area, steps in NEW_WAYS:
            made.append(trace(tenant, n, area, None, steps, now - timedelta(hours=generator.randint(1, 48)), []))
            n += 1
    return made


def main() -> int:
    # Step 1: the workspace, and its stores in Postgres
    tenant = sys.argv[sys.argv.index("--tenant") + 1] if "--tenant" in sys.argv else load_hq()[0]["tenant_id"] if "--hq" in sys.argv else None
    if not tenant or not store_postgres.database_is_up():
        print("say --tenant <id> or --hq, and start Postgres")
        return 1
    seed, _ = load_hq()
    connection, now = store_postgres.connect(), datetime.now(timezone.utc)
    lane = SimpleNamespace(seed={**seed, "tenant_id": tenant}, now=now, traces=PostgresTraces(connection, tenant), patterns=PostgresPatterns(connection, tenant),
                           drift=PostgresDrift(connection, tenant), records=store_postgres.PostgresRecords(connection, tenant), bus=Outbox(), memory_claims=set(),
                           graph=PostgresGraph(connection, tenant))
    if memory.policy_version_at(lane.graph, POLICY, now - timedelta(weeks=WEEKS)) is None:
        print(f"no {POLICY} in the graph {WEEKS} weeks back; load the workspace first")
        return 1

    # Step 2: twelve weeks, oldest first; a person confirms each new way of working, except the latest week's
    generator, kept, n = random.Random(2026), 0, 0
    for week in range(WEEKS - 1, -1, -1):
        for each in week_of_work(tenant, week, now, generator, lane.graph, n):
            n += 1
            if not lane.traces.save(each):
                continue
            kept += 1
            match = memory.triage(each, lane.patterns, zone_of(lane))  # the workspace's own weeks, as the consumer counts them
            lane.records.save(flow.MATCH_KIND, each.trace_id, match)
            if match.match == "surprise" and (week > 0 or each.skill):  # a person confirms; this week only the refund skill's new path
                memory.confirm(each, lane.patterns)
            elif match.match == "surprise":
                flow.raise_for_review(lane, match)

    # Step 3: the drift night on that history
    result = drift.night(lane)
    print(f"tenant {tenant}: {kept} traces kept over {WEEKS} weeks; drift night {result}")
    print("Next: run the workspace's night (Run now on the Distiller) so each drift's fix goes to an L1 user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
