# store_patterns.py: the living memory's patterns and areas (stage 5a). Each area keeps at most PATTERN_BUDGET patterns,
# read by area and key, never by listing everything; each pattern counts its traces per week, and a redelivered trace
# never counts twice. The area registry says which areas a company uses; Other is always on. The nightly tidy (5d) merges
# near-identical patterns and removes idle ones. PostgresPatterns and its twin.
# Used by: stages_memory.py, tests/test_memory_stores.py, tests/test_memory_skeleton.py. Uses: nothing local.
import hashlib
from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

# Config: Docs/CB_Living_Memory_Architecture.md sections 2, 4 and 13
PATTERN_BUDGET = 50
EXAMPLES_PER_PATTERN = 5
ALWAYS_ON = "general"
SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_patterns (
    tenant_id  text  NOT NULL,
    area       text  NOT NULL,
    key        text  NOT NULL,
    pattern_id text  NOT NULL,
    steps      jsonb NOT NULL,
    total      integer NOT NULL DEFAULT 0,
    examples   jsonb NOT NULL DEFAULT '[]',
    PRIMARY KEY (tenant_id, area, key)
);
CREATE UNIQUE INDEX IF NOT EXISTS memory_patterns_id ON memory_patterns (tenant_id, pattern_id);
CREATE TABLE IF NOT EXISTS memory_pattern_cases (
    tenant_id  text NOT NULL,
    pattern_id text NOT NULL,
    week       date NOT NULL,
    trace_id   text NOT NULL,
    PRIMARY KEY (tenant_id, pattern_id, trace_id)
);
CREATE INDEX IF NOT EXISTS memory_pattern_cases_week ON memory_pattern_cases (tenant_id, pattern_id, week);
CREATE TABLE IF NOT EXISTS memory_areas (
    tenant_id text    NOT NULL,
    area      text    NOT NULL,
    enabled   boolean NOT NULL,
    PRIMARY KEY (tenant_id, area)
);
"""


@dataclass
class Pattern:
    pattern_id: str
    key: str
    steps: list[str]
    count: int = 0
    examples: list[str] = field(default_factory=list)


def pattern_id_of(tenant_id: str, key: str) -> str:
    """The same key always gets the same id, so two workers adding one pattern at once agree on it."""
    return "pt-" + hashlib.sha256(f"{tenant_id}|{key}".encode()).hexdigest()[:12]


class MemoryPatterns:
    """The in-memory twin of PostgresPatterns."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.areas: dict[str, dict[str, Pattern]] = {}
        self.cases: dict[tuple[str, str], date] = {}  # (pattern_id, trace_id) to its week
        self.switched: dict[str, bool] = {}

    def area_patterns(self, area: str) -> dict[str, Pattern]:
        return self.areas.get(area, {})

    def add(self, area: str, key: str, steps: list[str]) -> Pattern | None:
        """A new pattern, or the existing one with this key. None once the area holds its budget."""
        patterns = self.areas.setdefault(area, {})
        if key not in patterns and len(patterns) >= PATTERN_BUDGET:
            return None
        return patterns.setdefault(key, Pattern(pattern_id_of(self.tenant_id, key), key, steps))

    def count(self, pattern: Pattern, week: date, trace_id: str) -> bool:
        """Count one trace in its week. False when it was already counted."""
        if (pattern.pattern_id, trace_id) in self.cases:
            return False
        self.cases[(pattern.pattern_id, trace_id)] = week
        pattern.count += 1
        pattern.examples = ([trace_id] + pattern.examples)[:EXAMPLES_PER_PATTERN]
        return True

    def weeks(self, pattern_id: str) -> dict[date, int]:
        weeks: dict[date, int] = {}
        for (pid, _), week in self.cases.items():
            if pid == pattern_id:
                weeks[week] = weeks.get(week, 0) + 1
        return dict(sorted(weeks.items()))

    def merge(self, area: str, survivor_key: str, merged_key: str) -> int:
        """Fold one pattern into another (the nightly tidy): its traces count for the survivor, never twice. Returns traces moved."""
        patterns = self.areas.get(area, {})
        survivor, merged = patterns.get(survivor_key), patterns.pop(merged_key, None)
        if not survivor or not merged:
            return 0
        moved = 0
        for _, trace_id in [key for key in self.cases if key[0] == merged.pattern_id]:
            week = self.cases.pop((merged.pattern_id, trace_id))
            moved += (survivor.pattern_id, trace_id) not in self.cases  # a trace both counted stays counted once
            self.cases.setdefault((survivor.pattern_id, trace_id), week)
        survivor.count = sum(1 for key in self.cases if key[0] == survivor.pattern_id)
        survivor.examples = (survivor.examples + merged.examples)[:EXAMPLES_PER_PATTERN]
        return moved

    def remove(self, area: str, key: str) -> Pattern | None:
        """Take a pattern out of its area with its counts (the tidy archived it first), freeing room in the budget."""
        pattern = self.areas.get(area, {}).pop(key, None)
        if pattern:
            self.cases = {k: week for k, week in self.cases.items() if k[0] != pattern.pattern_id}
        return pattern

    def area_on(self, area: str) -> bool:
        return area == ALWAYS_ON or self.switched.get(area, True)

    def switch_area(self, area: str, enabled: bool) -> bool:
        """Turn an area on or off for this company. Other can never be turned off: it catches what fits nowhere."""
        if area == ALWAYS_ON and not enabled:
            return False
        self.switched[area] = enabled
        return True


