# golden.py: loads the golden refund runs and raw samples once, for every test file.
# Used by: tests/test_stages.py, tests/test_chain.py. Uses: samples/golden_refund_run.json, samples/pipeline_samples.json.
import json
from datetime import datetime
from pathlib import Path

# Config
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
GOLDEN = json.loads((SAMPLES / "golden_refund_run.json").read_text())
RAW = {item["sample_id"]: item for item in json.loads((SAMPLES / "pipeline_samples.json").read_text())["items"]}
SEED = GOLDEN["seed"]
NOW = datetime.fromisoformat(GOLDEN["frozen_now"])
RUNS = {run["sample_id"][:2]: run for run in GOLDEN["runs"]}
ANSWER_FIELDS = ("rationale_summary", "citations", "confidence")


def golden(run_key: str, model_name: str) -> dict:
    """Data of the first step in a golden run that uses this contract."""
    return next(step["data"] for step in RUNS[run_key]["steps"] if step["model"] == model_name)


def raw_sample(key: str) -> dict:
    """Raw signal for a key like s2 or s4."""
    return next(item for sample_id, item in RAW.items() if sample_id.startswith(key + "_"))


def recorded_answer(run_key: str) -> dict:
    """The tool call Claude made in a golden run, ready for fakes.tool_response."""
    action = golden(run_key, "ProposedAction")
    tool_input = {**action["arguments"], **{key: action[key] for key in ANSWER_FIELDS}}
    usage = action["model"]
    return {"tool": action["action_type"], "tool_input": tool_input, "model": usage["model_id"], "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]}


def recorded_answers() -> dict[str, dict]:
    """Payment ref to recorded tool call, for s2 and s3."""
    return {golden(key, "ProposedAction")["arguments"]["payment_ref"]: recorded_answer(key) for key in ("s2", "s3")}


def released_policies() -> dict[str, dict]:
    """Policy id to its released node, as S7 reads them from the graph."""
    from app.pipeline.adapters import seeded
    from app.pipeline.store_graph import MemoryGraph

    return {node["_ref"]["id"]: node for node in seeded(MemoryGraph(SEED["tenant_id"]), SEED).latest("policy")}
