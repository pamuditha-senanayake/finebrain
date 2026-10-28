# research_make_refund_skills_pack.py: a dev script. Builds refund_skills_v1, a skills pack for the refund activity on
# Finebase Labs, and runs the pack audits on it:
#   uv run python scripts/research_make_refund_skills_pack.py <out.zip>
# Cases: 14 refund emails whose right ending follows from the refund policy (30 days, LKR 50,000 automatic limit): refund
# now, wait for a person (late or large), or hand to a person (a payment the shop does not have). Logs: how the work is
# really done, generated with known deviations from the written procedure: staff often confirm the order with the customer
# before refunding, and a refund that fails goes to a person. The normative model is the written procedure, one decision
# per case. Everything here is generated, never field data. Uses: research/pack_audits.py, pipeline/activities.py.
import io
import json
import random
import sys
import zipfile
from datetime import datetime, timedelta

from app.pipeline import activities
from app.research import pack_audits

# Config
SEED, NOW = 20261028, datetime.fromisoformat("2026-10-10T10:00:00+05:30")
TOOLS = ["issue_refund", "reply_customer", "escalate"]
CASES = [("refund", 8), ("late", 3), ("large", 3)]  # (kind, how many); plus escalations for unknown payments below
UNKNOWN = 2
NORMATIVE = ("->( 'retrieve_context', X( ->( 'propose_issue_refund', 'access_allow', X( 'act_issue_refund', ->( 'await_approval', X( tau, 'act_issue_refund' ) ) ) ), "
             "->( 'propose_escalate', 'access_allow', X( tau, 'act_escalate' ) ), ->( 'propose_reply_customer', 'access_allow', 'act_reply_customer' ) ) )")
# v1.1: as the product records a case, an escalation ends at the hand-off (no tool step) and a refund waiting for a person ends
# at the wait until someone decides; v1.0 asked for an action after both, which no run of the product can show
CONFIRM_FIRST, FAILED_THEN_PERSON = 0.35, 0.08  # how often real handling deviates from the written procedure
TRAIN, HELDOUT = 200, 100


def orders(rng: random.Random) -> tuple[list[dict], list[dict]]:
    found, tasks = [], []
    for kind, count in CASES:
        for _ in range(count):
            i = len(found) + 1
            paid = NOW - timedelta(days=rng.randrange(40, 70) if kind == "late" else rng.randrange(2, 9))
            total = rng.randrange(6_000_000, 9_000_000, 50_000) if kind == "large" else rng.randrange(200_000, 3_000_000, 50_000)
            ref = f"pay_FB_{paid:%Y%m%d}_{8000 + i:04d}"
            found.append({"id": f"ORD-K{i:02d}", "customer_id": f"cus_k{i:02d}", "product": rng.choice(["Desk lamp", "Headset", "Webcam", "Office chair"]),
                          "total_minor": total, "currency": "LKR", "status": "paid", "paid_at": paid.isoformat(), "payment_ref": ref})
            expected = {"outcome": "resolved", "refund_minor": total} if kind == "refund" else {"outcome": "awaiting_approval"}
            tasks.append(task(f"K-{i:02d}", f"customer{i:02d}@example.lk", ref, total, expected))
    for n in range(UNKNOWN):
        i = len(found) + n + 1
        tasks.append(task(f"K-{i:02d}", f"customer{(n % len(found)) + 1:02d}@example.lk", f"pay_FB_20261003_{7000 + i:04d}", 1_500_000, {"outcome": "escalated"}))
    return found, tasks


def task(task_id: str, email: str, ref: str, total: int, expected: dict) -> dict:
    message = f"Hello, I would like a full refund for my order (LKR {total // 100:,}, payment ref {ref}). It does not suit us. Thank you."
    return {"task_id": task_id, "user_message": message, "initial_state": {"customer_email": email, "principal": "agent_refund_worker", "payment_ref": ref},
            "expected_final_state": expected}


def trace(rng: random.Random) -> list[str]:
    """One case as it is really handled: mostly by the procedure, sometimes confirming first, sometimes failing to a person."""
    kind = rng.choices(["refund", "approval", "escalate"], [0.6, 0.25, 0.15])[0]
    events = ["retrieve_context"]
    if kind != "escalate" and rng.random() < CONFIRM_FIRST:
        events += ["propose_reply_customer", "access_allow", "act_reply_customer", "retrieve_context"]
    if kind == "escalate":
        return events + ["propose_escalate", "access_allow", "act_escalate"]
    events += ["propose_issue_refund", "access_allow"] + (["await_approval"] if kind == "approval" else [])
    if rng.random() < FAILED_THEN_PERSON:
        return events + ["act_issue_refund_failed", "propose_escalate", "access_allow", "act_escalate"]
    return events + ["act_issue_refund"]


def xes(traces: list[list[str]], name: str) -> str:
    """A minimal XES log, each event a minute after the one before."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<log xes.version="1.0" xmlns="http://www.xes-standard.org/">',
             '<extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>',
             '<extension name="Time" prefix="time" uri="http://www.xes-standard.org/time.xesext"/>', f'<string key="concept:name" value="{name}"/>']
    for n, events in enumerate(traces):
        start = NOW + timedelta(hours=n)
        lines.append(f'<trace><string key="concept:name" value="case_{n:04d}"/>')
        lines += [f'<event><string key="concept:name" value="{a}"/><date key="time:timestamp" value="{(start + timedelta(minutes=i)).isoformat()}"/></event>'
                  for i, a in enumerate(events)]
        lines.append("</trace>")
    return "\n".join(lines + ["</log>"]) + "\n"


def build_pack() -> bytes:
    rng = random.Random(SEED)
    shop_orders, tasks = orders(rng)
    shop = {"customers": [{"id": o["customer_id"], "email": f"customer{i + 1:02d}@example.lk", "name": f"Customer {i + 1:02d}"} for i, o in enumerate(shop_orders)],
            "orders": shop_orders, "refunds": []}
    alphabet = activities.alphabet({"allowed_tools": TOOLS})
    files = {"tasks.jsonl": jsonl(tasks), "gold.jsonl": jsonl([{"task_id": t["task_id"], "expected": t["expected_final_state"]} for t in tasks]),
             "shop.json": json.dumps(shop, indent=1), "alphabet.json": json.dumps(alphabet), "normative_model.ptree": NORMATIVE + "\n",
             "train_log.xes": xes([trace(rng) for _ in range(TRAIN)], "refund_train"), "heldout_log.xes": xes([trace(rng) for _ in range(HELDOUT)], "refund_heldout"),
             "README.md": "Generated refund cases and logs for the skills paper (seed 20261028). Not field data.\n"}
    manifest = {"kind": "skills", "name": "refund_skills_v1", "version": "1.1.0", "company": "Finebase Labs", "timezone": "Asia/Colombo", "currency": "LKR",
                "created_by": "research_lab", "license": "generated for the Finebrain Research Lab", "files": sorted(files)}  # no web check: there is nothing to search for in generated text, so the upload states that as the warning's reason
    files["manifest.json"] = json.dumps(manifest, indent=1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0)), files[path])
    return buffer.getvalue()


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


if __name__ == "__main__":
    data = build_pack()
    open(sys.argv[1], "wb").write(data)
    _, sha, checks = pack_audits.audit_pack(data)
    print(f"{sys.argv[1]}: {len(data)} bytes, sha256 {sha[:16]}, verdict {pack_audits.verdict(checks)}")
    for check in checks:
        print(f"  {check['status']:<15} {check['label']}: {check['detail']}", *(f"\n      {line}" for line in check["lines"][:5]))