class PostgresPatterns:
    """The patterns in Postgres. Same answers as MemoryPatterns."""

    def __init__(self, connection: psycopg.Connection, tenant_id: str):
        self.connection = connection
        self.tenant_id = tenant_id
        connection.execute(SCHEMA)

    def area_patterns(self, area: str) -> dict[str, Pattern]:
        rows = self.connection.execute("SELECT key, pattern_id, steps, total, examples FROM memory_patterns WHERE tenant_id = %s AND area = %s", (self.tenant_id, area))
        return {key: Pattern(pid, key, steps, total, examples) for key, pid, steps, total, examples in rows}

    def add(self, area: str, key: str, steps: list[str]) -> Pattern | None:
        # One lock per area, held for this transaction, so two workers can never both add the 50th pattern
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{self.tenant_id}|{area}",))
            held = self.connection.execute("SELECT count(*), bool_or(key = %s) FROM memory_patterns WHERE tenant_id = %s AND area = %s", (key, self.tenant_id, area)).fetchone()
            if not held[1] and held[0] >= PATTERN_BUDGET:
                return None
            self.connection.execute("INSERT INTO memory_patterns (tenant_id, area, key, pattern_id, steps) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                    (self.tenant_id, area, key, pattern_id_of(self.tenant_id, key), Jsonb(steps)))
        return self.area_patterns(area)[key]

    def count(self, pattern: Pattern, week: date, trace_id: str) -> bool:
        # Step 1: remember the trace; a redelivery stops here
        added = self.connection.execute("INSERT INTO memory_pattern_cases VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", (self.tenant_id, pattern.pattern_id, week, trace_id)).rowcount
        if not added:
            return False
        # Step 2: one more for the pattern, and the trace becomes its newest example
        row = self.connection.execute(
            """UPDATE memory_patterns SET total = total + 1, examples = (jsonb_build_array(%s::text) || examples) - 5
               WHERE tenant_id = %s AND pattern_id = %s RETURNING total, examples""", (trace_id, self.tenant_id, pattern.pattern_id)).fetchone()
        pattern.count, pattern.examples = row
        return True

    def weeks(self, pattern_id: str) -> dict[date, int]:
        rows = self.connection.execute(
            "SELECT week, count(*) FROM memory_pattern_cases WHERE tenant_id = %s AND pattern_id = %s GROUP BY week ORDER BY week", (self.tenant_id, pattern_id))
        return {week: count for week, count in rows}

    def merge(self, area: str, survivor_key: str, merged_key: str) -> int:
        # One transaction: the merged pattern's cases move and its row goes, or nothing changes
        with self.connection.transaction():
            patterns = self.area_patterns(area)
            survivor, merged = patterns.get(survivor_key), patterns.get(merged_key)
            if not survivor or not merged:
                return 0
            # A trace both counted stays counted once: move the others, drop the rest, then recount from the cases themselves
            moved = self.connection.execute(
                """UPDATE memory_pattern_cases m SET pattern_id = %s WHERE m.tenant_id = %s AND m.pattern_id = %s
                   AND NOT EXISTS (SELECT 1 FROM memory_pattern_cases s WHERE s.tenant_id = m.tenant_id AND s.pattern_id = %s AND s.trace_id = m.trace_id)""",
                (survivor.pattern_id, self.tenant_id, merged.pattern_id, survivor.pattern_id)).rowcount
            self.connection.execute("DELETE FROM memory_pattern_cases WHERE tenant_id = %s AND pattern_id = %s", (self.tenant_id, merged.pattern_id))
            self.connection.execute(
                """UPDATE memory_patterns SET examples = %s,
                   total = (SELECT count(*) FROM memory_pattern_cases WHERE tenant_id = %s AND pattern_id = %s) WHERE tenant_id = %s AND pattern_id = %s""",
                (Jsonb((survivor.examples + merged.examples)[:EXAMPLES_PER_PATTERN]), self.tenant_id, survivor.pattern_id, self.tenant_id, survivor.pattern_id))
            self.connection.execute("DELETE FROM memory_patterns WHERE tenant_id = %s AND pattern_id = %s", (self.tenant_id, merged.pattern_id))
        return moved

    def remove(self, area: str, key: str) -> Pattern | None:
        with self.connection.transaction():
            pattern = self.area_patterns(area).get(key)
            if pattern:
                self.connection.execute("DELETE FROM memory_pattern_cases WHERE tenant_id = %s AND pattern_id = %s", (self.tenant_id, pattern.pattern_id))
                self.connection.execute("DELETE FROM memory_patterns WHERE tenant_id = %s AND pattern_id = %s", (self.tenant_id, pattern.pattern_id))
        return pattern

    def area_on(self, area: str) -> bool:
        if area == ALWAYS_ON:
            return True
        row = self.connection.execute("SELECT enabled FROM memory_areas WHERE tenant_id = %s AND area = %s", (self.tenant_id, area)).fetchone()
        return row is None or row[0]

    def switch_area(self, area: str, enabled: bool) -> bool:
        if area == ALWAYS_ON and not enabled:
            return False
        self.connection.execute("INSERT INTO memory_areas VALUES (%s, %s, %s) ON CONFLICT (tenant_id, area) DO UPDATE SET enabled = EXCLUDED.enabled", (self.tenant_id, area, enabled))
        return True
