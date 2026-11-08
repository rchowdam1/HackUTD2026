"""Decision engine (§19.4). Pure: no SMS, DB, network or asyncio.

Both functions take every segment of the session so far and return the
session's cumulative results; the pipeline diffs against what it already
published or sent. Decision.basis holds the rule_ids of the RiskEvents behind it.

Arms (tables in policy/<version>/rules.yaml and lexicon.yaml):
- K: a lexicon term in any speaker's text.
- B: a caller request, in the caller's direction, not negated or hedged, whose
  object is a lexicon term in the same turn or (for "read it to me") a recent turn.
- C: B plus app.intent.classify on caller turns with a lexicon hit B didn't act on;
  the model only confirms the category the lexicon saw (it never acts alone).
Evidence is category wording and rule ids only, never call text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app import intent
from app.models import Arm, Decision, RiskEvent, Segment

POLICY_DIR = Path(__file__).resolve().parents[3] / "policy"


@dataclass(frozen=True)
class _Category:
    name: str
    cfg: dict
    lexicon: re.Pattern
    requests: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class _Policy:
    cfg: dict
    categories: tuple[_Category, ...]
    clause_split: re.Pattern
    negation: re.Pattern
    hedges: re.Pattern
    exclusions: re.Pattern
    context_object: re.Pattern
    negated_object: re.Pattern


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def _any(patterns: list[str]) -> re.Pattern:
    return _rx(r"\b(?:" + "|".join(f"(?:{p})" for p in patterns) + r")\b")


@lru_cache
def load_policy(policy_version: str) -> _Policy:
    root = POLICY_DIR / policy_version
    cfg = yaml.safe_load((root / "rules.yaml").read_text())
    lexicon = yaml.safe_load((root / "lexicon.yaml").read_text())["categories"]
    frames = "|".join(f"(?:{f})" for f in cfg["frames"])
    categories = []
    for name, c in cfg["categories"].items():
        v = rf"(?P<v>{c['verbs']})\b"
        requests = (
            _rx(rf"\b(?:{frames})(?:\s+[\w']+){{0,2}}?\s+{v}"),  # can you (just) read
            _rx(rf"^\s*(?:{cfg['intro']}\b[^,]*,\s*)?(?:{cfg['fillers']}\b[\s,]*)*{v}"),  # imperative: read me / buy
            _rx(rf"\b{v}(?:\s+[\w']+){{0,4}}?\s+(?:me|us)\b"),  # read it back to me
            *(_rx(rf"\b(?:{p})\b") for p in c["extra"]),
        )
        categories.append(_Category(name, c, _any(lexicon[name]), requests))
    return _Policy(cfg, tuple(categories), _rx(cfg["clause_split"]), _any(cfg["negation"]),
                   _any(cfg["hedges"]), _rx(r"(?:" + "|".join(cfg["exclusions"]) + r")\b"),
                   _rx(cfg["context_object"]), _rx(rf"\b{cfg['negated_object']}\b"))


def _negated(p: _Policy, clause: str, anchor: int) -> bool:
    if p.negated_object.search(clause, anchor):  # share it with no one
        return True
    for m in p.negation.finditer(clause, 0, anchor):
        gap = clause[m.end():anchor]
        aside = ""
        if gap.lstrip().startswith(","):  # "do not, under any circumstances, share"
            aside, _, gap = gap.lstrip()[1:].partition(",")
            if len(aside.split()) > p.cfg["negation_max_aside_words"]:
                continue
        elif "," in gap:  # "don't worry, read me": the comma ends the negated clause
            continue
        words = re.findall(r"[\w']+", gap.lower())
        if (len(words) <= p.cfg["negation_max_gap_words"]
                and not set(words + aside.lower().split()) & set(p.cfg["negation_blockers"])):
            return True
    return False


def _is_request(p: _Policy, cat: _Category, clause: str) -> bool:
    for pattern in cat.requests:
        for m in pattern.finditer(clause):
            anchor = m.start("v") if "v" in pattern.groupindex else m.start()
            if p.exclusions.match(clause, anchor):
                continue
            if p.hedges.search(clause, 0, anchor) or _negated(p, clause, anchor):
                continue
            return True
    return False


def _event(seg: Segment, event_type: str, source: str, rule_id: str, category: str,
           span: list[int], confidence: str, policy_version: str) -> RiskEvent:
    return RiskEvent.model_validate(dict(
        session_ref=seg.session_ref, event_type=event_type, source=source, rule_id=rule_id,
        category=category, span_seq=span, confidence_class=confidence, policy_version=policy_version))


def _keyword(p: _Policy, segments: list[Segment], policy_version: str) -> list[RiskEvent]:
    return [_event(s, c.cfg["k_event"], "rule", c.cfg["k_rule"], c.name, [s.seq], "low", policy_version)
            for s in segments for c in p.categories if c.lexicon.search(s.text)]


def _requests(p: _Policy, segments: list[Segment], i: int, policy_version: str) -> list[RiskEvent]:
    """B events for caller turn i, given the turns before it (dialogue state)."""
    seg = segments[i]
    window = segments[max(0, i - p.cfg["context_turns"]):i]
    clauses = [c for c in p.clause_split.split(seg.text) if c.strip()]
    out = []
    for cat in p.categories:
        for clause in clauses:
            if not _is_request(p, cat, clause):
                continue
            if cat.lexicon.search(seg.text):
                rid, conf, span = cat.cfg["b_rules"]["high"], "high", [seg.seq]
            elif p.context_object.search(clause) and (prior := [s for s in window if cat.lexicon.search(s.text)]):
                rid, conf, span = cat.cfg["b_rules"]["medium"], "medium", [prior[-1].seq, seg.seq]
            else:
                continue
            out.append(_event(seg, cat.cfg["b_event"], "rule", rid, cat.name, span, conf, policy_version))
            break
    return out


def _intent(p: _Policy, segments: list[Segment], i: int, fired: set[str],
            policy_version: str) -> list[RiskEvent]:
    """Arm C hook: the model confirms a lexicon category B didn't act on."""
    seg = segments[i]
    seen = {c.name: c for c in p.categories if c.name not in fired and c.lexicon.search(seg.text)}
    if not seen:
        return []
    label = intent.classify(segments[max(0, i - p.cfg["context_turns"]):i + 1])
    if label not in seen:
        return []
    cat = seen[label]
    return [_event(seg, cat.cfg["b_event"], "intent", cat.cfg["c_rule"], cat.name, [seg.seq],
                   "medium", policy_version)]


