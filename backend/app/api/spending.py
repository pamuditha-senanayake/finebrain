# spending.py: A4, spending nobody tracks. A filed receipt or invoice becomes one spend; people can add one by hand too.
# Each month is totalled in the budget's currency and shown as on track, close or over; spends that repeat are the
# subscriptions, with their cost per month. Totals only: no tax or finance advice. The "Spending" workflow in Studio holds
# the budget and can pause it. Used by: intake.py, routes.py, tests/test_spending.py. Uses: brain_workflows.py, intake_policy.py.
import uuid
from datetime import date, datetime

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from app.api import brain_workflows
from app.api import intake_policy as policy

# Config
KIND = "spend"
MONTHS_SHOWN = 6
PER_MONTH = {"once": 0.0, "monthly": 1.0, "yearly": 1 / 12}


class Spend(BaseModel):
    spend_id: str
    vendor: str
    amount: float
    currency: str
    category: str
    repeats: str
    paid_on: str  # YYYY-MM-DD
    source: dict | None = None  # {document_id, title} when it came from a filed receipt
    created_at: datetime
    created_by: str
    removed: bool = False


def checked(body: dict) -> dict:
    """A person's spend, cleaned by the intake's own rules; anything that does not fit is refused, not guessed."""
    out = {}
    for name in ("vendor", "amount", "currency", "category", "repeats"):
        if name in body:
            value = policy.clean(name, body[name])
            if value is None:
                raise HTTPException(400, f"bad_{name}")
            out[name] = value
    if "paid_on" in body:
        if (day := policy.spoken_date(str(body["paid_on"]))) is None:
            raise HTTPException(400, "bad_paid_on")
        out["paid_on"] = day
    return out


# --- From a receipt

def from_receipt(lane, fields: dict, document_id: str, title: str) -> dict | None:
    """One spend per filed receipt; its id comes from the document, so filing twice records it once."""
    if not brain_workflows.active(lane, brain_workflows.SPENDING):
        return None
    spend_id = f"spend_{document_id.removeprefix('doc_')}"
    if (kept := lane.records.load(KIND, spend_id)) is None:
        kept = Spend(spend_id=spend_id, vendor=fields["vendor"], amount=fields["amount"], currency=fields["currency"], category=fields["category"],
                     repeats=fields["repeats"], paid_on=fields["date"], source={"document_id": document_id, "title": title}, created_at=lane.now,
                     created_by="agent_bookkeeper").model_dump(mode="json")
        lane.records.save(KIND, spend_id, Spend.model_validate(kept))
    return spend_view(kept)


# --- Showing

def spend_view(spend: dict) -> dict:
    src = spend.get("source")
    return {"id": spend["spend_id"], "vendor": spend["vendor"], "amount": spend["amount"], "currency": spend["currency"], "category": spend["category"],
            "categoryLabel": policy.CATEGORIES[spend["category"]], "repeats": spend["repeats"], "paidOn": spend["paid_on"],
            "source": {"documentId": src["document_id"], "title": src["title"]} if src else None}


def month_of(day: str) -> str:
    return day[:7]


def summary(lane) -> dict:
    """This month against the budget, the last six months, this month by category, the subscriptions, and every spend."""
    rules = brain_workflows.budget(lane)
    spends = [s for s in lane.records.list_kind(KIND) if not s.get("removed")]
    now = lane.now.date()
    months = []
    year, month = now.year, now.month
    for _ in range(MONTHS_SHOWN):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    in_budget = [s for s in spends if s["currency"] == rules["currency"]]
    totals = {m: round(sum(s["amount"] for s in in_budget if month_of(s["paid_on"]) == m), 2) for m in months}
    this = months[0]
    spent = totals[this]
    used = round(spent / rules["monthly"] * 100, 1) if rules["monthly"] else 0.0
    state = "over" if used > 100 else "close" if used >= rules["warn_percent"] else "ok"
    by_category = {}
    for s in in_budget:
        if month_of(s["paid_on"]) == this:
            by_category[s["category"]] = round(by_category.get(s["category"], 0) + s["amount"], 2)
    other = sorted({s["currency"] for s in spends if s["currency"] != rules["currency"] and month_of(s["paid_on"]) == this})
    subscriptions = [{**spend_view(s), "perMonth": round(s["amount"] * PER_MONTH[s["repeats"]], 2)} for s in spends if s["repeats"] != "once"]
    return {
        "budget": {"currency": rules["currency"], "monthly": rules["monthly"], "warnPercent": rules["warn_percent"]},
        "month": {"month": this, "spent": spent, "usedPercent": used, "state": state, "otherCurrencies": other},
        "months": [{"month": m, "spent": totals[m]} for m in reversed(months)],
        "byCategory": [{"category": c, "label": policy.CATEGORIES[c], "spent": v} for c, v in sorted(by_category.items(), key=lambda kv: -kv[1])],
        "subscriptions": sorted(subscriptions, key=lambda s: -s["perMonth"]),
        "spends": [spend_view(s) for s in sorted(spends, key=lambda s: s["paid_on"], reverse=True)],
    }


def said(lane, spend: dict) -> str:
    """Lisena's words after a receipt is filed: what was logged and where the month stands."""
    month = summary(lane)
    where = {"over": "over budget", "close": "close to the budget", "ok": "on track"}[month["month"]["state"]]
    return (f"I logged {spend['currency']} {spend['amount']:,.2f} to {spend['vendor']}. This month is at {month['month']['usedPercent']:.0f}% "
            f"of the {month['budget']['currency']} {month['budget']['monthly']:,.0f} budget, {where}.")


def register(app: FastAPI, lane, check) -> None:
    """GET and POST /api/t/{tenant}/spending, POST /api/t/{tenant}/spending/{id}. Must be added before the catch-all POST route."""

    @app.get("/api/t/{tenant}/spending")
    def overview(tenant: str, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        return summary(lane)

    @app.post("/api/t/{tenant}/spending", status_code=201)
    async def add(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        body = checked({"repeats": "once", "paid_on": date.isoformat(lane.now.date()), **(await request.json())})
        if missing := [name for name in ("vendor", "amount", "currency", "category") if name not in body]:
            raise HTTPException(400, f"missing:{','.join(missing)}")
        spend = Spend(spend_id=f"spend_{uuid.uuid4().hex[:12]}", **body, created_at=lane.now, created_by=x_persona)
        lane.records.save(KIND, spend.spend_id, spend)
        return spend_view(spend.model_dump(mode="json"))

    @app.post("/api/t/{tenant}/spending/{spend_id}")
    async def change(tenant: str, spend_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        spend = lane.records.load(KIND, spend_id)
        if spend is None or spend.get("removed"):
            raise HTTPException(404, "not_found")
        body = await request.json()
        update = {"removed": True} if body.get("remove") else checked(body)
        lane.records.save(KIND, spend_id, Spend.model_validate({**spend, **update}))
        return spend_view({**spend, **update})
