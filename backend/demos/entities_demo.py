# entities_demo.py: step 13a. Send a few emails through S1 and S2 and print the entity registry they build.
# Edit EMAILS below, then run from backend/:  uv run python -m demos.entities_demo
# Runs in memory only: no Docker, no real services. Uses: orchestrate.py, entity_match.py, golden seed.
from app.pipeline import fakes, orchestrate
from tests.golden import NOW, SEED, raw_sample

# --- Input: change anything here
# (sample, message id): the same message id twice is a redelivery, a new id is a new email
EMAILS = [("s2", "mail_001"), ("s2", "mail_002"), ("s3", "mail_003")]
NOTE = "Refund note\n\nPayment pay_FB_20261004_0192 was refunded in full."  # an upload that names a payment


def build_s1_s2_only():
    """A memory pipeline wired for S1 and S2 only, so nothing downstream runs."""
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)
    lane.bus.subscribers = {"signals.raw": lane.bus.subscribers["signals.raw"]}
    return lane


def print_registry(lane) -> None:
    """One line per entity: its type, key, how many sources mention it, and its typed links (once each, though every source keeps its own row)."""
    for entity in lane.entities.all():
        links = dict.fromkeys(f"{link['rel']} {'->' if link['from_id'] == entity['entity_id'] else '<-'}" for link in lane.entities.links_of(entity["entity_id"]))
        print(f"{entity['type']:<13} {entity['key'][:30]:<31} sources {len(lane.entities.sources_of(entity['entity_id']))}  {', '.join(links)}")


def main() -> None:
    # Step 1: send the emails and the upload through S1 and S2
    lane = build_s1_s2_only()
    for key, message_id in EMAILS:
        orchestrate.capture_signal(lane, {**raw_sample(key), "external_id": message_id})
    orchestrate.capture_signal(lane, {**raw_sample("s1"), "external_id": "doc_demo_note", "raw_body": NOTE})
    lane.bus.drain()

    # Step 2: show what the registry now knows
    print(f"{len(lane.entities.all())} entities\n")
    print_registry(lane)


if __name__ == "__main__":
    main()
