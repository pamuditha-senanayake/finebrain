# event_log_routes.py: download a skill's runs as an XES event log (Research Lab P4), for conformance checking in pm4py,
# ProM or Disco. Read only; anyone who may open the tenant may export it. Used by: api/routes.py. Uses: event_log.py.
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response

from app.pipeline import event_log


def register(app: FastAPI, lane, check) -> None:
    @app.get("/api/t/{tenant}/skills/{skill_id}/event-log.xes")
    def export(tenant: str, skill_id: str, x_persona: str = Header(default="")) -> Response:
        check(tenant, x_persona)
        if not lane.graph.history("skill", skill_id):
            raise HTTPException(404, "skill_not_found")
        body = event_log.to_xes(event_log.runs_of(lane, skill_id), skill_id)
        return Response(body, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{skill_id}.xes"'})
