# reference_routes.py: numbers from outside the Lab for one paper: figures published in a paper's tables, and the Lab's own
# runs of a public benchmark (AgentDojo). Read only; rows come in through scripts/research_load_references.py.
# Used by: research/routes.py. Uses: research/contracts.py, the research.reference_results table (store.py).
from fastapi import FastAPI, Header

from app.research.contracts import ReferenceResult

# Config
BENCHMARKS_OF_PAPER = {"security": ["PhantomPolicy", "AgentDojo banking v1.2.1"], "policies": ["FiscalQA Pro"], "skills": ["tau3-bench retail"]}  # which outside numbers each paper sets beside its own
OURS = "Finebrain Lab run"  # a source title that starts with this is the Lab's own run of a public benchmark, not a published figure
COLUMNS = "id, benchmark, metric_key, value, model, source_title, source_url, peer_reviewed, reported_on, note"


def register(app: FastAPI, check, connection) -> None:
    """`connection()` is the request's Postgres connection."""

    @app.get("/references")
    def references(paper: str, x_persona: str = Header(default="")) -> list[dict]:
        check(x_persona)
        benchmarks = BENCHMARKS_OF_PAPER.get(paper, [])
        if not benchmarks:
            return []
        rows = connection().execute(f"SELECT {COLUMNS} FROM research.reference_results WHERE benchmark = ANY(%s) ORDER BY benchmark, metric_key, value DESC",
                                    (benchmarks,)).fetchall()
        return [as_ui(row) for row in rows]


def as_ui(row: tuple) -> dict:
    found = ReferenceResult(**dict(zip([c.strip() for c in COLUMNS.split(",")], [str(row[0]), *row[1:8], str(row[8]), row[9]])))
    return {**found.ui(), "ours": found.source_title.startswith(OURS)}
