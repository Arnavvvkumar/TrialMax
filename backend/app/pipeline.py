"""Full parse: deterministic rules first, then the LLM (within a time budget) for what is left."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait

from . import config, llm
from .criteria import parse_eligibility_rules
from .models import Rule

log = logging.getLogger("windtunnel.pipeline")

MAX_RULES = 150

# One shared pool for the whole server, so concurrent requests cannot multiply LLM threads.
_EXECUTOR = ThreadPoolExecutor(max_workers=config.LLM_MAX_WORKERS, thread_name_prefix="llm")


def needs_llm(rule: Rule) -> bool:
    return rule.parsed_by == "none" and not rule.simulatable


def parse_eligibility(text: str, use_llm: bool = True) -> tuple[list[Rule], list[str], bool]:
    """Returns (rules, warnings, llm_used)."""
    rules, warnings = parse_eligibility_rules(text)
    if len(rules) > MAX_RULES:
        raise ValueError(f"Analysis limit is {MAX_RULES} parsed rules; this text produced {len(rules)}. "
                         "No partial analysis was performed. Submit a smaller set of criteria.")
    todo = [i for i, r in enumerate(rules) if needs_llm(r)]
    if not todo or not use_llm:
        return rules, warnings, False
    if not config.llm_configured():
        warnings.append("AI parsing is off (Chalk gateway key, environment or model missing in .env); "
                        f"{len(todo)} criteria were left unparsed.")
        return rules, warnings, False

    if len(todo) > config.LLM_MAX_CRITERIA:
        warnings.append(f"AI was asked about the first {config.LLM_MAX_CRITERIA} of {len(todo)} unparsed criteria.")
        todo = todo[:config.LLM_MAX_CRITERIA]

    futures = {_EXECUTOR.submit(llm.classify, rules[i]): i for i in todo}
    done, not_done = wait(futures, timeout=config.LLM_TOTAL_BUDGET_S)
    for fut in not_done:
        fut.cancel()  # queued calls are dropped; running ones end at their own timeout
    failed = 0
    for fut in done:
        i = futures[fut]
        try:
            parsed, from_cache = fut.result()
        except Exception as exc:  # network or provider error: keep the rule unparsed
            log.warning("LLM call failed for %s: %s", rules[i].id, exc)
            failed += 1
            continue
        if parsed is None:
            failed += 1
            continue
        rules[i] = llm.apply(rules[i], parsed, from_cache)
    if not_done:
        warnings.append(f"AI ran out of time on {len(not_done)} criteria; they are left unparsed.")
    if failed:
        warnings.append(f"AI could not parse {failed} criteria; they are left unparsed.")
    return rules, warnings, True
