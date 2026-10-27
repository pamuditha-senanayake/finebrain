# experiment_store.py: experiments, their case results, metric values and comparisons, all keyed. A worker claims an
# experiment in one statement (a crashed worker's claim lapses when its heartbeat is old); a case result is written once
# per (experiment, condition, seed, trial, case), so a resumed run never counts a case twice. PostgresExperiments and twin.
# Used by: research/runner.py, research/experiment_routes.py. Uses: research/contracts.py.
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Jsonb

from app.research.contracts import CaseResult, Comparison, Experiment, MetricValue

# Config
CLAIMABLE = ("draft", "estimated", "paused", "failed")
STALE_AFTER = timedelta(seconds=120)  # no heartbeat for this long: the worker is gone and another may take over
EXPERIMENT_COLUMNS = ("id, paper, pack_id, prereg_id, source, benchmark, conditions, seeds, trials, models, budget_usd, config_sha256, git_commit, "
                      "status, started_at, finished_at, cost_usd, notes")
CASE_COLUMNS = "experiment_id, condition, seed, trial, case_id, correlation_id, outcome, passed, latency_ms, tokens_in, tokens_out, cost_usd, trace_uri, error"


def case_key(case: CaseResult) -> tuple:
    return case.condition, case.seed, case.trial, case.case_id


class MemoryExperiments:
    """The in-memory twin of PostgresExperiments."""

    def __init__(self):
        self.rows: dict[str, Experiment] = {}
        self.claims: dict[str, tuple[str, datetime]] = {}
        self.cases: dict[str, dict[tuple, CaseResult]] = {}
        self.metrics: dict[str, list[MetricValue]] = {}
        self.comparisons: dict[str, list[Comparison]] = {}

    def create(self, experiment: Experiment) -> Experiment:
        self.rows[experiment.id] = experiment
        return experiment

    def get(self, experiment_id: str) -> Experiment | None:
        return self.rows.get(experiment_id)

    def recent(self, limit: int = 50) -> list[Experiment]:
        return list(reversed(self.rows.values()))[:limit]

    def claim(self, experiment_id: str, worker: str, now: datetime) -> bool:
        current = self.rows.get(experiment_id)
        holder = self.claims.get(experiment_id)
        lapsed = current is not None and current.status == "running" and holder is not None and now - holder[1] > STALE_AFTER
        if current is None or not (current.status in CLAIMABLE or lapsed):
            return False
        self.claims[experiment_id] = (worker, now)
        self.rows[experiment_id] = current.model_copy(update={"status": "running", "started_at": current.started_at or now.isoformat()})
        return True

    def heartbeat(self, experiment_id: str, worker: str, now: datetime) -> None:
        if self.claims.get(experiment_id, ("",))[0] == worker:
            self.claims[experiment_id] = (worker, now)

    def stalled(self, experiment_id: str, now: datetime) -> bool:
        """Running, but its worker has not beaten for STALE_AFTER: it is gone, and the run can be resumed."""
        current, holder = self.rows.get(experiment_id), self.claims.get(experiment_id)
        return bool(current and current.status == "running" and holder and now - holder[1] > STALE_AFTER)

    def update(self, experiment_id: str, **changes) -> Experiment:
        self.rows[experiment_id] = self.rows[experiment_id].model_copy(update=changes)
        return self.rows[experiment_id]

    def add_case(self, case: CaseResult) -> bool:
        cases = self.cases.setdefault(case.experiment_id, {})
        if case_key(case) in cases:
            return False
        cases[case_key(case)] = case
        return True

    def cases_of(self, experiment_id: str) -> list[CaseResult]:
        return list(self.cases.get(experiment_id, {}).values())

    def cost_of(self, experiment_id: str) -> float:
        return sum(case.cost_usd or 0.0 for case in self.cases_of(experiment_id))

    def count_of(self, experiment_id: str) -> int:
        return len(self.cases.get(experiment_id, {}))

    def save_results(self, experiment_id: str, metrics: list[MetricValue], comparisons: list[Comparison]) -> None:
        self.metrics[experiment_id], self.comparisons[experiment_id] = metrics, comparisons

    def results_of(self, experiment_id: str) -> tuple[list[MetricValue], list[Comparison]]:
        return self.metrics.get(experiment_id, []), self.comparisons.get(experiment_id, [])


