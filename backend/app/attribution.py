"""Exact Shapley values for the union of known synthetic-patient exclusions.

This is an exclusion-coverage game, not Trial Pathfinder's survival/hazard-ratio
game. Unknowns never receive exclusion credit. No permutations are sampled.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping

import numpy as np

from .models import AttributionOverlap, Rule, RuleAttribution, ensure_unique_ids

_POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


def shapley_attribution(
    rules: list[Rule],
    masks: Mapping[str, tuple[np.ndarray, np.ndarray]],
    modeled_ids: Collection[str],
) -> list[RuleAttribution]:
    """Split each known excluded patient equally among all their failing rules.

    Masks are (known_failure, unknown), as returned by engine.rule_masks(). Rule
    ordering is canonicalized before arithmetic for reproducible ID-level values.
    """
    ensure_unique_ids(rules)
    modeled = set(modeled_ids)
    active = sorted((r for r in rules if r.id in modeled and r.simulatable and not r.not_applicable),
                    key=lambda r: r.id)
    if not active:
        return []
    f = np.column_stack([np.asarray(masks[r.id][0], dtype=bool)
                         & ~np.asarray(masks[r.id][1], dtype=bool) for r in active])
    multiplicity = f.sum(axis=1)
    weights = np.divide(1.0, multiplicity, out=np.zeros(len(f), dtype=float), where=multiplicity > 0)
    values = f.T @ weights
    total_excluded = int(np.count_nonzero(multiplicity))
    totals = f.sum(axis=0)
    unique = f[multiplicity == 1].sum(axis=0)

    # Exact pair counts across ALL modeled rules, not the engine's top-20 preview.
    # Packed bits avoid allocating a patient-by-rule integer matrix for F.T @ F.
    packed = np.packbits(f, axis=0).T
    overlaps: list[list[AttributionOverlap]] = [[] for _ in active]
    for a in range(len(active)):
        if not totals[a]:
            continue
        for b in range(a + 1, len(active)):
            if not totals[b]:
                continue
            count = int(_POPCOUNT[np.bitwise_and(packed[a], packed[b])].sum(dtype=np.int64))
            if count:
                overlaps[a].append(AttributionOverlap(rule_id=active[b].id, patient_n=count))
                overlaps[b].append(AttributionOverlap(rule_id=active[a].id, patient_n=count))
    result = [RuleAttribution(
        rule_id=r.id, shapley_value=float(values[i]), unique_n=int(unique[i]), total_fail_n=int(totals[i]),
        shapley_share_pct=100 * float(values[i]) / total_excluded if total_excluded else 0.0,
        top_overlaps=sorted(overlaps[i], key=lambda o: (-o.patient_n, o.rule_id))[:3],
    ) for i, r in enumerate(active)]
    return sorted(result, key=lambda a: (-a.shapley_value, a.rule_id))
