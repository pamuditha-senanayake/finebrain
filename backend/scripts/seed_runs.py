# seed_runs.py: a dev script. Fills a memory pipeline with thousands of runs, to test lists of thousands (step 12).
# Run it to serve Finebase HQ on port 8000 with N runs loaded:  uv run python -m scripts.seed_runs 10000
# Tests import add_runs. Uses: app/api (routes, hq), app/pipeline (orchestrate, fakes), tests/golden.py.
import sys
import threading
import time
from datetime import timedelta

from app.api.hq import load_hq
from app.api.routes import create_api_app
from app.pipeline import fakes, orchestrate
from app.pipeline.contracts_run import RunRecord
from tests.golden import NOW, golden

# Config
AGENTS = ["agent_refund_worker", "agent_billing_worker", "agent_support_worker"]
OUTCOMES = ["resolved", "resolved", "resolved", "escalated", "failed", "awaiting_approval"]
SPREAD_DAYS = 60
TEMPLATE = RunRecord.model_validate(golden("s3", "RunRecord"))


def add_runs(lane, count: int) -> list[str]:
    """Save `count` runs: spread over 60 days, three agents, mixed outcomes, a case number in every subject."""
    ids = []
    for i in range(count):
        started = NOW - timedelta(minutes=i * (SPREAD_DAYS * 24 * 60) // count)
        steps = [step.model_copy(update={"started_at": started}) for step in TEMPLATE.steps]
        run = TEMPLATE.model_copy(update={"run_id": f"run_{i:05d}", "task_id": f"Issue refund LKR {1000 + (i * 37) % 90000:,} case {i:05d}", "agent_id": AGENTS[i % 3],
                                          "outcome": OUTCOMES[i % len(OUTCOMES)], "steps": steps, "trace_object_uri": f"pending:{i}"})
        lane.records.save("run", run.run_id, run)
        ids.append(run.run_id)
    return ids


def main(count: int) -> None:
    import uvicorn

    seed, hq = load_hq()
    lane = orchestrate.build_lane(seed, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    add_runs(lane, count)
    threading.Thread(target=lambda: [(lane.bus.drain(), time.sleep(0.3)) for _ in iter(int, 1)], daemon=True).start()  # uploads move through the bus
    print(f"{count} runs loaded; serving Finebase HQ on http://localhost:8000")
    uvicorn.run(create_api_app(lane, hq), host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