class PostgresExperiments:
    """Rows in the research schema. Same answers as MemoryExperiments."""

    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def create(self, e: Experiment) -> Experiment:
        self.connection.execute(f"INSERT INTO research.experiments ({EXPERIMENT_COLUMNS}) VALUES ({', '.join(['%s'] * 18)})",
                                (e.id, e.paper, e.pack_id, e.prereg_id, e.source, e.benchmark, e.conditions, e.seeds, e.trials, Jsonb(e.models), e.budget_usd,
                                 e.config_sha256, e.git_commit, e.status, None, None, None, Jsonb(e.notes)))
        return self.get(e.id)

    def get(self, experiment_id: str) -> Experiment | None:
        if not is_uuid(experiment_id):
            return None
        row = self.connection.execute(f"SELECT {EXPERIMENT_COLUMNS} FROM research.experiments WHERE id = %s", (experiment_id,)).fetchone()
        return as_experiment(row) if row else None

    def recent(self, limit: int = 50) -> list[Experiment]:
        rows = self.connection.execute(f"SELECT {EXPERIMENT_COLUMNS} FROM research.experiments ORDER BY coalesce(started_at, 'infinity') DESC, id LIMIT %s", (limit,))
        return [as_experiment(row) for row in rows]

    def claim(self, experiment_id: str, worker: str, now: datetime) -> bool:
        """One statement: of two workers asking at once, one gets the row back."""
        if not is_uuid(experiment_id):
            return False
        row = self.connection.execute(
            """UPDATE research.experiments SET status = 'running', worker_id = %s, heartbeat_at = %s, started_at = coalesce(started_at, %s)
               WHERE id = %s AND (status = ANY(%s) OR (status = 'running' AND heartbeat_at < %s)) RETURNING id""",
            (worker, now, now, experiment_id, list(CLAIMABLE), now - STALE_AFTER)).fetchone()
        return row is not None

    def stalled(self, experiment_id: str, now: datetime) -> bool:
        row = self.connection.execute("SELECT status = 'running' AND heartbeat_at < %s FROM research.experiments WHERE id = %s", (now - STALE_AFTER, experiment_id)).fetchone()
        return bool(row and row[0])

    def heartbeat(self, experiment_id: str, worker: str, now: datetime) -> None:
        self.connection.execute("UPDATE research.experiments SET heartbeat_at = %s WHERE id = %s AND worker_id = %s", (now, experiment_id, worker))

    def update(self, experiment_id: str, **changes) -> Experiment:
        values = {key: Jsonb(value) if key == "notes" else value for key, value in changes.items()}
        assignments = ", ".join(f"{key} = %({key})s" for key in values)  # keys are Experiment field names, never input
        self.connection.execute(f"UPDATE research.experiments SET {assignments} WHERE id = %(experiment_id)s", {**values, "experiment_id": experiment_id})
        return self.get(experiment_id)

    def add_case(self, c: CaseResult) -> bool:
        inserted = self.connection.execute(f"INSERT INTO research.case_results ({CASE_COLUMNS}) VALUES ({', '.join(['%s'] * 14)}) ON CONFLICT DO NOTHING",
                                           (c.experiment_id, c.condition, c.seed, c.trial, c.case_id, c.correlation_id, Jsonb(c.outcome), c.passed,
                                            c.latency_ms, c.tokens_in, c.tokens_out, c.cost_usd, c.trace_uri, c.error)).rowcount
        return inserted == 1

    def cases_of(self, experiment_id: str) -> list[CaseResult]:
        rows = self.connection.execute(f"SELECT {CASE_COLUMNS} FROM research.case_results WHERE experiment_id = %s ORDER BY condition, seed, trial, case_id", (experiment_id,))
        return [CaseResult(**dict(zip([c.strip() for c in CASE_COLUMNS.split(",")], (str(r[0]), *r[1:])))) for r in rows]

    def count_of(self, experiment_id: str) -> int:
        return self.connection.execute("SELECT count(*) FROM research.case_results WHERE experiment_id = %s", (experiment_id,)).fetchone()[0]

    def cost_of(self, experiment_id: str) -> float:
        return float(self.connection.execute("SELECT coalesce(sum(cost_usd), 0) FROM research.case_results WHERE experiment_id = %s", (experiment_id,)).fetchone()[0])

    def save_results(self, experiment_id: str, metrics: list[MetricValue], comparisons: list[Comparison]) -> None:
        """Replace the experiment's results in one transaction, so a reader never sees half of them."""
        with self.connection.transaction():
            self.connection.execute("DELETE FROM research.metric_values WHERE experiment_id = %s", (experiment_id,))
            self.connection.execute("DELETE FROM research.comparisons WHERE experiment_id = %s", (experiment_id,))
            for m in metrics:
                self.connection.execute("INSERT INTO research.metric_values VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
                                        (m.experiment_id, m.metric_key, m.condition, m.value, m.unit, m.n, m.ci_low, m.ci_high, m.ci_level, m.provenance))
            for c in comparisons:
                self.connection.execute("INSERT INTO research.comparisons VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (c.experiment_id, c.hypothesis_id, c.metric_key, c.condition_a, c.condition_b, c.effect, c.ci_low, c.ci_high,
                                         c.test, c.statistic, c.p_value, c.p_adjusted, c.verdict, c.diagnosis_stage))

    def results_of(self, experiment_id: str) -> tuple[list[MetricValue], list[Comparison]]:
        metric_rows = self.connection.execute("SELECT * FROM research.metric_values WHERE experiment_id = %s ORDER BY metric_key, condition", (experiment_id,)).fetchall()
        comparison_rows = self.connection.execute("SELECT * FROM research.comparisons WHERE experiment_id = %s ORDER BY hypothesis_id", (experiment_id,)).fetchall()
        metrics = [MetricValue(experiment_id=str(r[0]), metric_key=r[1], condition=r[2], value=r[3], unit=r[4], n=r[5], ci_low=r[6], ci_high=r[7], ci_level=r[8], provenance=r[9]) for r in metric_rows]
        comparisons = [Comparison(experiment_id=str(r[0]), hypothesis_id=r[1], metric_key=r[2], condition_a=r[3], condition_b=r[4], effect=r[5], ci_low=r[6], ci_high=r[7],
                                  test=r[8], statistic=r[9], p_value=r[10], p_adjusted=r[11], verdict=r[12], diagnosis_stage=r[13]) for r in comparison_rows]
        return metrics, comparisons


def as_experiment(row: tuple) -> Experiment:
    names = [c.strip() for c in EXPERIMENT_COLUMNS.split(",")]
    values = dict(zip(names, row))
    times = {key: values[key].isoformat() if values[key] else None for key in ("started_at", "finished_at")}
    ids = {key: str(values[key]) if values[key] else None for key in ("id", "pack_id", "prereg_id")}
    return Experiment(**{**values, **times, **ids, "budget_usd": float(values["budget_usd"]), "cost_usd": float(values["cost_usd"]) if values["cost_usd"] is not None else None})


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
