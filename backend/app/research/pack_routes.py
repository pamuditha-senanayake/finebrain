# pack_routes.py: upload, list and read experiment packs. An upload is read, audited (pack_audits.py) and stored only when
# no audit fails and every warning has a typed reason. Each refusal says why in a code the console turns into words.
# Used by: research/routes.py. Uses: research/pack_audits.py, research/packs.py, research/pack_store.py.
import json

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.research import pack_audits, pack_store
from app.research.packs import MAX_ZIP_BYTES, PackRefused


def reasons_from(text: str) -> dict[str, str]:
    """The typed reasons for warnings, as {audit key: reason}. Anything else is a bad request."""
    try:
        reasons = json.loads(text or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "bad_reasons") from None
    if not isinstance(reasons, dict) or not all(isinstance(v, str) for v in reasons.values()):
        raise HTTPException(400, "bad_reasons")
    return {key: value.strip() for key, value in reasons.items()}


def audited(data: bytes, reasons: dict[str, str]) -> tuple[dict, str, dict]:
    """The pack, its hash and the audit to store. Raises with the full audit when it fails or a warning has no reason."""
    try:
        pack, sha, checks = pack_audits.audit_pack(data)
    except PackRefused as error:
        raise HTTPException(400, str(error)) from None
    verdict = pack_audits.verdict(checks)
    if verdict == "fail":
        raise HTTPException(422, {"error": "pack_failed_audits", "audits": checks})
    needs = [check["key"] for check in checks if check["status"] == "warn" and not reasons.get(check["key"])]
    if needs:
        raise HTTPException(409, {"error": "warnings_need_reasons", "needs": needs, "audits": checks})
    return pack, sha, {"verdict": verdict, "checks": checks, "reasons": {key: reasons[key] for key in reasons if key in {c["key"] for c in checks}}}


def register(app: FastAPI, check, packs) -> None:
    """`check` lets only the founder or the research role in; `packs()` is the store, raising 503 when it does not answer."""

    @app.post("/packs")
    async def upload(file: UploadFile = File(...), reasons: str = Form(default="{}"), x_persona: str = Header(default="")):
        # Step 1: who, and a size that fits
        check(x_persona)
        data = await file.read(MAX_ZIP_BYTES + 1)
        if len(data) > MAX_ZIP_BYTES:
            raise HTTPException(413, "too_large")

        # Step 2: read and audit; a fail or an unexplained warning stops here, with every audit shown
        pack, sha, audit = audited(data, reasons_from(reasons))

        # Step 3: keep it; the same pack again answers with the one already kept
        new = pack_store.new_pack(pack["manifest"].kind, pack["manifest"].model_dump(mode="json"), sha, audit, x_persona)
        stored, created = packs().save(new, data)
        return JSONResponse({"pack": stored.ui(), "created": created}, status_code=201 if created else 200)

    @app.get("/packs")
    def recent(x_persona: str = Header(default="")) -> list[dict]:
        check(x_persona)
        return [pack.ui() for pack in packs().recent()]

    @app.get("/packs/{pack_id}")
    def one(pack_id: str, x_persona: str = Header(default="")) -> dict:
        check(x_persona)
        pack = packs().get(pack_id)
        if pack is None:
            raise HTTPException(404, "pack_not_found")
        return pack.ui()
