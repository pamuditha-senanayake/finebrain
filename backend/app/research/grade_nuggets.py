# grade_nuggets.py: grades an answer by a pack's nuggets, as FiscalQA Pro's own scorer does (scripts/score_nuggets.py in
# rosecymbler/fiscal-fr-bench, MIT): the same arithmetic normalization (thirds, French thousands, decimal comma), then each
# nugget is a regex, an exact string, or a number within a tolerance; "strict" means every required nugget holds. On top,
# the Lab's labels: fresh when the question's own nuggets hold, stale when instead those of another date's question about
# the same article hold (an earlier or later version's value), mixed when both, wrong otherwise. Never a model.
# Used by: research/kinds.py. Uses: nothing local.
import re
import unicodedata

# Config
GRADER_VERSION = "n1"
NUM = re.compile(r"\d+(?:\.\d+)?")  # no sign: tax values are never negative, and list bullets are dashes


def normalize(text: str) -> str:
    """FiscalQA's arithmetic normalization, unchanged: "33 1/3" to 33.3333, "1 370" to 1370, "5,5" to 5.5."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"(\d+)\s*(?:1/3|⅓)", lambda m: f"{int(m.group(1)) + 1/3:.4f}", t)
    t = re.sub(r"(?<=\d)[\s  \.](?=\d{3}\b)", "", t)
    return re.sub(r"(?<=\d),(?=\d)", ".", t)


def holds(nugget, said: str, numbers: list[float]) -> bool:
    if nugget.kind == "regex":
        return re.search(nugget.pattern, said, re.IGNORECASE) is not None
    if nugget.kind == "exact":
        return normalize(nugget.value) in said
    return any(abs(n - nugget.target) <= nugget.tol for n in numbers)


def strict(answer: str, nuggets: list) -> bool:
    """Every required nugget holds (all of them when none is marked required), as FiscalQA scores."""
    said = normalize(answer)
    numbers = [float(x) for x in NUM.findall(said)]
    hits = [holds(n, said, numbers) for n in nuggets]
    required = [hit for hit, n in zip(hits, nuggets) if n.required]
    return bool(nuggets) and (all(required) if required else all(hits))


def grade(answer: str, own: list, others: list[list]) -> str:
    """fresh, stale, mixed or wrong. `others` are the nuggets of the same article's questions at other dates whose values differ."""
    fresh = strict(answer, own)
    stale = any(strict(answer, other) for other in others)
    if fresh and stale:
        return "mixed"
    return "fresh" if fresh else "stale" if stale else "wrong"
