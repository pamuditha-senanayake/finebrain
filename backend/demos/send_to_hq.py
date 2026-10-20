# send_to_hq.py: send the sample refund emails to Finebase HQ's capture endpoint, signed as the Gmail connector would.
# Run with the API up (port 8000), from backend/:  uv run python -m demos.send_to_hq        (both)
#                                                 uv run python -m demos.send_to_hq s3     (just the one that needs approval)
#                                                 uv run python -m demos.send_to_hq s2 10  (ten of it: a busy week for the spike check)
# Each send gets a fresh message id, so S2 never drops it as a duplicate. Secrets are the seed's test-only values.
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

from app.pipeline.capture_api import sign

# Config
API = os.environ.get("HQ_API", "http://localhost:8000")
CONNECTOR = "conn_gmail_support"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
EMAILS = {"s2": "s2_refund_monthly_in_policy", "s3": "s3_refund_annual_late_large"}


def send(sample_id: str, secret: str, samples: dict) -> None:
    """POST one signed email and print what S1 answered."""
    body = samples[sample_id]["raw_body"].encode()
    headers = {"content-type": "message/rfc822", "x-external-id": f"gmail_demo_{uuid.uuid4().hex[:10]}", "x-signature": sign(secret, body),
               "subject": samples[sample_id]["headers_subset"]["subject"], "to": "support@finebase.lk"}
    response = httpx.post(f"{API}/capture/{CONNECTOR}", content=body, headers=headers, timeout=60)  # S1 answers slowly while the pipeline is busy with Claude
    print(f"{sample_id}: HTTP {response.status_code} {response.json()}")


def main() -> None:
    # Step 1: the sample emails and the connector's test secret
    samples = {item["sample_id"]: item for item in json.loads((SAMPLES / "pipeline_samples.json").read_text())["items"]}
    secret = json.loads((SAMPLES / "golden_refund_run.json").read_text())["seed"]["connectors"][CONNECTOR]["secret"]

    # Step 2: send the ones asked for, as many times as asked
    args = sys.argv[1:]
    times = int(args.pop()) if args and args[-1].isdigit() else 1
    for key in args or list(EMAILS):
        for _ in range(times):
            send(EMAILS[key], secret, samples)


if __name__ == "__main__":
    main()
