# store.py: the Research Lab's own Postgres schema, `research`, apart from every product table. A locked preregistration
# can never change or go (a trigger, so no code path can move a threshold after the first run).
# Used by: research/routes.py, tests/test_research_schema.py. Uses: store_postgres.py (the database address only).
import psycopg

from app.pipeline.store_postgres import DATABASE_URL

# Config
SCHEMA_LOCK = 72_000_001  # advisory lock id: two workers starting at once create the schema one after the other
KINDS = "'freshness', 'policy_drift', 'skills', 'security', 'integration'"
PAPERS = "'skills', 'policies', 'security', 'integration'"
PROVENANCES = "'field', 'lab', 'benchmark', 'reference', 'sample'"
VERDICTS = "'supported', 'not_supported', 'invalid_run'"
SCHEMA = f"""
CREATE SCHEMA IF NOT EXISTS research;
CREATE TABLE IF NOT EXISTS research.packs (
    id uuid PRIMARY KEY, kind text NOT NULL CHECK (kind IN ({KINDS})),
    name text NOT NULL, version text NOT NULL,
    sha256 text NOT NULL UNIQUE, manifest jsonb NOT NULL,
    audit jsonb NOT NULL,
    uploaded_by text NOT NULL, uploaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS research.preregistrations (
    id uuid PRIMARY KEY, paper text NOT NULL CHECK (paper IN ({PAPERS})), title text NOT NULL,
    hypotheses jsonb NOT NULL,
    sha256 text NOT NULL, locked_at timestamptz, locked_by text,
    CHECK ((locked_at IS NULL) = (locked_by IS NULL))
);
CREATE TABLE IF NOT EXISTS research.experiments (
    id uuid PRIMARY KEY, paper text NOT NULL CHECK (paper IN ({PAPERS})),
    pack_id uuid REFERENCES research.packs, prereg_id uuid REFERENCES research.preregistrations,
    source text NOT NULL CHECK (source IN ('lab', 'benchmark')), benchmark text,
    conditions text[] NOT NULL, seeds int[] NOT NULL, trials int NOT NULL CHECK (trials > 0),
    models jsonb NOT NULL, budget_usd numeric NOT NULL CHECK (budget_usd >= 0),
    config_sha256 text NOT NULL, git_commit text NOT NULL,
    status text NOT NULL, started_at timestamptz, finished_at timestamptz, cost_usd numeric
);
ALTER TABLE research.experiments ADD COLUMN IF NOT EXISTS worker_id text;
ALTER TABLE research.experiments ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE research.experiments ADD COLUMN IF NOT EXISTS notes jsonb NOT NULL DEFAULT '{{}}';
CREATE TABLE IF NOT EXISTS research.case_results (
    experiment_id uuid REFERENCES research.experiments ON DELETE CASCADE,
    condition text, seed int, trial int, case_id text,
    correlation_id text, outcome jsonb NOT NULL,
    passed boolean, latency_ms int, tokens_in int, tokens_out int, cost_usd numeric,
    trace_uri text, error text,
    PRIMARY KEY (experiment_id, condition, seed, trial, case_id)
);
CREATE TABLE IF NOT EXISTS research.metric_values (
    experiment_id uuid REFERENCES research.experiments ON DELETE CASCADE, metric_key text, condition text,
    value double precision, unit text, n int,
    ci_low double precision, ci_high double precision, ci_level double precision,
    provenance text NOT NULL CHECK (provenance IN ({PROVENANCES})), computed_at timestamptz DEFAULT now(),
    PRIMARY KEY (experiment_id, metric_key, condition)
);
CREATE TABLE IF NOT EXISTS research.comparisons (
    experiment_id uuid REFERENCES research.experiments ON DELETE CASCADE, hypothesis_id text, metric_key text,
    condition_a text, condition_b text, effect double precision,
    ci_low double precision, ci_high double precision,
    test text, statistic double precision, p_value double precision, p_adjusted double precision,
    verdict text NOT NULL CHECK (verdict IN ({VERDICTS})), diagnosis_stage int,
    PRIMARY KEY (experiment_id, hypothesis_id, metric_key, condition_a, condition_b)
);
CREATE TABLE IF NOT EXISTS research.reference_results (
    id uuid PRIMARY KEY, benchmark text NOT NULL, metric_key text NOT NULL, value double precision NOT NULL,
    model text, source_title text NOT NULL, source_url text NOT NULL, peer_reviewed boolean NOT NULL,
    reported_on date, note text
);
CREATE OR REPLACE FUNCTION research.keep_locked_prereg() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.locked_at IS NOT NULL THEN
        RAISE EXCEPTION 'preregistration_locked' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER prereg_locked BEFORE UPDATE OR DELETE ON research.preregistrations
    FOR EACH ROW EXECUTE FUNCTION research.keep_locked_prereg();
"""
TABLES = ["packs", "preregistrations", "experiments", "case_results", "metric_values", "comparisons", "reference_results"]


# --- Schema

def ensure_schema(connection: psycopg.Connection) -> None:
    """Create the research schema once. Safe to run again, and from two workers at the same time."""
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
        connection.execute(SCHEMA)


def schema_ready(connection: psycopg.Connection) -> bool:
    """True when every research table exists."""
    names = [f"research.{table}" for table in TABLES]
    row = connection.execute("SELECT bool_and(to_regclass(name) IS NOT NULL) FROM unnest(%s::text[]) AS name", (names,)).fetchone()
    return bool(row[0])


def connect(url: str = DATABASE_URL) -> psycopg.Connection:
    """A connection with the research schema in place. Raises psycopg.OperationalError when Postgres is down."""
    connection = psycopg.connect(url, autocommit=True, connect_timeout=3)
    ensure_schema(connection)
    return connection
