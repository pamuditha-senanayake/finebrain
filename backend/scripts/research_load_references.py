# research_load_references.py: puts the papers' outside numbers into research.reference_results, the same rows again when
# run again (each row's id comes from what it is). PhantomPolicy's data has no public link yet, so its rows are the paper's
# own table values; FiscalQA Pro's are its released report's; AgentDojo's are the Lab's run of the public banking suite
# (scripts/research_agentdojo.py).
#   uv run python scripts/research_load_references.py --agentdojo <results.json>
import argparse
import json
import uuid

from app.research import store

# Config
PHANTOM = {"benchmark": "PhantomPolicy", "source_title": "Wu and Gong, Policy-Invisible Violations in LLM-Based Agents, arXiv 2604.12177 (Tables 5 and 8)",
           "source_url": "https://arxiv.org/abs/2604.12177", "peer_reviewed": False, "reported_on": "2026-04-14"}
PHANTOM_ROWS = [  # (metric, value, model, note): risky cases where the agent took the forbidden action
    ("forbidden_action_rate", 286 / 300, "five models, GPT-5.4 to Claude Opus 4.6", "No enforcement, 286 of 300"),
    ("forbidden_action_rate", 54 / 60, "Claude Sonnet 4.6", "No enforcement, 54 of 60"),
    ("forbidden_action_rate", 122 / 300, "five models, GPT-5.4 to Claude Opus 4.6", "Policy in the prompt, 122 of 300"),
    ("forbidden_action_rate", 0.12, "five models, GPT-5.4 to Claude Opus 4.6", "Sentinel at the call, violations it missed (1 minus its recall)"),
]
FISCAL = {"benchmark": "FiscalQA Pro", "source_title": "Temporal Misgrounding in Legal RAG, arXiv 2608.09393 (its released stats_clustered_report.md, Table 2)",
          "source_url": "https://github.com/rosecymbler/fiscal-fr-bench", "peer_reviewed": False, "reported_on": "2026-08-05"}
FISCAL_ROWS = [  # (metric, value, model, note): FiscalQA's strict score (every required nugget) on its 209 scored temporal questions; its
    # no-retrieval condition (3.0%) is left out, being no retrieval at all
    ("states_current", 0.027, "eleven models", "Current version only (B), pooled"),
    ("states_current", 0.014, "Claude Sonnet 4.6", "Current version only (B)"),
    ("states_current", 0.991, "eleven models", "Gold article in force (C-oracle), pooled"),
    ("states_current", 0.983, "eleven models", "Their retriever in force (C-prod), pooled"),
    ("states_current", 0.990, "Claude Sonnet 4.6", "Their retriever in force (C-prod)"),
]
AGENTDOJO = {"source_title": "Finebrain Lab run of AgentDojo, important_instructions attack", "source_url": "https://github.com/ethz-spylab/agentdojo", "peer_reviewed": False}  # the suite is published; this run is ours
METRIC_OF = {"attack_success": "attack_success_rate", "utility": "task_success", "utility_attacked": "task_success_under_attack"}
DEFENSE_WORDS = {"none": "No defense", "finebrain": "Finebrain's rule at the call"}


TAU3 = {"benchmark": "tau3-bench retail", "source_title": "Finebrain Lab run of tau3-bench retail (tau's own agent and user simulator)",
        "source_url": "https://github.com/sierra-research/tau2-bench", "peer_reviewed": False}


def tau3_rows(tau3: dict | None, reported_on: str) -> list[dict]:
    """pass^1 to pass^n of the Lab's tau3 run (scripts/research_tau3.py), for scale beside the skills paper's own curve."""
    if not tau3:
        return []
    return [{**TAU3, "metric_key": key, "value": got["value"], "model": tau3["model"], "reported_on": reported_on,
             "note": f"{key.replace('pass_hat_', 'pass^')}, {tau3['tasks']} tasks x {tau3['trials']} trials"} for key, got in tau3["curve"].items()]


def rows_from(agentdojo: dict | None, reported_on: str) -> list[dict]:
    found = [{**PHANTOM, "metric_key": m, "value": v, "model": model, "note": note} for m, v, model, note in PHANTOM_ROWS]
    found += [{**FISCAL, "metric_key": m, "value": v, "model": model, "note": note} for m, v, model, note in FISCAL_ROWS]
    for defense in ("none", "finebrain") if agentdojo else ():
        for key, metric in METRIC_OF.items():
            got = agentdojo[defense][key]
            found.append({**AGENTDOJO, "benchmark": f"AgentDojo {agentdojo['suite']}", "metric_key": metric, "value": got["value"], "model": agentdojo["model"],
                          "reported_on": reported_on, "note": f"{DEFENSE_WORDS[defense]}, {round(got['value'] * got['n'])} of {got['n']}"})
    return found


def load(rows: list[dict]) -> int:
    """Each row's id comes from its benchmark, metric, model and the note's first words, so rows must differ in one of them."""
    with store.connect() as connection, connection.transaction():
        for r in rows:
            row_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{r['benchmark']}|{r['metric_key']}|{r['model']}|{r['note'].split(',')[0]}")
            connection.execute("""INSERT INTO research.reference_results VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                  ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value, note = EXCLUDED.note, reported_on = EXCLUDED.reported_on""",
                               (row_id, r["benchmark"], r["metric_key"], r["value"], r["model"], r["source_title"], r["source_url"], r["peer_reviewed"], r["reported_on"], r["note"]))
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentdojo", help="the results JSON scripts/research_agentdojo.py wrote")
    parser.add_argument("--tau3", help="the summary JSON scripts/research_tau3.py wrote")
    parser.add_argument("--on", default="2026-10-27", help="the day the Lab ran AgentDojo")
    parser.add_argument("--tau3-on", default="2026-10-28", help="the day the Lab ran tau3")
    args = parser.parse_args()
    found = rows_from(json.loads(open(args.agentdojo).read()) if args.agentdojo else None, args.on)
    print(load(found + tau3_rows(json.loads(open(args.tau3).read()) if args.tau3 else None, args.tau3_on)), "rows")
