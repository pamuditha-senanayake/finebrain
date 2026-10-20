# policy_follow_up.py: step 14, after a fact change merges. A Studio policy whose wording still states the old value (the
# refund policy saying 30 days once the refund window fact says 45) is never rewritten silently: the librarian drafts the
# matching Studio change and it waits for the policy's DRI, like any Studio change. Merged fact changes from before are
# followed up on start. Used by: studio_approvals.py (merge), vault_routes.py (start-up). Uses: studio_approvals.py, studio_review.py.
import re

from app.api import studio_approvals  # imported as a module: studio_approvals imports this file too
from app.api.studio_changes import ChangeRecord
from app.api.studio_review import review
from app.api.studio_state import Studio
from app.pipeline.observe import log_event

# Config
LIBRARIAN = "librarian"  # the drafter, so the DRI may approve; nobody approves their own change
AMOUNT = re.compile(r"(\d+(?:[.,]\d+)*)\s*(day|week|month|year)s?", re.IGNORECASE)
TOPIC_WORD = 4  # predicate words this long name the topic: refund_request_window is about refund, request, window


# --- Where a policy states the old value

def phrase_of(raw: str) -> re.Pattern:
    """How a policy may write a value: "30 days" also reads "30-day" or "30 day"; anything else as written."""
    found = AMOUNT.fullmatch(raw.strip())
    if found:
        return re.compile(rf"\b{re.escape(found[1])}[\s-]*{found[2]}s?\b", re.IGNORECASE)
    return re.compile(re.escape(raw.strip()), re.IGNORECASE)


def rewritten(text: str, old_raw: str, new_raw: str) -> str:
    """The text with the old value replaced, keeping its form ("30-day" becomes "45-day") when only the number changed."""
    old, new = AMOUNT.fullmatch(old_raw.strip()), AMOUNT.fullmatch(new_raw.strip())
    if old and new and old[2].lower() == new[2].lower():
        return phrase_of(old_raw).sub(lambda m: m[0].replace(old[1], new[1], 1), text)
    return phrase_of(old_raw).sub(lambda m: new_raw.strip(), text)


def stating(st: Studio, predicate: str, old_raw: str) -> list[dict]:
    """Active policies about the fact's topic (a predicate word in their name or rule kind) whose statement states the old value."""
    topic = {word for word in predicate.lower().split("_") if len(word) >= TOPIC_WORD}
    phrase = phrase_of(old_raw)
    return [item for item in st.items.values() if item["kind"] == "policy" and item["status"] == "active"
            and topic & set(re.findall(r"[a-z]+", f"{item['name']} {item['fields'].get('ruleKind', '')}".lower()))
            and phrase.search(str(item["fields"].get("statement", "")))]


def patch_for(policy: dict, old_raw: str, new_raw: str) -> dict:
    """The new statement, and the day limit too when it held the old number of days."""
    fields = {"statement": rewritten(str(policy["fields"]["statement"]), old_raw, new_raw)}
    old, new = AMOUNT.fullmatch(old_raw.strip()), AMOUNT.fullmatch(new_raw.strip())
    if old and new and old[2].lower() == new[2].lower() == "day" and str(policy["fields"].get("param.days")) == old[1]:
        fields["param.days"] = int(new[1])
    return fields


# --- Drafting the change for the policy's DRI

def draft_for(lane, st: Studio, policy: dict, label: str, old_raw: str, new_raw: str, fact_cr: str) -> str:
    """A Studio change request, drafted by the librarian and reviewed like any other. Returns its id."""
    change = {"intent": "update", "kind": "policy", "targetId": policy["id"], "workflowId": policy["workflowId"],
              "patch": {"fields": patch_for(policy, old_raw, new_raw)}}
    proposal = review(lane, policy["dri"], change, st)  # the review needs a person for its authority line; the DRI is who decides
    proposal = {**proposal, "title": f"Match the new {label}: {policy['name']}"}
    note = f"The {label} fact changed from {old_raw} to {new_raw} ({fact_cr}). {policy['name']} still said {old_raw}."
    return studio_approvals.open_change(lane, LIBRARIAN, change, proposal, note)["changeRequestId"]


def flag(lane, record) -> list[str] | None:
    """After a fact change merges: draft a change for each policy that states the old value. None when it failed, so start-up tries again.
    It never undoes the merge: the fact is ground truth already."""
    closed, added = record.drafts[0].fields, record.drafts[1].fields
    old_raw, new_raw, label = closed["value"]["raw"], added["value"]["raw"], closed["predicate"].replace("_", " ")
    try:
        st = Studio.of(lane)
        drafted = [draft_for(lane, st, policy, label, old_raw, new_raw, record.cr_id) for policy in stating(st, closed["predicate"], old_raw)]
    except Exception as error:  # a policy that cannot be drafted is logged; the fact change stays merged
        log_event("S12", "policy_follow_up_failed", cr_id=record.cr_id, error=type(error).__name__)
        return None
    log_event("S12", "policy_follow_up", cr_id=record.cr_id, drafted=len(drafted))
    return drafted


def follow_up_merged(lane) -> int:
    """Start-up: merged fact changes from before this rule, followed up once. Returns how many policy changes were drafted."""
    drafted = 0
    for stored in lane.records.list_kind("change_request"):
        record = ChangeRecord.model_validate(stored)
        if record.kind != "fact" or record.status != "merged" or record.follow_ups is not None:
            continue
        follow_ups = flag(lane, record)
        if follow_ups is not None:
            lane.records.save("change_request", record.cr_id, record.model_copy(update={"follow_ups": follow_ups}))
            drafted += len(follow_ups)
    return drafted
