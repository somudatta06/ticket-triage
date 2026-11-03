"""Stage checks for Ticket Triage. Each returns a list of (passed, message).

Stages that test plumbing use the fake backend, so they're exact and cost nothing.
Stages that need real behaviour read your eval runs, which used your own model.
Please don't edit this file: the finish line is scored on the server the same way.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid

import llm

LIVE_IDS = 3          # tickets stage 2 runs live (kept small: local models are slow)
MIN_TAGS = 10
MIN_LIFT = 0.03


def _ok(cond, yes, no):
    return (bool(cond), yes if cond else no)


# ---------- 01 connect ----------

def check_01(ctx):
    cfg = ctx.config()
    b = cfg.get("backend")
    calls = [c for c in ctx.calls() if c.get("backend") == b and c.get("ok")]
    return [
        _ok(b and b != "fake", "A model backend is chosen: %s%s" % (b, (" " + cfg["model"]) if cfg.get("model") else ""),
            "No backend chosen. Run: python3 insideout.py doctor"),
        _ok(calls, "It has answered at least once.",
            "No successful call yet. Run doctor with --use and fix what it says."),
    ]


# ---------- 02 first call ----------

def check_02(ctx):
    triage = ctx.learner("triage")
    run = "check02-" + uuid.uuid4().hex[:6]
    os.environ["INSIDEOUT_RUN"] = run
    items = ctx.tickets("examples")[:LIVE_IDS]
    results = []
    good = 0
    for t in items:
        out = triage.triage(ctx.public(t))
        if isinstance(out, dict) and out.get("queue") in ctx.queues:
            good += 1
        else:
            results.append((False, "%s: triage() returned %s. It should be a dict with a \"queue\" from QUEUES."
                            % (t["id"], json.dumps(out)[:120])))
    calls = [c for c in ctx.calls() if c.get("run") == run]
    results.insert(0, _ok(good == len(items), "triage() returned a valid queue for all %d tickets." % len(items),
                          "Only %d of %d returned a valid queue." % (good, len(items))))
    results.insert(1, _ok(calls, "It asked your model (%d calls)." % len(calls),
                          "No model calls were recorded. Use llm.ask() inside triage()."))
    return results


# ---------- 03 read ----------

def check_03(ctx):
    text = ctx.text("notes/reading.md")
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith(("#", ">", "<!--"))]
    words = sum(len(l.split()) for l in lines)
    known = {t["id"] for t in ctx.tickets("examples")} | {t["id"] for t in ctx.tickets("dev")}
    ids = {m.upper() for m in re.findall(r"\bT-\d{4}\b", text, flags=re.I)} & known
    return [
        _ok(words >= 80, "notes/reading.md has your notes (%d words)." % words,
            "notes/reading.md needs your own notes: about 80 words or more (it has %d)." % words),
        _ok(len(ids) >= 3, "It names %d real tickets." % len(ids),
            "Name at least 3 tickets you found hard, by id (like T-0012). Found %d." % len(ids)),
    ]


# ---------- 04 json ----------

PARSE_CASES = [
    ('{"queue":"billing","urgency":"high","order_id":"ORD-48213","wants_refund":true}',
     {"queue": "billing", "urgency": "high", "order_id": "ORD-48213", "wants_refund": True}),
    ('```json\n{"queue": "Returns", "urgency": "Normal", "order_id": "#50017", "wants_refund": false}\n```',
     {"queue": "returns", "urgency": "normal", "order_id": "ORD-50017", "wants_refund": False}),
    ('Here is the routing:\n{"queue":"shipping","urgency":"normal","order_id":null,"wants_refund":false}\nLet me know if you need more.',
     {"queue": "shipping", "urgency": "normal", "order_id": None, "wants_refund": False}),
    ('{"queue":"order changes","urgency":"high","order_id":"ord 61200","wants_refund":false}',
     {"queue": "order_changes", "urgency": "high", "order_id": "ORD-61200", "wants_refund": False}),
    ('{"queue":"account","urgency":"URGENT","order_id":"","wants_refund":"false"}',
     {"queue": "account", "urgency": "urgent", "order_id": None, "wants_refund": False}),
    ('{"queue":"product","urgency":"normal","wants_refund":false}',
     {"queue": "product", "urgency": "normal", "order_id": None, "wants_refund": False}),
    ('{"queue":"refunds","urgency":"normal","order_id":null,"wants_refund":true}', ValueError),
    ('I think this one is billing.', ValueError),
    ('{"queue":"billing","urgency":"high"', ValueError),
    ('{"queue":"billing","urgency":"medium","order_id":null,"wants_refund":false}', ValueError),
]

ORDER_CASES = [
    ("#48213", "ORD-48213"), ("order 48213", "ORD-48213"), ("ORD48213", "ORD-48213"),
    ("ord-48213", "ORD-48213"), ("48213", "ORD-48213"), (" ORD-48213 ", "ORD-48213"),
    ("ORD-48213, ORD-50017", "ORD-48213"), (None, None), ("", None), ("null", None), ("N/A", None),
    ("1Z999AA10123456784", None), ("INV-2026-0441", None), ("482133", None),
]

GOOD = '{"queue":"billing","urgency":"high","order_id":"ORD-11111","wants_refund":true}'


class Script:
    """A fake model: plays back a list of replies (or errors), one per call."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, prompt, system, schema):
        self.calls.append(prompt)
        step = self.steps[min(len(self.steps) - 1, len(self.calls) - 1)]
        if isinstance(step, type) and issubclass(step, Exception):
            raise step("scripted %s" % step.__name__)
        return step


