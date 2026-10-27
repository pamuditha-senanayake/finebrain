# contracts.py: the Research Lab's shapes. Snapshot, metric and verdict mirror frontend/contracts/research.ts (camelCase);
# the rest mirror the research schema's rows (store.py). Old snapshots without provenance still load, as sample.
# Used by: research/routes.py, later the runner and results. Uses: api/ui_models.py (UiModel). Product code never imports this.
from typing import Literal

from pydantic import Field

from app.api.ui_models import UiModel

# Config
Provenance = Literal["field", "lab", "benchmark", "reference", "sample"]
Unit = Literal["ratio", "percent", "ms", "count", "usd", "tokens"]
Paper = Literal["skills", "policies", "security", "integration"]
PackKind = Literal["freshness", "policy_drift", "skills", "security", "integration"]
VerdictKind = Literal["supported", "not_supported", "invalid_run"]
ExperimentSource = Literal["lab", "benchmark"]
Comparator = Literal["at_least", "at_most", "below", "above"]
StatTest = Literal["exact_mcnemar", "paired_bootstrap", "wilson", "rule_of_three", "bootstrap_mean"]  # each one is in stats.py
ExperimentStatus = Literal["draft", "estimated", "running", "paused", "budget_reached", "finished", "failed", "invalid_run"]
EXPORTABLE: frozenset[str] = frozenset({"field", "lab", "benchmark", "reference"})  # a sample value is never a result


class ResearchModel(UiModel):
    def ui(self) -> dict:
        """Unset fields are left out, because zod's optional() refuses null."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# --- Shown in the console (research.ts)

class Point(ResearchModel):
    x: str | float
    y: float


class Interval(ResearchModel):
    low: float
    high: float
    level: float


class ResearchMetric(ResearchModel):
    key: str
    label: str
    definition: str
    value: float
    unit: Unit
    condition: str
    series: list[Point]
    provenance: Provenance = "sample"  # a snapshot written before provenance existed was mock data
    n: int | None = None
    ci: Interval | None = None
    experiment_id: str | None = None


class ResearchVerdict(ResearchModel):
    hypothesis_id: str
    metric_key: str
    threshold: str
    observed: str
    verdict: VerdictKind
    diagnosis_stage: int | None = None
    test: str
    p_adjusted: float | None = None


class ResearchSnapshot(ResearchModel):
    paper: Paper
    title: str
    is_sample: bool
    source: str
    taken_at: str
    metrics: list[ResearchMetric]
    verdicts: list[ResearchVerdict] = Field(default_factory=list)
    prereg_id: str | None = None
    prereg_sha256: str | None = None


# --- Rows of the research schema (store.py)

class Hypothesis(ResearchModel):
    """One condition: the threshold applies to its value. Two: to the first minus the second (ratios, so 10 points is 0.10)."""
    id: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    metric: str = Field(pattern=r"^[a-z0-9_]+$")
    comparator: Comparator
    threshold: float
    conditions: list[str] = Field(min_length=1, max_length=2)
    test: StatTest
    alpha: float = Field(default=0.05, gt=0, le=0.5)
    diagnosis_stage: int | None = Field(default=None, ge=1, le=4)


class Pack(ResearchModel):
    id: str
    kind: PackKind
    name: str
    version: str
    sha256: str
    manifest: dict
    audit: dict
    uploaded_by: str
    uploaded_at: str | None = None


class Preregistration(ResearchModel):
    id: str
    paper: Paper
    title: str
    hypotheses: list[Hypothesis]
    sha256: str
    locked_at: str | None = None  # once set, the row never changes again (the lock trigger in store.py)
    locked_by: str | None = None


class Experiment(ResearchModel):
    id: str
    paper: Paper
    pack_id: str | None = None
    prereg_id: str | None = None
    source: ExperimentSource
    benchmark: str | None = None
    conditions: list[str]
    seeds: list[int]
    trials: int
    models: dict
    budget_usd: float
    config_sha256: str
    git_commit: str
    status: ExperimentStatus = "draft"
    started_at: str | None = None
    finished_at: str | None = None
    cost_usd: float | None = None


class CaseResult(ResearchModel):
    experiment_id: str
    condition: str
    seed: int
    trial: int
    case_id: str
    correlation_id: str | None = None  # links the case to the product's run records and traces
    outcome: dict
    passed: bool | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    trace_uri: str | None = None
    error: str | None = None


class MetricValue(ResearchModel):
    experiment_id: str
    metric_key: str
    condition: str
    value: float
    unit: Unit
    n: int
    ci_low: float | None = None
    ci_high: float | None = None
    ci_level: float | None = None
    provenance: Provenance


class Comparison(ResearchModel):
    experiment_id: str
    hypothesis_id: str
    metric_key: str
    condition_a: str
    condition_b: str
    effect: float
    ci_low: float | None = None
    ci_high: float | None = None
    test: str
    statistic: float | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    verdict: VerdictKind
    diagnosis_stage: int | None = None


class ReferenceResult(ResearchModel):
    id: str
    benchmark: str
    metric_key: str
    value: float
    model: str
    source_title: str
    source_url: str
    peer_reviewed: bool
    reported_on: str
    note: str | None = None
