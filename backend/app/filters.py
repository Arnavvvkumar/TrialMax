"""Exploratory PCA of known binary failure patterns, not a clinical independence test."""
from __future__ import annotations

import numpy as np

from .engine import rule_masks
from .models import FilterSummary, HiddenFilter, RedundancyPair, Rule
from .variables import VARIABLES

ORGAN_FUNCTION = {"anc", "platelets", "hemoglobin", "creatinine", "crcl", "egfr", "bilirubin", "ast", "alt"}


def _label(top: list[Rule]) -> str:
    variables = {r.variable for r in top}
    group = ("Organ function" if variables <= ORGAN_FUNCTION else
             "Age and functional status" if variables <= {"age", "ecog"} else "Mixed failure patterns")
    return group + ": " + ", ".join(dict.fromkeys(VARIABLES[r.variable]["label"] for r in top))


def hidden_filters(rules: list[Rule], columns: dict[str, np.ndarray], *, population_n: int | None = None) -> FilterSummary:
    masks = rule_masks(rules, columns, population_n=population_n)
    active, dropped = [], []
    for rule in sorted(rules, key=lambda r: r.id):
        failed, unknown = masks[rule.id]
        if (not rule.simulatable or rule.not_applicable or not (~unknown).any()
                or not failed.any() or failed.all()):
            dropped.append(rule.id)
        else:
            active.append(rule)
    if not active:
        return FilterSummary(dropped_rule_ids=dropped)

    # Keep F boolean and center in bounded blocks. SVD of its centered covariance
    # gives the same principal axes as SVD(F-centered), without allocating a huge U.
    f = np.column_stack([masks[r.id][0] for r in active])
    n, p = f.shape
    counts = f.sum(axis=0).astype(float)
    means = counts / n
    covariance = np.zeros((p, p), dtype=float)
    for offset in range(0, n, 4096):
        centered = f[offset:offset + 4096].astype(float) - means
        covariance += centered.T @ centered
    covariance /= n - 1
    axes, variance, _ = np.linalg.svd(covariance, full_matrices=False)
    variance = np.maximum(variance, 0)
    ratios = variance / variance.sum()
    positive = int((variance > variance[0] * 1e-10).sum())
    k = min(5, positive, int(np.searchsorted(np.cumsum(ratios), 0.85)) + 1)
    components = []
    for i in range(k):
        axis = axes[:, i].copy()
        pivot = int(np.argmax(np.abs(axis)))
        if axis[pivot] < 0:  # fix the arbitrary PCA sign for reproducible presentation
            axis *= -1
        ranking = sorted(range(p), key=lambda j: (-abs(axis[j]), active[j].id))
        top = [active[j] for j in ranking[:3] if abs(axis[j]) >= abs(axis[pivot]) * 0.15]
        components.append(HiddenFilter(component=i + 1, label=_label(top), explained_variance_ratio=float(ratios[i]),
                         loadings={r.id: float(axis[j]) for j, r in enumerate(active)}, top_rule_ids=[r.id for r in top]))

    # Recover exact integer intersections from centered cross-products.
    intersections = np.rint(covariance * (n - 1) + np.outer(counts, counts) / n).astype(np.int64)
    pairs = []
    for a in range(p):
        for b in range(a + 1, p):
            overlap = int(intersections[a, b])
            union = int(counts[a] + counts[b]) - overlap
            jaccard = overlap / union if union else 0
            if jaccard >= 0.5:
                ra, rb = active[a].id, active[b].id
                pairs.append(RedundancyPair(rule_a_id=ra, rule_b_id=rb, jaccard=jaccard, both_fail_n=overlap,
                    explanation=f"{ra} and {rb} exclude many of the same synthetic patients. Relaxing either alone may recover few patients while the other still excludes them; verify the combined effect in the simulator."))
    pairs.sort(key=lambda pair: (-pair.jaccard, pair.rule_a_id, pair.rule_b_id))
    total = min(1.0, sum(c.explained_variance_ratio for c in components))
    return FilterSummary(components=components, explained_variance_total=total, variance_target_reached=total >= 0.85 - 1e-10,
                         included_rule_ids=[r.id for r in active], dropped_rule_ids=dropped, redundancy_pairs=pairs)
