#!/usr/bin/env python3
"""
insideout.py: the project runner for Ticket Triage. Python 3.9+, nothing to install.

  python3 insideout.py doctor               find a model you can use, and save it
  python3 insideout.py stage                what to do now
  python3 insideout.py check                check your work; moves you on when it passes
  python3 insideout.py hint                 one more hint for this stage
  python3 insideout.py show [N | ID]        print tickets to read (from data/examples.jsonl)
  python3 insideout.py try ID               run your triage() on one ticket and show every model call
  python3 insideout.py predict "TEXT"       write down what you expect before you run an eval
  python3 insideout.py eval [--model M] [--backend B] [--limit N]
                                            run triage() on data/dev.jsonl and score it
  python3 insideout.py failures [--groups]  what your last eval got wrong, or your failure tags counted
  python3 insideout.py compare              your eval runs side by side
  python3 insideout.py trace                open the trace viewer in your browser
  python3 insideout.py submit               the finish line: run on tickets you've never seen
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import llm  # noqa: E402

STATE_DIR = os.path.join(ROOT, ".insideout")
PROGRESS = os.path.join(STATE_DIR, "progress.json")
EVALS = os.path.join(ROOT, "traces", "evals.jsonl")
RUNS_DIR = os.path.join(ROOT, "traces", "runs")

STAGES = [
    ("01-connect", "Connect a model"),
    ("02-first-call", "Route your first ticket"),
    ("03-read", "Read the tickets yourself"),
    ("04-json", "Four answers, always valid"),
    ("05-eval", "Measure it"),
    ("06-errors", "Find what breaks, fix the biggest group"),
    ("07-failures", "When the model fails"),
    ("08-choose", "Pick a model"),
    ("09-finish", "The finish line"),
]

QUEUES = ["billing", "shipping", "returns", "order_changes", "product", "account", "other"]
URGENCIES = ["urgent", "high", "normal"]
FIELDS = ["queue", "urgency", "order_id", "wants_refund"]


# ---------- small helpers ----------

def say(text=""):
    print(text)


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_progress():
    try:
        with open(PROGRESS) as f:
            p = json.load(f)
    except (OSError, ValueError):
        p = {}
    p.setdefault("stage", 0)
    p.setdefault("done", [])
    p.setdefault("hints", {})
    p.setdefault("predictions", [])
    return p


def save_progress(p):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PROGRESS, "w") as f:
        json.dump(p, f, indent=2)


def tickets(name):
    """data/<name>.jsonl as a list of tickets (with labels)."""
    return read_jsonl(os.path.join(ROOT, "data", name + ".jsonl"))


def public(t):
    """What triage() gets: the ticket without its label."""
    return {k: t[k] for k in ("id", "channel", "subject", "body", "lang") if k in t}


def find_ticket(tid):
    for name in ("examples", "dev"):
        for t in tickets(name):
            if t["id"].lower() == tid.lower():
                return t
    return None


def load_learner(module):
    """Import triage.py or score.py fresh, so edits since the last run count."""
    if module in sys.modules:
        return importlib.reload(sys.modules[module])
    return importlib.import_module(module)


def file_hash(name):
    try:
        with open(os.path.join(ROOT, name), "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return None


def show_ticket(t, full=True):
    say("─" * 72)
    head = "%s  ·  %s" % (t["id"], t.get("channel", ""))
    if t.get("lang") and t["lang"] != "en":
        head += "  ·  " + t["lang"]
    say(head)
    if t.get("subject"):
        say("Subject: " + t["subject"])
    body = t.get("body", "")
    if not full and len(body) > 400:
        body = body[:400].rstrip() + " …"
    say(body)


# ---------- reference scoring (used for checks and the finish line; your own is in score.py) ----------

def ref_score(preds, gold):
    n = len(gold) or 1
    right = {f: 0 for f in FIELDS}
    all4 = 0
    for tid, g in gold.items():
        p = preds.get(tid) or {}
        ok = {f: (p.get(f) == g.get(f)) for f in FIELDS}
        for f in FIELDS:
            right[f] += ok[f]
        all4 += all(ok.values())
    out = {f: right[f] / n for f in FIELDS}
    out["all_four"] = all4 / n
    return out


def pct(x):
    return "—" if x is None else "%d%%" % int(100 * x + 0.5)


# ---------- doctor ----------

def which(cmd):
    return shutil.which(cmd) is not None


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception:
        return None


DEFAULTS = {"claude": dict(concurrency=3, timeout=120, model_class="frontier"),
            "codex": dict(concurrency=3, timeout=180, model_class="frontier"),
            "copilot": dict(concurrency=3, timeout=180, model_class="frontier"),
            "ollama": dict(concurrency=2, timeout=180, model_class="small"),
            "openai": dict(concurrency=6, timeout=90, model_class="mid")}


def cmd_doctor(args):
    opts = parse_opts(args, ["use", "model", "url", "key-env", "class", "think"])
    if not opts.get("use"):
        say("What this computer has:\n")
        found = []
        if which("claude"):
            found.append("claude")
            say("  claude   Claude Code is installed. Uses your Claude login.")
        if which("codex"):
            found.append("codex")
            say("  codex    Codex is installed. Uses your ChatGPT or Codex login.")
        if which("copilot"):
            found.append("copilot")
            say("  copilot  GitHub Copilot CLI is installed. Uses your Copilot plan.")
        tags = http_ok("http://localhost:11434/api/tags")
        if tags is not None:
            models = [m.get("name") for m in tags.get("models", [])]
            found.append("ollama")
            say("  ollama   Ollama is running. Models pulled: %s" % (", ".join(models) or "none yet (try: ollama pull qwen3:4b)"))
        if http_ok("http://localhost:1234/v1/models") is not None:
            found.append("openai")
            say("  openai   LM Studio (or another server) is running on localhost:1234.")
        for env in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
            if os.environ.get(env):
                say("  openai   %s is set. Use it with --url and --key-env %s." % (env, env))
        if not found:
            say("  Nothing found yet. Install Claude Code, Codex or Ollama, or read docs/running-models.md.")
        say("\nPick one and test it, for example:\n")
        say("  python3 insideout.py doctor --use claude --model <a model your account has>")
        say("  python3 insideout.py doctor --use codex")
        say("  python3 insideout.py doctor --use ollama --model qwen3:4b")
        say("  python3 insideout.py doctor --use openai --url https://openrouter.ai/api/v1 --key-env OPENROUTER_API_KEY --model <model>")
        say("\nSmaller models use less of your plan and are plenty for this project. Leave out --model to use")
        say("the tool's default. Agent tools need the full model name, not a short alias.")
        return 0

    backend = opts["use"]
    if backend not in DEFAULTS:
        say("Unknown backend %r. Use one of: claude, codex, copilot, ollama, openai." % backend)
        return 1
    cfg = dict(DEFAULTS[backend])
    cfg.update({"backend": backend, "model": opts.get("model")})
    if opts.get("url"):
        cfg["openai_base_url" if backend == "openai" else "ollama_url"] = opts["url"]
    if opts.get("key-env"):
        cfg["openai_key_env"] = opts["key-env"]
    if opts.get("class"):
        cfg["model_class"] = opts["class"]
    if opts.get("think") and backend == "ollama":
        cfg["ollama_think"] = opts["think"] == "on"
    old = llm.load_config()
    llm.save_config(cfg)
    say("Testing %s%s …" % (backend, (" with " + cfg["model"]) if cfg.get("model") else ""))
    os.environ["INSIDEOUT_STAGE"] = "doctor"
    try:
        r = llm.ask("Reply with the single word: ready", system="You are a test. Reply with one word.",
                    tag="doctor")
    except llm.ModelError as e:
        say("\nThat didn't work (%s): %s" % (e.kind, e))
        if old:
            llm.save_config(old)
            say("Kept your previous setting.")
        return 1
    say("It answered: %r  (%d ms%s)" % (r.text.strip()[:60], r.ms,
        (", %s in / %s out tokens" % (r.input_tokens, r.output_tokens)) if r.input_tokens else ""))
    say("Saved. Every call from llm.ask() now goes to %s." % backend)
    say("This counts as a %s model for the finish line. Change it with --class small|mid|frontier." % cfg["model_class"])
    if len(r.text.strip()) > 40:
        say("Note: the reply had extra text around the answer. Some models think out loud; your parsing will need to cope.")
    if backend == "ollama" and r.ms > 5000:
        say("Slow replies often mean the model thinks before answering. Some models can switch that off with --think off;")
        say("if you try it, check the test reply is still clean.")
    return 0


# ---------- stages ----------

def stage_text(idx):
    sid = STAGES[idx][0]
    with open(os.path.join(ROOT, "stages", sid + ".md")) as f:
        text = f.read()
    main, _, hints = text.partition("\n## Hints")
    rungs = [h.strip() for h in re.split(r"\n\s*\d+\.\s", "\n" + hints) if h.strip()]
    return main.strip(), rungs


def cmd_stage(args):
    p = load_progress()
    if "--all" in args:
        for i, (sid, title) in enumerate(STAGES):
            mark = "✓" if sid in p["done"] else ("→" if i == p["stage"] else " ")
            say(" %s %s" % (mark, title))
        return 0
    if p["stage"] >= len(STAGES):
        say("You've finished Ticket Triage. Your results are in traces/. Run: python3 insideout.py trace")
        return 0
    main, _ = stage_text(p["stage"])
    say(main)
    say("\nWhen you think it's done: python3 insideout.py check     Stuck: python3 insideout.py hint")
    return 0


def cmd_hint(args):
    p = load_progress()
    if p["stage"] >= len(STAGES):
        say("No stage left.")
        return 0
    sid = STAGES[p["stage"]][0]
    _, rungs = stage_text(p["stage"])
    used = p["hints"].get(sid, 0)
    if used >= len(rungs):
        say("That's every hint for this stage. The last one is:\n")
        say(rungs[-1] if rungs else "(none)")
        return 0
    say("Hint %d of %d:\n" % (used + 1, len(rungs)))
    say(rungs[used])
    p["hints"][sid] = used + 1
    save_progress(p)
    return 0


def cmd_check(args):
    p = load_progress()
    if p["stage"] >= len(STAGES):
        say("Everything's done.")
        return 0
    sid, title = STAGES[p["stage"]]
    sys.path.insert(0, os.path.join(ROOT, "kit"))
    import checks  # noqa: E402
    importlib.reload(checks)
    fn = getattr(checks, "check_" + sid.split("-")[0])
    say("Checking: %s\n" % title)
    os.environ["INSIDEOUT_STAGE"] = sid
    try:
        results = fn(Ctx())
    except Exception as e:  # a crash in the learner's code shows up here
        results = [(False, "Your code raised %s: %s" % (type(e).__name__, e))]
    for ok, msg in results:
        say(("  ✓ " if ok else "  ✗ ") + msg)
    if results and all(ok for ok, _ in results):
        p["done"].append(sid)
        p["stage"] += 1
        save_progress(p)
        say("\nPassed.")
        if p["stage"] < len(STAGES):
            say("\n" + "═" * 72 + "\n")
            cmd_stage([])
        return 0
    say("\nNot yet. Fix the ✗ lines and run check again.")
    return 1


# ---------- reading and trying ----------

def cmd_show(args):
    ex = tickets("examples")
    if args and not args[0].isdigit():
        t = find_ticket(args[0])
        if not t:
            say("No ticket %s in data/examples.jsonl or data/dev.jsonl." % args[0])
            return 1
        show_ticket(t)
        return 0
    n = int(args[0]) if args else 10
    for t in ex[:n]:
        show_ticket(t, full=False)
    say("─" * 72)
    say("%d of %d tickets in data/examples.jsonl. Show one in full: python3 insideout.py show %s" % (min(n, len(ex)), len(ex), ex[0]["id"] if ex else "ID"))
    return 0


def cmd_try(args):
    if not args:
        say("Which ticket? e.g. python3 insideout.py try %s" % (tickets("examples") or [{"id": "T-0001"}])[0]["id"])
        return 1
    t = find_ticket(args[0])
    if not t:
        say("No ticket %s." % args[0])
        return 1
    show_ticket(t)
    run = "try-" + uuid.uuid4().hex[:8]
    os.environ["INSIDEOUT_RUN"] = run
    os.environ["INSIDEOUT_STAGE"] = "try"
    triage = load_learner("triage")
    say("─" * 72)
    try:
        out = triage.triage(public(t))
    except Exception as e:
        out = None
        say("triage() raised %s: %s" % (type(e).__name__, e))
    calls = [c for c in read_jsonl(llm.TRACE_PATH) if c.get("run") == run]
    for i, c in enumerate(calls, 1):
        say("\nModel call %d  (%s%s, %s ms)" % (i, c.get("backend"), (" " + c["model"]) if c.get("model") else "", c.get("ms")))
        if c.get("system"):
            say("  system: " + c["system"][:600].replace("\n", "\n          "))
        say("  prompt: " + (c.get("prompt") or "")[:600].replace("\n", "\n          "))
        if c.get("ok"):
            say("  reply:  " + (c.get("reply") or "")[:600].replace("\n", "\n          "))
        else:
            say("  error:  %s: %s" % (c.get("error"), c.get("message")))
    say("\nYour triage() returned: %s" % json.dumps(out))
    if t.get("label") is not None:
        say("The team routed it as:  %s" % json.dumps(t["label"]))
    return 0


def cmd_predict(args):
    if not args:
        say('Write what you expect, e.g. python3 insideout.py predict "about 70% of queues right; urgency worse"')
        return 1
    p = load_progress()
    p["predictions"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "text": " ".join(args), "used_by": None})
    save_progress(p)
    say("Noted. Your next eval will show it next to the result.")
    return 0


# ---------- eval ----------

def run_triage_over(items, label, backend=None, model=None, limit=None):
    cfg = llm.load_config()
    if backend or model:
        cfg2 = dict(cfg)
        if backend:
            cfg2.update(DEFAULTS.get(backend, {}))
            cfg2["backend"] = backend
            if not model:
                cfg2["model"] = None
        if model:
            cfg2["model"] = model
        llm.save_config(cfg2)
    try:
        cfg_now = llm.load_config()
        if not cfg_now.get("backend"):
            raise SystemExit("No model chosen yet. Run: python3 insideout.py doctor")
        run = "%s-%s" % (label, time.strftime("%m%d-%H%M%S"))
        os.environ["INSIDEOUT_RUN"] = run
        triage = load_learner("triage")
        items = items[:limit] if limit else items
        preds, errors = {}, {}
        done = 0
        say("Running triage() on %d tickets with %s%s …" % (len(items), cfg_now["backend"], (" " + cfg_now["model"]) if cfg_now.get("model") else ""))

        def one(t):
            try:
                return t["id"], triage.triage(public(t)), None
            except Exception as e:
                return t["id"], None, "%s: %s" % (type(e).__name__, str(e)[:200])

        with cf.ThreadPoolExecutor(max_workers=int(cfg_now.get("concurrency") or 3)) as pool:
            for tid, out, err in pool.map(one, items):
                done += 1
                if err:
                    errors[tid] = err
                preds[tid] = out if isinstance(out, dict) else None
                if done % 10 == 0 or done == len(items):
                    say("  %d/%d" % (done, len(items)))
        calls = [c for c in read_jsonl(llm.TRACE_PATH) if c.get("run") == run]
        return run, preds, errors, calls, cfg_now
    finally:
        if backend or model:
            llm.save_config(cfg)


def call_stats(calls, n_items):
    oks = [c for c in calls if c.get("ok")]
    ms = sorted(c["ms"] for c in oks if c.get("ms") is not None)
    tin = [c["input_tokens"] for c in oks if c.get("input_tokens") is not None]
    tout = [c["output_tokens"] for c in oks if c.get("output_tokens") is not None]
    cost = [c["cost_usd"] for c in oks if c.get("cost_usd") is not None]
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))] if xs else None
    return {
        "calls": len(calls), "failed_calls": len(calls) - len(oks),
        "ms_p50": q(ms, .5), "ms_p95": q(ms, .95),
        "tokens_in_per_ticket": (sum(tin) / n_items) if tin else None,
        "tokens_out_per_ticket": (sum(tout) / n_items) if tout else None,
        "cost_per_1k": (1000 * sum(cost) / n_items) if cost else None,
    }


def cmd_eval(args):
    opts = parse_opts(args, ["model", "backend", "limit"])
    dev = tickets("dev")
    limit = int(opts["limit"]) if opts.get("limit") else None
    p = load_progress()
    pred = next((x for x in reversed(p["predictions"]) if not x.get("used_by")), None)
    run, preds, errors, calls, cfg = run_triage_over(dev, "eval", opts.get("backend"), opts.get("model"), limit)
    items = dev[:limit] if limit else dev
    gold = {t["id"]: t["label"] for t in items}
    ref = ref_score(preds, gold)
    mine, mine_err = None, None
    try:
        score = load_learner("score")
        mine = score.score(preds, gold)
    except NotImplementedError:
        mine_err = "score.py isn't written yet (stage 5)"
    except Exception as e:
        mine_err = "score.py raised %s: %s" % (type(e).__name__, e)
    stats = call_stats(calls, len(items))
    rec = {"run": run, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": cfg["backend"],
           "model": cfg.get("model"), "n": len(items), "full": not limit, "ref": ref,
           "mine": mine if isinstance(mine, dict) else None, "errors": len(errors),
           "prediction": pred["text"] if pred else None, "triage_hash": file_hash("triage.py"), **stats}
    append_jsonl(EVALS, rec)
    os.makedirs(RUNS_DIR, exist_ok=True)
    with open(os.path.join(RUNS_DIR, run + ".json"), "w") as f:
        json.dump({"preds": preds, "errors": errors}, f, ensure_ascii=False, indent=1)
    if pred:
        pred["used_by"] = run
        save_progress(p)

    say("")
    if pred:
        say("You predicted:  %s" % pred["text"])
    say("Result (%d tickets):  queue %s · urgency %s · order id %s · refund %s · all four right %s"
        % (len(items), pct(ref["queue"]), pct(ref["urgency"]), pct(ref["order_id"]), pct(ref["wants_refund"]), pct(ref["all_four"])))
    if mine_err:
        say("Your score.py: %s" % mine_err)
    elif isinstance(mine, dict):
        diffs = [f for f in FIELDS + ["all_four"] if isinstance(mine.get(f), (int, float)) and abs(mine[f] - ref[f]) > 1e-9]
        say("Your score.py agrees with the reference." if not diffs else
            "Your score.py disagrees on: %s (reference above). Worth a look." % ", ".join(diffs))
    say("Time per ticket: p50 %s ms · p95 %s ms%s%s" % (
        stats["ms_p50"], stats["ms_p95"],
        (" · %.0f tokens in, %.0f out per ticket" % (stats["tokens_in_per_ticket"], stats["tokens_out_per_ticket"] or 0)) if stats["tokens_in_per_ticket"] else "",
        (" · about $%.2f per 1,000 tickets at API prices" % stats["cost_per_1k"]) if stats["cost_per_1k"] else ""))
    if errors:
        say("triage() crashed on %d tickets, e.g. %s: %s" % (len(errors), next(iter(errors)), next(iter(errors.values()))))
    if stats["calls"] and stats["failed_calls"] > stats["calls"] / 2:
        bad = next((c for c in calls if not c.get("ok")), {})
        say("Most model calls failed (%s: %s). Run doctor before trusting this result." % (bad.get("error"), bad.get("message")))
    say("\nSee what went wrong: python3 insideout.py failures     Every call: python3 insideout.py trace")
    return 0


def last_full_run():
    runs = [r for r in read_jsonl(EVALS) if r.get("full")]
    return runs[-1] if runs else None


def cmd_failures(args):
    if "--groups" in args:
        path = os.path.join(ROOT, "notes", "failures.csv")
        rows = read_failures(path)
        if not rows:
            say("notes/failures.csv has no tagged failures yet. One line each: ticket_id,what went wrong")
            return 1
        counts = {}
        for _, tag in rows:
            counts[tag] = counts.get(tag, 0) + 1
        say("Your failure groups (%d tagged):\n" % len(rows))
        for tag, n in sorted(counts.items(), key=lambda x: -x[1]):
            say("  %3d  %s" % (n, tag))
        say("\nFix the biggest group first.")
        return 0
    run = last_full_run()
    if not run:
        say("No full eval yet. Run: python3 insideout.py eval")
        return 1
    with open(os.path.join(RUNS_DIR, run["run"] + ".json")) as f:
        data = json.load(f)
    preds = data["preds"]
    wrong = []
    for t in tickets("dev"):
        p = preds.get(t["id"]) or {}
        bad = [fld for fld in FIELDS if p.get(fld) != t["label"].get(fld)]
        if bad:
            wrong.append((t, p, bad))
    say("%d of %d tickets had at least one field wrong in %s (%s%s).\n" % (
        len(wrong), run["n"], run["run"], run["backend"], (" " + run["model"]) if run.get("model") else ""))
    limit = 15 if "--all" not in args else len(wrong)
    for t, p, bad in wrong[:limit]:
        show_ticket(t, full=False)
        for fld in bad:
            say("  %-12s yours: %-16s team: %s" % (fld, json.dumps(p.get(fld)), json.dumps(t["label"].get(fld))))
        if data["errors"].get(t["id"]):
            say("  crashed: " + data["errors"][t["id"]])
    if len(wrong) > limit:
        say("\n… %d more. See all: python3 insideout.py failures --all" % (len(wrong) - limit))
    say("\nTag them in notes/failures.csv (ticket_id,what went wrong), then: python3 insideout.py failures --groups")
    return 0


def read_failures(path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.lower().startswith("ticket_id"):
                    continue
                tid, _, tag = line.partition(",")
                if tid.strip() and tag.strip():
                    rows.append((tid.strip(), tag.strip().lower()))
    except OSError:
        pass
    return rows


def cmd_compare(args):
    runs = [r for r in read_jsonl(EVALS) if r.get("full")]
    if not runs:
        say("No full eval runs yet.")
        return 1
    say("%-22s %-28s %6s %6s %8s %8s %10s %9s" % ("run", "model", "queue", "all 4", "p50 ms", "p95 ms", "tok/ticket", "$/1k"))
    for r in runs:
        name = (r["backend"] + (" " + r["model"] if r.get("model") else ""))[:28]
        tok = (r.get("tokens_in_per_ticket") or 0) + (r.get("tokens_out_per_ticket") or 0)
        say("%-22s %-28s %6s %6s %8s %8s %10s %9s" % (
            r["run"], name, pct(r["ref"]["queue"]), pct(r["ref"]["all_four"]), r.get("ms_p50") or "—",
            r.get("ms_p95") or "—", ("%.0f" % tok) if tok else "—",
            ("%.2f" % r["cost_per_1k"]) if r.get("cost_per_1k") else "—"))
    say("\n$/1k is what 1,000 tickets would cost on a pay-per-token API, when the backend reports it.")
    return 0


# ---------- trace viewer ----------

def cmd_trace(args):
    calls = read_jsonl(llm.TRACE_PATH)[-2000:]
    runs = read_jsonl(EVALS)
    preds = {}
    for r in runs[-12:]:
        try:
            with open(os.path.join(RUNS_DIR, r["run"] + ".json")) as f:
                preds[r["run"]] = json.load(f)
        except OSError:
            pass
    gold = {t["id"]: {"label": t["label"], "subject": t.get("subject", ""), "body": t.get("body", "")[:600]}
            for t in tickets("dev")}
    data = {"calls": calls, "runs": runs, "preds": preds, "gold": gold, "project": "Ticket Triage"}
    with open(os.path.join(ROOT, "kit", "viewer.html")) as f:
        html = f.read()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = os.path.join(ROOT, "traces", "view.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html.replace("/*DATA*/null", blob))
    say("Wrote traces/view.html (%d calls, %d eval runs)." % (len(calls), len(runs)))
    if "--no-open" not in args:
        webbrowser.open("file://" + out)
    return 0


# ---------- finish line ----------
# The server sends a random sample of tickets you've never seen (inputs only), your triage() runs on them with your
# own model, and the server compares your answers with the team's. No model runs on insideout's side, and the
# answers never leave the server. Only totals come back.

SERVER = os.environ.get("INSIDEOUT_SERVER") or "https://fjxdbwjuoqosvyqgqfdo.supabase.co"
PUBLIC_KEY = "sb_publishable_tpZdIJ4el0-A1JPFx19qCQ_VveQhBQE"   # insideout's public site key: it can only start and score runs
PROJECT = "ticket-triage"
FLOORS = {"small": 0.45, "mid": 0.60, "frontier": 0.70}   # used only for the offline test file


def client_id():
    """A random id for this copy of the project, so the server can cap runs per day. It says nothing about you."""
    path = os.path.join(STATE_DIR, "client_id")
    try:
        with open(path) as f:
            cid = f.read().strip()
        if 8 <= len(cid) <= 64:
            return cid
    except OSError:
        pass
    cid = uuid.uuid4().hex
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w") as f:
        f.write(cid)
    return cid


def rpc(name, body):
    req = urllib.request.Request(SERVER.rstrip("/") + "/rest/v1/rpc/" + name, data=json.dumps(body).encode(),
                                 method="POST", headers={"apikey": PUBLIC_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message")
        except Exception:
            msg = None
        if e.code == 404:
            msg = "The finish line isn't open yet. Your evals still work; try submit again later."
        raise SystemExit(msg or "The finish line answered with HTTP %d. Try again in a minute." % e.code)
    except urllib.error.URLError as e:
        raise SystemExit("Can't reach the finish line (%s). Check your connection and try again." % e.reason)


def cmd_submit(args):
    cfg = llm.load_config()
    if not cfg.get("backend"):
        say("Choose a model first: python3 insideout.py doctor")
        return 1
    offline = os.environ.get("INSIDEOUT_HIDDEN")
    if offline:
        hidden = read_jsonl(offline)
        items, session = [public(t) for t in hidden], None
    else:
        say("Asking the finish line for tickets …")
        start = rpc("finish_start", {"p_project": PROJECT, "p_client": client_id()})
        items, session = start.get("items") or [], start.get("session")
    say("The finish line: %d tickets you've never seen, scored the same way as your evals." % len(items))
    run, preds, errors, calls, cfg = run_triage_over(items, "submit")
    good = [c for c in calls if c.get("ok")]
    if calls and len(good) < len(items) / 2:
        bad = next((c for c in calls if not c.get("ok")), {})
        say("\nYour model answered only %d of %d calls, so this run wasn't sent for scoring (it won't count)." % (len(good), len(calls)))
        say("The first problem was %s: %s" % (bad.get("error"), bad.get("message")))
        say("Fix it with: python3 insideout.py doctor     Then submit again.")
        return 1
    cls = cfg.get("model_class") or "mid"
    if offline:
        ref = ref_score(preds, {t["id"]: t["label"] for t in hidden})
        floor = FLOORS.get(cls, 0.6)
        passed = ref["all_four"] >= floor
    else:
        res = rpc("finish_score", {"p_session": session, "p_outputs": preds,
                                   "p_meta": {"backend": cfg["backend"], "model": cfg.get("model"), "model_class": cls}})
        fields = res.get("fields") or {}
        ref = {f: fields.get(f) for f in FIELDS}
        ref["all_four"] = res.get("all")
        floor, passed = res.get("floor"), bool(res.get("passed"))
    runs = [r for r in read_jsonl(EVALS) if r.get("full")]
    first, best = (runs[0]["ref"]["all_four"], max(r["ref"]["all_four"] for r in runs)) if runs else (None, None)
    rec = {"run": run, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": cfg["backend"], "model": cfg.get("model"),
           "model_class": cls, "ref": ref, "floor": floor, "passed": passed, "first_dev": first, "best_dev": best,
           "server": not offline, **call_stats(calls, len(items))}
    append_jsonl(os.path.join(ROOT, "traces", "submissions.jsonl"), rec)
    say("\nAll four right: %s   (the bar for a %s model is %s)" % (pct(ref["all_four"]), cls, pct(floor)))
    say("Queue %s · urgency %s · order id %s · refund %s" % (pct(ref["queue"]), pct(ref["urgency"]), pct(ref["order_id"]), pct(ref["wants_refund"])))
    if first is not None:
        say("On the dev set you went from %s on your first eval to %s at your best." % (pct(first), pct(best)))
    if errors:
        say("triage() crashed on %d of these tickets; they count as wrong." % len(errors))
    say("\n" + ("Passed. Ticket Triage is done." if passed else "Not over the bar yet. Look at your failures, change one thing, eval, and submit again."))
    return 0


# ---------- the checks need a little context ----------

class Ctx:
    root = ROOT
    queues = QUEUES
    urgencies = URGENCIES
    fields = FIELDS

    def tickets(self, name):
        return tickets(name)

    def public(self, t):
        return public(t)

    def learner(self, module):
        return load_learner(module)

    def evals(self):
        return read_jsonl(EVALS)

    def calls(self):
        return read_jsonl(llm.TRACE_PATH)

    def progress(self):
        return load_progress()

    def config(self):
        return llm.load_config()

    def run_preds(self, run):
        try:
            with open(os.path.join(RUNS_DIR, run + ".json")) as f:
                return json.load(f)["preds"]
        except (OSError, ValueError, KeyError):
            return {}

    def failures_csv(self):
        return read_failures(os.path.join(ROOT, "notes", "failures.csv"))

    def submissions(self):
        return read_jsonl(os.path.join(ROOT, "traces", "submissions.jsonl"))

    def text(self, rel):
        try:
            with open(os.path.join(ROOT, rel)) as f:
                return f.read()
        except OSError:
            return ""

    ref_score = staticmethod(ref_score)


# ---------- command line ----------

def parse_opts(args, names):
    out, i = {}, 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and a[2:] in names and i + 1 < len(args):
            out[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return out


COMMANDS = {"doctor": cmd_doctor, "stage": cmd_stage, "check": cmd_check, "hint": cmd_hint,
            "show": cmd_show, "try": cmd_try, "predict": cmd_predict, "eval": cmd_eval,
            "failures": cmd_failures, "compare": cmd_compare, "trace": cmd_trace, "submit": cmd_submit}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        say(__doc__.strip())
        return 0 if not argv else 1
    return COMMANDS[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
