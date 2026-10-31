"""Pure helpers for building the retrieval gold set (no database, no I/O)."""

import random
from collections import defaultdict


def sibling_issues(candidates):
    """Map each issue to the other issues fixed by any of the same PRs.

    The issue itself is never its own sibling: otherwise the sibling task
    would be trivially solved by retrieving the query issue.
    """
    issues_by_pr = defaultdict(set)
    for issue in candidates:
        for pr_number in issue["gold_pr_ids"]:
            issues_by_pr[pr_number].add(issue["number"])

    siblings = {}
    for issue in candidates:
        related = set()
        for pr_number in issue["gold_pr_ids"]:
            related |= issues_by_pr[pr_number]
        related.discard(issue["number"])
        siblings[issue["number"]] = sorted(related)
    return siblings


def stratified_sample(issue_numbers, siblings, size, min_with_siblings, seed):
    """Random sample that guarantees enough sibling cases.

    Only ~10% of issues have siblings, so a plain random sample would leave
    the sibling task with too few cases to measure. A fixed seed makes the
    gold set reproducible: same inputs, same file.
    """
    rng = random.Random(seed)
    with_siblings = sorted(n for n in issue_numbers if siblings[n])
    without = sorted(n for n in issue_numbers if not siblings[n])

    picked = rng.sample(with_siblings, min(min_with_siblings, len(with_siblings)))
    picked += rng.sample(without, min(size - len(picked), len(without)))
    return sorted(picked)