def _with_fake(ctx, steps, ticket=None):
    s = Script(steps)
    llm.use_fake(s)
    try:
        triage = ctx.learner("triage")
        t = ticket or {"id": "T-9999", "channel": "email", "subject": "charged twice",
                       "body": "You charged my card twice for order 11111. I want my money back.", "lang": "en"}
        try:
            out, err = triage.triage(t), None
        except Exception as e:
            out, err = None, e
        return out, err, s
    finally:
        llm.use_fake(None)


def check_04(ctx):
    triage = ctx.learner("triage")
    res = []
    for name in ("parse_reply", "normalize_order_id"):
        if not hasattr(triage, name):
            return [(False, "triage.py needs a %s() function. See the stage brief." % name)]
    bad = []
    for raw, want in ORDER_CASES:
        try:
            got = triage.normalize_order_id(raw)
        except Exception as e:
            got = "raised %s" % type(e).__name__
        if got != want:
            bad.append("%r → %r (want %r)" % (raw, got, want))
    res.append(_ok(not bad, "normalize_order_id() handles all %d cases." % len(ORDER_CASES),
                   "normalize_order_id() got %d wrong, e.g. %s" % (len(bad), "; ".join(bad[:3]))))
    bad = []
    for raw, want in PARSE_CASES:
        try:
            got = triage.parse_reply(raw)
            if want is ValueError:
                bad.append("%r should raise ValueError, got %s" % (raw[:40], json.dumps(got)))
            elif got != want:
                bad.append("%r → %s (want %s)" % (raw[:40], json.dumps(got), json.dumps(want)))
        except ValueError:
            if want is not ValueError:
                bad.append("%r raised ValueError but is usable" % raw[:40])
        except Exception as e:
            bad.append("%r raised %s (raise ValueError for unusable replies)" % (raw[:40], type(e).__name__))
    res.append(_ok(not bad, "parse_reply() handles all %d replies." % len(PARSE_CASES),
                   "parse_reply() got %d wrong, e.g. %s" % (len(bad), "; ".join(bad[:2]))))
    out, err, s = _with_fake(ctx, ["Sure! It's billing.", GOOD])
    res.append(_ok(isinstance(out, dict) and out.get("queue") == "billing" and len(s.calls) == 2,
                   "triage() asks again once when a reply can't be used.",
                   "When the first reply is unusable, triage() should ask once more and use the second "
                   "(made %d calls, returned %s)." % (len(s.calls), json.dumps(out) if not err else type(err).__name__)))
    out, err, s = _with_fake(ctx, [GOOD])
    res.append(_ok(isinstance(out, dict) and all(out.get(k) == v for k, v in json.loads(GOOD).items()
                                                 if k != "order_id") and out.get("order_id") == "ORD-11111" and len(s.calls) == 1,
                   "With a good reply it makes one call and returns all four fields.",
                   "With a good first reply, triage() should make one call and return all four fields "
                   "(made %d, returned %s)." % (len(s.calls), json.dumps(out))))
    return res


