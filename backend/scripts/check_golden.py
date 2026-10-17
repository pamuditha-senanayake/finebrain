# check_golden.py: checks the golden refund runs and the extra samples against their Pydantic contracts.
# Uses: app/pipeline/contracts_*.py, samples/golden_refund_run.json, samples/pipeline_samples.json.
# Run from backend/: uv run python -m scripts.check_golden
import hashlib
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.pipeline import contracts_failure, contracts_graph, contracts_reason, contracts_run, contracts_signal

# Config
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
GOLDEN_FILE = SAMPLES_DIR / "golden_refund_run.json"
RAW_FILE = SAMPLES_DIR / "pipeline_samples.json"
CONTRACT_MODULES = [contracts_signal, contracts_reason, contracts_run, contracts_graph, contracts_failure]


# --- Loading

def load_json(path: Path) -> dict:
    """Read one JSON file."""
    return json.loads(path.read_text())


def load_raw_bodies() -> dict[str, bytes]:
    """Map sample_id to the raw body bytes S1 would receive."""
    items = load_json(RAW_FILE)["items"]
    return {item["sample_id"]: item["raw_body"].encode() for item in items}


def find_model(name: str) -> type[BaseModel]:
    """Look up a contract class by name across the contract modules."""
    for module in CONTRACT_MODULES:
        model = getattr(module, name, None)
        if model is not None:
            return model
    raise LookupError(f"no contract named {name}")


# --- Helpers

def is_kafka(step: dict) -> bool:
    """Only Kafka steps carry an envelope and a causation link."""
    return step["transport"].startswith("kafka:")


def describe(error: Exception) -> str:
    """Shorten an error to its first problem, so one table row stays one line."""
    if not isinstance(error, ValidationError):
        return str(error)
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}"


# --- Checks (each returns a problem, or "" when the step is fine)

def check_contract(step: dict) -> str:
    """The step's data must fit its named contract."""
    try:
        find_model(step["model"]).model_validate(step["data"])
    except (ValidationError, LookupError) as error:
        return describe(error)
    return ""


def check_envelope(step: dict, envelope: dict) -> str:
    """Kafka steps must form a valid shared envelope."""
    if not is_kafka(step):
        return ""
    message = {**envelope, **step["event"], "payload": step["data"]}
    try:
        contracts_signal.Envelope.model_validate(message)
    except ValidationError as error:
        return describe(error)
    return ""


def check_raw_body(step: dict, raw_body: bytes) -> str:
    """K1 hash and size must match the raw body in pipeline_samples.json."""
    if step["contract"] != "K1":
        return ""
    if hashlib.sha256(raw_body).hexdigest() != step["data"]["raw_sha256"]:
        return "raw_sha256 does not match the raw body"
    if len(raw_body) != step["data"]["size_bytes"]:
        return "size_bytes does not match the raw body"
    return ""


def check_causation(step: dict, previous_event_id: str | None) -> str:
    """Each Kafka message points at the Kafka message before it."""
    if not is_kafka(step):
        return ""
    if step["event"]["causation_id"] != previous_event_id:
        return f"causation_id should be {previous_event_id}"
    return ""


# --- Main logic

def check_run(run: dict, raw_bodies: dict[str, bytes]) -> list[tuple[str, str, str, str]]:
    """Run every check on every step of one run, in order."""
    rows = []
    previous_event_id = None
    for step in run["steps"]:
        problems = [
            check_contract(step),
            check_envelope(step, run["envelope"]),
            check_raw_body(step, raw_bodies[run["sample_id"]]),
            check_causation(step, previous_event_id),
        ]
        result = "; ".join(problem for problem in problems if problem) or "ok"
        rows.append((run["sample_id"][:2], step["stage"], f"{step['contract']} {step['model']}", result))
        if is_kafka(step):
            previous_event_id = step["event"]["event_id"]
    return rows


def check_extras(extras: list[dict]) -> list[tuple[str, str, str, str]]:
    """Samples outside the refund path are only checked against their contract."""
    return [("ex", "-", f"{item['contract']} {item['model']}", check_contract(item) or "ok") for item in extras]


def print_table(rows: list[tuple[str, str, str, str]]) -> None:
    """Print one line per step."""
    print(f"{'run':<4} {'stage':<6} {'contract':<24} result")
    for run, stage, contract, result in rows:
        print(f"{run:<4} {stage:<6} {contract:<24} {result}")


def main() -> int:
    # Step 1: load the golden runs and the raw bodies they point at
    golden = load_json(GOLDEN_FILE)
    raw_bodies = load_raw_bodies()

    # Step 2: check every step of every run, then the extras
    rows = [row for run in golden["runs"] for row in check_run(run, raw_bodies)]
    rows += check_extras(golden["extras"])

    # Step 3: report, and exit non-zero so CI can use it later
    print_table(rows)
    failures = sum(1 for row in rows if row[3] != "ok")
    print(f"\n{len(rows) - failures} ok, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