def detect(segments: list[Segment], arm: Arm, policy_version: str) -> list[RiskEvent]:
    """The session's RiskEvents for this arm, first occurrence of each rule_id, in turn order."""
    p = load_policy(policy_version)
    if arm == "K":
        events = _keyword(p, segments, policy_version)
    else:
        events = []
        for i, seg in enumerate(segments):
            if seg.speaker != "caller":
                continue
            new = _requests(p, segments, i, policy_version)
            if arm == "C":
                new += _intent(p, segments, i, {e.category for e in events + new}, policy_version)
            events += new
    first: dict[str | None, RiskEvent] = {}
    for e in events:
        first.setdefault(e.rule_id, e)
    return list(first.values())


def decide(segments: list[Segment], arm: Arm, policy_version: str) -> list[Decision]:
    """One action_warning per category with evidence, in order of first evidence. [] = no alert."""
    p = load_policy(policy_version)
    keyword = detect(segments, "K", policy_version)
    events = keyword if arm == "K" else detect(segments, arm, policy_version)
    by_category: dict[str, list[RiskEvent]] = {}
    for e in events:
        by_category.setdefault(e.category, []).append(e)
    cfg = p.cfg["categories"]
    return [Decision(session_ref=evs[0].session_ref, level="action_warning",
                     template_id=cfg[cat]["alert"], followup_template_id=cfg[cat]["followup"],
                     basis=[e.rule_id for e in evs if e.rule_id],
                     keyword_arm_would_fire=any(k.category == cat for k in keyword),
                     policy_version=policy_version)
            for cat, evs in by_category.items()]
