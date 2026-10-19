# ready_routes.py: step 16, readiness from the console: "Check now" runs S15's check at once (the screens also run it when it is
# over an hour old). A steward (L2) or a leader (L1) may run it. Used by: routes.py (registers before the general ops route).
# Uses: ready_views.py (run_check).
from fastapi import FastAPI, Header, HTTPException

from app.api import ready_views

# Config
MAY_CHECK = {"L1", "L2"}


def register(app: FastAPI, lane, check) -> None:
    """POST ops/runReadinessScheduler, the console's name for Check now. Must be added before the general ops route."""

    @app.post("/api/t/{tenant}/ops/runReadinessScheduler")
    def run_now(tenant: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        if lane.seed["people"][x_persona]["tier"] not in MAY_CHECK:
            raise HTTPException(403, "not_a_steward")
        return ready_views.run_check(lane, x_persona)
