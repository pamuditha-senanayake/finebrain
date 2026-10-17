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
ANSWER_FIELDS = ("action_type", "tool_id", "tool_version", "arguments", "rationale_summary", "citations", "confidence")


def golden(run_key: str, model_name: str) -> dict:
    """Data of the first step in a golden run that uses this contract."""
    return next(step["data"] for step in RUNS[run_key]["steps"] if step["model"] == model_name)


def raw_sample(key: str) -> dict:
    """Raw signal for a key like s2 or s4."""
    return next(item for sample_id, item in RAW.items() if sample_id.startswith(key + "_"))


def recorded_answer(run_key: str) -> dict:
    """What the model said in a golden run, in the shape S6 expects from the model."""
    action = golden(run_key, "ProposedAction")
    return {**{key: action[key] for key in ANSWER_FIELDS}, "usage": action["model"]}
