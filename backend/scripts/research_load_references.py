# research_load_references.py: puts the security paper's outside numbers into research.reference_results, the same rows
# again when run again (each row's id comes from what it is). PhantomPolicy's data has no public link yet, so its rows are the
# paper's own table values; AgentDojo's rows are the Lab's run of the public banking suite (scripts/research_agentdojo.py).
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
AGENTDOJO = {"source_title": "Finebrain Lab run of AgentDojo, important_instructions attack", "source_url": "https://github.com/ethz-spylab/agentdojo", "peer_reviewed": False}  # the suite is published; this run is ours
METRIC_OF = {"attack_success": "attack_success_rate", "utility": "task_success", "utility_attacked": "task_success_under_attack"}
DEFENSE_WORDS = {"none": "No defense", "finebrain": "Finebrain's rule at the call"}


def rows_from(agentdojo: dict | None, reported_on: str) -> list[dict]:
    found = [{**PHANTOM, "metric_key": m, "value": v, "model": model, "note": note} for m, v, model, note in PHANTOM_ROWS]
    for defense in ("none", "finebrain") if agentdojo else ():
        for key, metric in METRIC_OF.items():
            got = agentdojo[defense][key]
            found.append({**AGENTDOJO, "benchmark": f"AgentDojo {agentdojo['suite']}", "metric_key": metric, "value": got["value"], "model": agentdojo["model"],
                          "reported_on": reported_on, "note": f"{DEFENSE_WORDS[defense]}, {round(got['value'] * got['n'])} of {got['n']}"})
    return found


def load(rows: list[dict]) -> int:
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
    parser.add_argument("--on", default="2026-10-27", help="the day the Lab ran AgentDojo")
    args = parser.parse_args()
    print(load(rows_from(json.loads(open(args.agentdojo).read()) if args.agentdojo else None, args.on)), "rows")