# ---------- 05 eval ----------

SCORE_PREDS = {
    "a": {"queue": "billing", "urgency": "high", "order_id": "ORD-10001", "wants_refund": True},
    "b": {"queue": "returns", "urgency": "normal", "order_id": None, "wants_refund": False},
    "c": {"queue": "shipping", "urgency": "normal", "order_id": "ORD-10003", "wants_refund": False},
    "d": None,
    "e": {"queue": "product", "urgency": "normal", "order_id": None, "wants_refund": False},
}
SCORE_GOLD = {
    "a": {"queue": "billing", "urgency": "high", "order_id": "ORD-10001", "wants_refund": True},
    "b": {"queue": "billing", "urgency": "high", "order_id": None, "wants_refund": True},
    "c": {"queue": "shipping", "urgency": "high", "order_id": "ORD-10003", "wants_refund": False},
    "d": {"queue": "account", "urgency": "urgent", "order_id": None, "wants_refund": False},
    "e": {"queue": "product", "urgency": "normal", "order_id": None, "wants_refund": False},
}
SCORE_WANT = {"queue": 0.6, "urgency": 0.4, "order_id": 0.8, "wants_refund": 0.6, "all_four": 0.4,
              "confusion": {"billing": {"billing": 1, "returns": 1}, "shipping": {"shipping": 1},
                            "account": {"error": 1}, "product": {"product": 1}}}


def check_05(ctx):
    res = []
    try:
        got = ctx.learner("score").score(SCORE_PREDS, SCORE_GOLD)
    except NotImplementedError:
        return [(False, "score.py: write score(preds, gold) first.")]
    bad = [k for k in ("queue", "urgency", "order_id", "wants_refund", "all_four")
           if not isinstance(got.get(k), (int, float)) or abs(got[k] - SCORE_WANT[k]) > 1e-9]
    res.append(_ok(not bad, "score() gets every accuracy right on a test case.",
                   "score() is off for: %s. Got %s" % (", ".join(bad), json.dumps({k: got.get(k) for k in bad}))))
    conf = got.get("confusion")
    res.append(_ok(conf == SCORE_WANT["confusion"], "score() builds the confusion table right.",
                   "confusion should be %s, got %s" % (json.dumps(SCORE_WANT["confusion"]), json.dumps(conf))))
    cfg = ctx.config()
    runs = [r for r in ctx.evals() if r.get("full") and r.get("backend") != "fake"]
    res.append(_ok(runs, "You've run a full eval on the dev set with your model.",
                   "Run a full eval: python3 insideout.py eval"))
    res.append(_ok(any(r.get("prediction") for r in runs),
                   "You wrote down a prediction before an eval.",
                   "Before an eval, write what you expect: python3 insideout.py predict \"...\" Then eval again."))
    return res


# ---------- 06 errors ----------

def check_06(ctx):
    runs = [r for r in ctx.evals() if r.get("full") and r.get("backend") != "fake"]
    wrong_ids = set()
    gold = {t["id"]: t["label"] for t in ctx.tickets("dev")}
    for r in runs:
        preds = ctx.run_preds(r["run"])
        for tid, g in gold.items():
            p = preds.get(tid) or {}
            if any(p.get(f) != g.get(f) for f in ctx.fields):
                wrong_ids.add(tid)
    tags = [(tid, tag) for tid, tag in ctx.failures_csv() if tid.upper() in wrong_ids]
    groups = len({tag for _, tag in tags})
    res = [_ok(len(tags) >= MIN_TAGS, "You tagged %d real failures in %d groups." % (len(tags), groups),
               "Tag at least %d failures from your evals in notes/failures.csv (found %d that match)."
               % (MIN_TAGS, len(tags)))]
    by_setup = {}
    for r in runs:
        by_setup.setdefault((r["backend"], r.get("model")), []).append(r)
    lifted = False
    for setup, rs in by_setup.items():
        if len(rs) >= 2 and rs[-1].get("triage_hash") != rs[0].get("triage_hash"):
            if max(r["ref"]["all_four"] for r in rs[1:]) - rs[0]["ref"]["all_four"] >= MIN_LIFT:
                lifted = True
    res.append(_ok(lifted, "After a change to triage.py, the same model scored better than your first eval.",
                   "Change triage.py to fix your biggest group, then eval again with the same model. "
                   "It needs to beat your first eval by %d points on all four." % round(MIN_LIFT * 100)))
    return res


