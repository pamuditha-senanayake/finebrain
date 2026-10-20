# stages_tiers.py: the tier mover (step 13c). Each tier has a fixed budget in numbers, never a percentage, so what a
# question reads stays the same size however much is stored. Every night, by value: the best open items fill hot up to
# its budget, the rest stay warm while their entity (or, for items about no entity, their domain) has room, and the
# overflow and long-closed facts go cold, where only questions about the past look.
# Used by: api/memory_routes.py, api/hq.py (nightly), tests/test_tiers.py, test_cold.py. Uses: stages_value.py (moment), stages_cold.py (archive).
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.pipeline import stages_cold
from app.pipeline.stages_value import moment

# Config
BUDGETS = {"hot": 100_000, "warm_per_entity": 500, "warm_per_domain": 5_000, "closed_grace_days": 30}  # docs: Starting numbers
RUN_KIND = "tier_run"


class TierRun(BaseModel):
    """What one pass did, kept as the latest record so the overview can say it."""
    at: datetime
    hot: int
    warm: int
    cold: int
    moved: int


# --- Placing

def keys_of(row: dict) -> list[str]:
    """The budgets an item counts against: each entity it is about, or its domain when it is about none."""
    return [f"entity:{e}" for e in row.get("entity_ids") or []] or [f"domain:{row.get('domain') or 'general'}"]


def closed_by(row: dict, when: datetime) -> bool:
    return bool(row.get("valid_to")) and moment(row["valid_to"]) <= when


def place(rows: list[dict], now: datetime, budgets: dict = BUDGETS) -> dict[str, str]:
    """Each item's tier. Highest value first, so when a budget is full it is the lowest value that moves down."""
    placed, used, hot = {}, {}, 0
    for row in sorted(rows, key=lambda r: (-(r.get("value") or 0), r["item_id"])):
        if closed_by(row, now - timedelta(days=budgets["closed_grace_days"])):
            placed[row["item_id"]] = "cold"
        elif hot < budgets["hot"] and not closed_by(row, now):
            placed[row["item_id"]], hot = "hot", hot + 1
        else:
            placed[row["item_id"]] = warm_or_cold(row, used, budgets)
    return placed


def warm_or_cold(row: dict, used: dict[str, int], budgets: dict) -> str:
    """Warm while one of the item's budgets has room; that use counts against all of them."""
    keys = keys_of(row)
    room = any(used.get(key, 0) < (budgets["warm_per_entity"] if key.startswith("entity:") else budgets["warm_per_domain"]) for key in keys)
    if not room:
        return "cold"
    for key in keys:
        used[key] = used.get(key, 0) + 1
    return "warm"


# --- Moving

def move(lane, budgets: dict | None = None) -> TierRun:
    """Place every item and store only what changed. Budgets come from the seed when it sets them, else the defaults."""
    budgets = budgets or {**BUDGETS, **lane.seed.get("tier_budgets", {})}
    rows = lane.chunks.value_rows()
    placed = place(rows, lane.now, budgets)
    changed = {row["item_id"]: placed[row["item_id"]] for row in rows if row.get("tier") != placed[row["item_id"]]}
    was_cold = {row["item_id"] for row in rows if row.get("tier") == "cold"}

    # Coming up from cold gets its vector back first; going cold is archived once its tier is set
    stages_cold.thaw(lane, [item_id for item_id in changed if item_id in was_cold])
    lane.chunks.set_tiers(changed)
    stages_cold.freeze(lane, [row["item_id"] for row in rows if placed[row["item_id"]] == "cold" and row.get("has_vector", True)])  # also cold from before
    run = TierRun(at=lane.now, moved=len(changed), **{tier: sum(t == tier for t in placed.values()) for tier in ("hot", "warm", "cold")})
    lane.records.save(RUN_KIND, "latest", run)
    return run
