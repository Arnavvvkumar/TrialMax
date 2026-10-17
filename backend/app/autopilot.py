"""Prespecified threshold candidates and bounded, simulator-scored beam search."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math

from .cohorts import compare_population, resolve
from .engine import evaluate
from .filters import hidden_filters
from .models import (AutopilotBlocked, AutopilotConsidered, AutopilotEdit, AutopilotRequest,
                     AutopilotResponse, Rule)
from .simulate import _critical, classify_change
from .variables import ULN, VARIABLES, validate_rule_semantics

MAX_SIMULATIONS = 150  # baseline evaluation + TWO evaluations for each compare_population call
BEAM_WIDTH = 5
LOWER_STEPS = {
    "anc": {1.5: (1.0,)}, "platelets": {100.0: (75.0,)},
    "hemoglobin": {10.0: (9.0, 8.0), 9.0: (8.0,)},
    "egfr": {60.0: (45.0, 30.0), 45.0: (30.0,)},
    "crcl": {60.0: (45.0, 30.0), 45.0: (30.0,)},
}
UPPER_ULN_STEPS = {"bilirubin": {1.5: (2.0,)}, "ast": {2.5: (3.0,)}, "alt": {2.5: (3.0,)}}


@dataclass(frozen=True)
class Candidate:
    rule_id: str
    field: str
    before: float
    after: float
    rule: Rule


def candidate_edits(rule: Rule) -> list[Candidate]:
    """Only these explicit table entries are allowed; never change units, kind, or operator."""
    if _critical(rule) or not rule.simulatable or rule.not_applicable:
        return []
    values, field = (), "value"
    lower = (rule.kind == "inclusion" and rule.operator == ">=") or (rule.kind == "exclusion" and rule.operator in ("<", "<="))
    upper = (rule.kind == "inclusion" and rule.operator == "<=") or (rule.kind == "exclusion" and rule.operator in (">", ">="))
    if rule.variable == "age" and (upper or (rule.kind == "inclusion" and rule.operator == "between")):
        field = "value_max" if rule.operator == "between" else "value"
        start = getattr(rule, field)
        values = (start + 5, start + 10)
    elif lower and rule.variable in LOWER_STEPS:
        values = next((steps for value, steps in LOWER_STEPS[rule.variable].items()
                       if math.isclose(rule.value, value, abs_tol=1e-9, rel_tol=0)), ())
    elif upper and rule.variable == "ecog" and rule.value == 1:
        values = (2.0,)
    elif upper and rule.variable in UPPER_ULN_STEPS:
        factor = 1.0 if rule.unit == "x_uln" else ULN[rule.variable]
        values = next((tuple(step * factor for step in steps)
                       for value, steps in UPPER_ULN_STEPS[rule.variable].items()
                       if math.isclose(rule.value, value * factor, abs_tol=1e-9, rel_tol=0)), ())
    result = []
    for value in values:
        data = rule.model_dump()
        data[field] = float(value)
        validate_rule_semantics(data["variable"], data["operator"], data["value"], data["value_max"], data["unit"])
        edited = Rule.model_validate(data)
        if classify_change(rule, edited) == "relaxed":
            result.append(Candidate(rule.id, field, getattr(rule, field), float(value), edited))
    return result


@dataclass(frozen=True)
class Score:
    gain: int
    review_ids: frozenset[str]


def _joint_moves(options: list[Candidate], filters, max_edits: int) -> set[tuple[int, ...]]:
    """Coordinate same-variable bounds and overlapping pairs; every member remains a table edit."""
    by_rule: dict[str, list[int]] = {}
    bounds: dict[tuple[str, bool], dict[str, list[int]]] = {}
    for i, candidate in enumerate(options):
        by_rule.setdefault(candidate.rule_id, []).append(i)
        # Increasing an allowed upper bound and decreasing a required lower bound
        # are different directions, even when they share a variable.
        key = (candidate.rule.variable, candidate.after > candidate.before)
        bounds.setdefault(key, {}).setdefault(candidate.rule_id, []).append(i)
    moves = set()
    for members in bounds.values():
        if not 2 <= len(members) <= max_edits:
            continue
        # Synchronize on an available table destination, normalizing only x ULN.
        # No cross-variable/unit conversion or invented intermediate steps.
        destinations = {}
        for rid, indices in members.items():
            destinations[rid] = {}
            for i in indices:
                c = options[i]
                value = c.after * (ULN[c.rule.variable] if c.rule.unit == "x_uln" else 1)
                destinations[rid][round(value, 9)] = i
        shared = set.intersection(*(set(d) for d in destinations.values()))
        for destination in sorted(shared):
            moves.add(tuple(sorted(d[destination] for d in destinations.values())))
    if max_edits >= 2:
        for pair in filters.redundancy_pairs:
            for a, b in product(by_rule.get(pair.rule_a_id, []), by_rule.get(pair.rule_b_id, [])):
                moves.add(tuple(sorted((a, b))))
    return moves


def run_autopilot(request: AutopilotRequest) -> AutopilotResponse:
    rules = request.rules
    cohort, columns, ids, assumptions = resolve(request.population)
    pinned = request.population.model_copy(update={"version": cohort.version, "cohort_id": cohort.id})
    baseline = evaluate(rules, columns, cohort, assumptions, ids)[0]
    filters = hidden_filters(rules, columns, population_n=cohort.population_n)
    warnings = list(baseline.warnings) + [
        "Prespecified exploratory edits are not proof of clinical safety. Researcher and clinical review remain required.",
        "Beam search returns the smallest set found within its budget, not a globally optimal or clinically validated plan.",
        "The table maximum applies the furthest listed step to every relaxable rule and can require more than max_edits.",
    ]
    if not filters.variance_target_reached and filters.components:
        warnings.append("The five-component PCA limit does not capture the full variance target.")
    blocked = [AutopilotBlocked(rule_id=r.id, label=VARIABLES.get(r.variable, {}).get("label", r.clause or r.text),
               reason="Hard safety block: critical by rule flag or variable registry; never relaxed, removed or disabled.")
               for r in sorted(rules, key=lambda r: r.id) if _critical(r)]
    options, considered = [], []
    for rule in sorted(rules, key=lambda r: r.id):
        if _critical(rule):
            continue
        edits = candidate_edits(rule)
        if rule.id not in baseline.modeled_rule_ids:
            reason = "Not checked in this population; unknowns cannot be treated as recovered patients."
        elif not edits:
            reason = "No allowed relaxation in the prespecified step table."
        else:
            options.extend(edits)
            continue
        considered.append(AutopilotConsidered(rule_id=rule.id, reason=reason))

    simulation_count = 1
    cache: dict[tuple[int, ...], Score | None] = {(): Score(0, frozenset())}
    cap_hit = False

    def score(path: tuple[int, ...]) -> Score | None:
        nonlocal simulation_count, cap_hit
        key = tuple(sorted(path))
        if key in cache:
            return cache[key]
        if simulation_count + 2 > MAX_SIMULATIONS:
            cap_hit = True
            return None
        replacements = {options[i].rule_id: options[i].rule for i in key}
        proposed = [replacements.get(r.id, r) for r in rules]
        result = compare_population(rules, proposed, pinned)
        simulation_count += 2
        if result.cohort.id != cohort.id:
            raise ValueError("Autopilot comparison changed cohort; rerun the baseline.")
        if result.relaxed_safety_critical_rule_ids or any(c.safety_critical for c in result.changes):
            warnings.append("A candidate failed the comparison safety guard and was discarded.")
            cache[key] = None
        elif result.modeled_eligible_change_n is None:
            cache[key] = None
        else:
            cache[key] = Score(result.modeled_eligible_change_n, frozenset(result.safety_review_rule_ids))
        return cache[key]

    components = {}
    for rule in rules:
        ranked = sorted(filters.components, key=lambda c: (-abs(c.loadings.get(rule.id, 0)), c.component))
        if ranked and abs(ranked[0].loadings.get(rule.id, 0)) > 1e-8:
            components[rule.id] = ranked[0]

    def movement(path: tuple[int, ...]):
        return sum(abs(options[i].after - options[i].before) / max(1.0, abs(options[i].before)) for i in path)

    def diversity(path: tuple[int, ...]):
        return len({components[options[i].rule_id].component for i in path if options[i].rule_id in components})

    def rank(path: tuple[int, ...]):
        gain = cache[tuple(sorted(path))].gain
        return (-gain, len(path), movement(path), -diversity(path), tuple(path))

    def target_rank(path: tuple[int, ...]):
        # Once the target is met, extra recovery cannot justify a larger relaxation.
        return (len(path), movement(path), -diversity(path), rank(path))

    def score_prefixes(path: tuple[int, ...]) -> Score | None:
        # A joint move can have zero gain until its final edit. Score every prefix
        # so the flat UI plan still reports independently reproducible marginals.
        for length in range(1, len(path) + 1):
            outcome = score(path[:length])
            if outcome is None:
                return None
        return outcome

    # Each rule's furthest table step is monotone and supplies the all-rule upper bound.
    furthest: dict[str, int] = {}
    for i, candidate in enumerate(options):
        previous = furthest.get(candidate.rule_id)
        if previous is None or abs(candidate.after - candidate.before) > abs(options[previous].after - options[previous].before):
            furthest[candidate.rule_id] = i
    maximum = score(tuple(furthest.values())) if options and baseline.modeled_eligible_n is not None else None
    max_gain = max(0, maximum.gain) if maximum else 0
    target = math.ceil(request.target_fraction * max_gain)
    screened, rejected = [], []
    # Reserve roughly half the comparison budget for combinations rather than singles.
    single_limit = max(1, (MAX_SIMULATIONS - 5) // 4)
    if max_gain > 0:
        for i, candidate in enumerate(options):
            if i >= single_limit:
                rejected.append(AutopilotConsidered(rule_id=candidate.rule_id, field=candidate.field, to=candidate.after,
                                                  reason="Single-candidate budget exhausted; not evaluated."))
                continue
            outcome = score((i,))
            if outcome is not None:
                screened.append(i)  # zero-gain edits may be necessary in a joint move
            else:
                rejected.append(AutopilotConsidered(rule_id=candidate.rule_id, field=candidate.field, to=candidate.after,
                    reason="Safety/coverage guard failed, or simulation budget exhausted."))
    moves = {(i,) for i in screened}
    if max_gain > 0:
        moves.update(_joint_moves(options, filters, request.max_edits))
    moves = sorted(moves, key=lambda p: (len(p), movement(p), p))
    # Joint moves have the cost of ALL their edited rules. Weighted breadth avoids
    # treating a coordinated three-rule change as one edit or skipping cheaper plans.
    pending: dict[int, dict[tuple[int, ...], tuple[int, ...]]] = {n: {} for n in range(1, request.max_edits + 1)}
    for move in moves:
        pending[len(move)][move] = move
    winner: tuple[int, ...] = ()
    reached = False
    for depth in range(1, request.max_edits + 1):
        frontier = []
        paths = sorted(pending[depth].values(), key=lambda p: (movement(p), -diversity(p), p))
        for path in paths:
            if score_prefixes(path) is not None:
                frontier.append(path)
            if cap_hit:
                break
        if not frontier:
            continue
        frontier.sort(key=rank)
        if cache[tuple(sorted(frontier[0]))].gain > 0 and (not winner or rank(frontier[0]) < rank(winner)):
            winner = frontier[0]
        reaching = [p for p in frontier if cache[tuple(sorted(p))].gain >= target]
        if reaching:
            winner, reached = min(reaching, key=target_rank), True
            break  # breadth by edit count: this is the smallest depth found to meet the target
        if depth == request.max_edits or cap_hit:
            break
        for path in frontier[:BEAM_WIDTH]:
            used = {options[i].rule_id for i in path}
            for move in moves:
                if depth + len(move) > request.max_edits or any(options[i].rule_id in used for i in move):
                    continue
                next_path = path + move
                key = tuple(sorted(next_path))
                pending[len(next_path)].setdefault(key, next_path)

    plan = []
    previous_gain = 0
    for length, i in enumerate(winner, 1):
        candidate = options[i]
        outcome = cache[tuple(sorted(winner[:length]))]
        review = candidate.rule_id in outcome.review_ids or candidate.rule.purpose == "safety" or VARIABLES[candidate.rule.variable]["purpose"] == "safety"
        component = components.get(candidate.rule_id)
        marginal = outcome.gain - previous_gain
        plan.append(AutopilotEdit(rule_id=candidate.rule_id, variable=candidate.rule.variable, field=candidate.field,
            **{"from": candidate.before}, to=candidate.after, unit=candidate.rule.unit, marginal_gain=marginal,
            cumulative_gain=outcome.gain, component_label=component.label if component else "Other available checks",
            review_flag=review, rationale=f"Simulator marginal gain: {marginal}; cumulative gain: {outcome.gain}. "
            + ("Clinical review required." if review else "Researcher review required.")))
        previous_gain = outcome.gain
    for i in screened:
        if i not in winner:
            c = options[i]
            rejected.append(AutopilotConsidered(rule_id=c.rule_id, field=c.field, to=c.after, gain=cache[(i,)].gain,
                             reason="Alternative not selected by the bounded search; gain shown is for this edit alone."))
    if cap_hit or len(options) > single_limit:
        warnings.append("Simulation/candidate budget reached; some alternatives were not explored. The target may not be reached.")
    if not options:
        reason = "No modeled, noncritical rules have an allowed table relaxation."
    elif baseline.modeled_eligible_n is None:
        reason = "No modeled passing estimate is available for this population."
    elif max_gain <= 0:
        reason = "Even all allowed table relaxations together recover no additional patients on the modeled checks."
    elif not plan:
        reason = "No positive-gain plan found within the edit and simulation limits, including coordinated rule relaxations."
    elif reached:
        reason = "Target reached with the fewest edited rules found, then the smallest relative threshold movement."
    else:
        reason = "Best plan found falls below the target within the edit and simulation limits."
    rejected.sort(key=lambda c: (-(c.gain if c.gain is not None else -1), c.rule_id, c.to or 0))
    response = AutopilotResponse(cohort_id=cohort.id, baseline_modeled_eligible_n=baseline.modeled_eligible_n,
        max_achievable_gain=max_gain, target_gain=target, target_fraction=request.target_fraction,
        target_reached=reached, status="target_reached" if reached else "best_found_below_target" if plan else "no_plan",
        reason=reason, plan=plan, also_considered=(rejected + considered)[:12], blocked_rules=blocked, filters=filters,
        simulation_count=simulation_count, simulation_cap=MAX_SIMULATIONS, summary="",
        assumptions=list(assumptions), warnings=list(dict.fromkeys(warnings)))
    from .autopilot_narration import narrate
    return narrate(response, request.use_llm)