# ---------- 07 failures ----------

class _Sleeps:
    def __init__(self):
        self.calls = []

    def __call__(self, s):
        self.calls.append(s)


def check_07(ctx):
    real_sleep = time.sleep
    sleeps = _Sleeps()
    time.sleep = sleeps
    try:
        res = []
        cases = [
            ("rate limit twice, then a good reply", [llm.RateLimited, llm.RateLimited, GOOD],
             lambda out, s, z: out and out.get("queue") == "billing" and len(s.calls) == 3 and len(z.calls) >= 2,
             "should retry after waiting, and return billing on the third call"),
            ("the model keeps timing out", [llm.Timeout],
             lambda out, s, z: out and out.get("queue") == "needs_human" and len(s.calls) <= 3,
             "should give up after at most 3 tries and return queue \"needs_human\""),
            ("the backend is unavailable", [llm.Unavailable],
             lambda out, s, z: out and out.get("queue") == "needs_human" and len(s.calls) == 1,
             "shouldn't retry (it won't help) and should return \"needs_human\""),
            ("two unusable replies", ["no idea", "still no JSON"],
             lambda out, s, z: out and out.get("queue") == "needs_human" and len(s.calls) <= 3,
             "should stop after the repair attempt and return \"needs_human\""),
            ("a good reply first time", [GOOD],
             lambda out, s, z: out and out.get("queue") == "billing" and len(s.calls) == 1 and not z.calls,
             "should make one call and not wait"),
        ]
        for name, steps, ok, want in cases:
            sleeps.calls.clear()
            out, err, s = _with_fake(ctx, steps)
            passed = err is None and ok(out, s, sleeps)
            if err is not None:
                detail = "it raised %s instead of returning" % type(err).__name__
            else:
                detail = "made %d calls, waited %d times, returned %s" % (len(s.calls), len(sleeps.calls), json.dumps(out))
            res.append(_ok(passed, "When %s: handled." % name, "When %s: it %s (%s)." % (name, want, detail)))
        return res
    finally:
        time.sleep = real_sleep


# ---------- 08 choose ----------

def check_08(ctx):
    runs = [r for r in ctx.evals() if r.get("full") and r.get("backend") != "fake"]
    setups = {(r["backend"], r.get("model")) for r in runs}
    text = ctx.text("notes/decision.md")
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith(("#", ">", "<!--"))]
    names = {s for b, m in setups for s in (b, m) if s}
    mentions = any(n.lower() in text.lower() for n in names)
    has_number = bool(re.search(r"\d", " ".join(lines)))
    return [
        _ok(len(setups) >= 2, "You've run full evals on %d different models." % len(setups),
            "Run a full eval on a second model or backend, e.g. python3 insideout.py eval --model <another>"),
        _ok(len(lines) >= 3 and mentions and has_number,
            "notes/decision.md says which model you'd ship, with numbers.",
            "In notes/decision.md, name the model you'd ship and why, using numbers from: python3 insideout.py compare"),
    ]


# ---------- 09 finish ----------

def check_09(ctx):
    subs = ctx.submissions()
    best = max(subs, key=lambda s: s["ref"]["all_four"]) if subs else None
    return [
        _ok(subs, "You've submitted to the finish line.", "Run: python3 insideout.py submit"),
        _ok(best and best.get("passed"), "You're over the bar (%s all four right)." % (
            "%d%%" % round(100 * best["ref"]["all_four"]) if best else ""),
            "Not over the bar yet. Improve, eval, submit again."),
    ]
