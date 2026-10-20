# stages_dupes.py: duplicate merging (step 13d), a Distiller job. Open chunks with the same words (whatever the case, spacing
# or punctuation) answer once: the best of each group (highest value, then the earliest) is kept and the others point to it,
# so search skips them. Nothing is deleted: when the kept one is retired or erased, the others answer again.
# Used by: api/distiller.py, api/forget_layers.py (DuplicateLayer), tests/test_dupes.py. Uses: a chunks store.


def merge(lane) -> int:
    """Mark the duplicates of each group. Returns how many were marked."""
    marks = {item_id: group[0] for group in lane.chunks.duplicate_groups() for item_id in group[1:]}
    if marks:
        lane.chunks.mark_duplicates(marks)
    return len(marks)


def reopen(lane, kept_ids: list[str]) -> list[str]:
    """The kept items are going: their duplicates answer again (the next night may merge them anew). Returns what reopened."""
    reopened = lane.chunks.duplicates_of(kept_ids)
    if reopened:
        lane.chunks.mark_duplicates({item_id: None for item_id in reopened})
    return reopened
