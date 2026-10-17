"""Full parse: deterministic rules first, then the LLM for whatever is left."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config, llm
from .criteria import parse_eligibility_rules
from .models import Rule

log = logging.getLogger("windtunnel.pipeline")


def needs_llm(rule: Rule) -> bool:
    return rule.parsed_by == "none" and rule.category not in ("administrative", "permission")


def parse_eligibility(text: str, use_llm: bool = True) -> tuple[list[Rule], list[str], bool]:
    """Returns (rules, warnings, llm_used)."""
    rules = parse_eligibility_rules(text)
    warnings: list[str] = []
    todo = [i for i, r in enumerate(rules) if needs_llm(r)]
    if not todo or not use_llm:
        return rules, warnings, False
    if not config.llm_configured():
        warnings.append("AI parsing is off (no Chalk gateway key or model in .env); "
                        f"{len(todo)} criteria were left unparsed.")
        return rules, warnings, False

    failed = 0
    with ThreadPoolExecutor(max_workers=config.LLM_MAX_WORKERS) as pool:
        futures = {pool.submit(llm.classify, rules[i]): i for i in todo}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                parsed = fut.result()
            except Exception as exc:  # network or provider error: keep the rule unparsed
                log.warning("LLM call failed for %s: %s", rules[i].id, exc)
                failed += 1
                continue
            if parsed is None:
                failed += 1
                continue
            rules[i] = llm.apply(rules[i], parsed)
    if failed:
        warnings.append(f"AI could not parse {failed} of {len(todo)} criteria; they are left unparsed.")
    return rules, warnings, True
