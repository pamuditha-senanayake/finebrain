# prereg_routes.py: draft, edit, lock, list and read preregistrations. Locking needs the title typed back, so a lock is
# never a slip of the mouse; a locked one answers 409 to every change. Used by: research/routes.py. Uses: research/prereg.py.
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ValidationError

from app.research import prereg
from app.research.contracts import Hypothesis, Paper


class DraftBody(BaseModel):
    paper: Paper
    title: str
    hypotheses: list[dict]


class EditBody(BaseModel):
    title: str
    hypotheses: list[dict]


class LockBody(BaseModel):
    confirm: str  # the title, typed again


def hypotheses_from(raw: list[dict]) -> list[Hypothesis]:
    """Valid hypotheses, or a 422 naming every problem at once."""
    found, issues = [], []
    for index, item in enumerate(raw):
        try:
            found.append(Hypothesis.model_validate(item))
        except ValidationError as error:
            issues += [f"hypothesis {index + 1}: {'.'.join(map(str, e['loc']))} {e['msg']}" for e in error.errors()]
    issues += prereg.problems(found) if not issues else []
    if issues:
        raise HTTPException(422, {"error": "invalid_hypotheses", "problems": issues})
    return found


def register(app: FastAPI, check, preregs) -> None:
    """`check` lets only the founder or the research role in; `preregs()` is the store."""

    @app.post("/preregistrations", status_code=201)
    def create(body: DraftBody, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        if not body.title.strip():
            raise HTTPException(422, {"error": "invalid_hypotheses", "problems": ["a title is needed"]})
        return preregs().create(prereg.draft(body.paper, body.title.strip(), hypotheses_from(body.hypotheses))).ui()

    @app.put("/preregistrations/{prereg_id}")
    def edit(prereg_id: str, body: EditBody, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        try:
            changed = preregs().edit(prereg_id, body.title.strip(), hypotheses_from(body.hypotheses))
        except prereg.PreregLocked:
            raise HTTPException(409, "preregistration_locked") from None
        if changed is None:
            raise HTTPException(404, "preregistration_not_found")
        return changed.ui()

    @app.post("/preregistrations/{prereg_id}/lock")
    def lock(prereg_id: str, body: LockBody, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        current = preregs().get(prereg_id)
        if current is None:
            raise HTTPException(404, "preregistration_not_found")
        if body.confirm.strip() != current.title:
            raise HTTPException(400, "confirm_does_not_match_title")
        try:
            return preregs().lock(prereg_id, x_persona).ui()
        except prereg.PreregLocked:
            raise HTTPException(409, "preregistration_locked") from None

    @app.get("/preregistrations")
    def recent(x_persona: str = Header(default="")) -> list[dict]:
        check(x_persona)
        return [p.ui() for p in preregs().recent()]

    @app.get("/preregistrations/{prereg_id}")
    def one(prereg_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        found = preregs().get(prereg_id)
        if found is None:
            raise HTTPException(404, "preregistration_not_found")
        return found.ui()
