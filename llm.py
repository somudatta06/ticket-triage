"""
llm.py: call a language model with whatever you already have. No API key needed.

Backends (pick one with `python3 insideout.py doctor`; it saves your choice):
  claude   your own Claude Code login       runs `claude -p`
  codex    your own Codex login             runs `codex exec`
  copilot  your own GitHub Copilot login    runs `copilot -p`
  ollama   a model on your own computer     talks to `ollama serve`
  openai   any OpenAI-compatible server     LM Studio, vLLM, OpenRouter, Groq, or a key you have
  fake     scripted replies                 used only by the checks, to test failures

Every call is written to traces/calls.jsonl: what was sent, what came back, tokens, time.
`ask()` never retries. Deciding when to retry is your job (stage 7).

You can read this file, but you don't need to change it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, ".insideout", "config.json")
TRACE_PATH = os.path.join(ROOT, "traces", "calls.jsonl")
BACKENDS = ["claude", "codex", "copilot", "ollama", "openai", "fake"]


# ---------- errors your code can catch ----------

class ModelError(Exception):
    """Something went wrong calling the model."""
    kind = "error"


class Timeout(ModelError):
    """The model took longer than the timeout. Often worth one more try."""
    kind = "timeout"


class RateLimited(ModelError):
    """Too many calls, too fast, or your plan's limit is used up for now. Wait, then try again."""
    kind = "rate_limited"


class Unavailable(ModelError):
    """The backend or model can't be used: not installed, not logged in, or no access to that model.
    Trying again won't help."""
    kind = "unavailable"


class BadReply(ModelError):
    """The model answered, but with nothing usable (empty, cut off, or unreadable)."""
    kind = "bad_reply"


# ---------- what a call returns ----------

@dataclass
class Reply:
    text: str                       # what the model said (a JSON string if you passed a schema)
    model: str                      # the model that answered, if the backend says
    backend: str
    input_tokens: Optional[int]     # None when the backend doesn't report it
    output_tokens: Optional[int]
    cost_usd: Optional[float]       # what this call would cost on a pay-per-token API, if known
    ms: int                         # wall-clock time for the call
    call_id: str


# ---------- settings ----------

def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


_FAKE: Optional[Callable] = None


def use_fake(responder: Optional[Callable]) -> None:
    """Route every call to `responder(prompt=..., system=..., schema=...)` instead of a model.
    It returns the reply text, or raises one of the errors above. The checks use this."""
    global _FAKE
    _FAKE = responder


# ---------- the one function you call ----------

def ask(prompt: str, system: Optional[str] = None, *, model: Optional[str] = None,
        backend: Optional[str] = None, schema: Optional[dict] = None,
        timeout: Optional[float] = None, tag: Optional[str] = None) -> Reply:
    """Send one prompt and get one reply.

    prompt   the user message
    system   instructions for the model (optional)
    model    which model; defaults to the one you chose in doctor
    schema   a JSON Schema; backends that support it will only return JSON that fits it
    timeout  seconds before giving up (default from config, else 90)
    tag      a label stored in the trace, e.g. the ticket id
    """
    cfg = load_config()
    backend = backend or ("fake" if _FAKE else cfg.get("backend"))
    if not backend:
        raise Unavailable("No model backend chosen yet. Run: python3 insideout.py doctor")
    if backend not in BACKENDS:
        raise Unavailable("Unknown backend %r. Use one of: %s" % (backend, ", ".join(BACKENDS)))
    model = model or cfg.get("model") or None
    timeout = float(timeout or cfg.get("timeout") or 90)

    call_id = uuid.uuid4().hex[:12]
    started = time.time()
    record = {
        "call_id": call_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": backend,
        "model": model, "system": system, "prompt": prompt, "schema": bool(schema), "tag": tag,
        "run": os.environ.get("INSIDEOUT_RUN"), "stage": os.environ.get("INSIDEOUT_STAGE"),
    }
    try:
        fn = {"claude": _claude, "codex": _codex, "copilot": _copilot, "ollama": _ollama,
              "openai": _openai, "fake": _fake}[backend]
        text, used_model, tin, tout, cost = fn(prompt, system, model, schema, timeout, cfg)
        if text is None or not str(text).strip():
            raise BadReply("The model returned an empty reply.")
        reply = Reply(text=str(text), model=used_model or model or "", backend=backend,
                      input_tokens=tin, output_tokens=tout, cost_usd=cost,
                      ms=int((time.time() - started) * 1000), call_id=call_id)
        record.update({"ok": True, "reply": reply.text, "model": reply.model, "input_tokens": tin,
                       "output_tokens": tout, "cost_usd": cost, "ms": reply.ms})
        return reply
    except ModelError as e:
        record.update({"ok": False, "error": e.kind, "message": str(e)[:500],
                       "ms": int((time.time() - started) * 1000)})
        raise
    finally:
        if backend != "fake" or os.environ.get("INSIDEOUT_TRACE_FAKE"):
            _write_trace(record)


def _write_trace(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TRACE_PATH), exist_ok=True)
        with open(TRACE_PATH, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------- backends ----------

def _clean_dir() -> str:
    """An empty folder to run agent CLIs in, so they don't read this project's AGENTS.md or CLAUDE.md
    as part of the system you're testing."""
    d = os.path.join(tempfile.gettempdir(), "insideout-clean")
    os.makedirs(d, exist_ok=True)
    return d


def _run(cmd, stdin_text, timeout, cwd):
    try:
        p = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
    except FileNotFoundError:
        raise Unavailable("%s isn't installed or isn't on your PATH." % cmd[0])
    except subprocess.TimeoutExpired:
        raise Timeout("No reply within %ds." % timeout)
    return p


def _classify_failure(text: str) -> ModelError:
    t = (text or "").lower()
    if "429" in t or "rate limit" in t or "rate_limit" in t or "usage limit" in t or "too many requests" in t:
        return RateLimited(text.strip()[-300:])
    if any(s in t for s in ("401", "403", "not logged in", "log in", "login", "authenticat",
                             "not available", "not found", "404", "does not exist", "no access")):
        return Unavailable(text.strip()[-300:])
    if "timed out" in t or "timeout" in t:
        return Timeout(text.strip()[-300:])
    return ModelError(text.strip()[-300:] or "The backend failed without saying why.")


def _claude(prompt, system, model, schema, timeout, cfg):
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    if system:
        cmd += ["--system-prompt", system]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    p = _run(cmd, prompt, timeout, _clean_dir())
    try:
        d = json.loads(p.stdout)
    except ValueError:
        raise _classify_failure(p.stderr or p.stdout)
    if d.get("is_error"):
        status = d.get("api_error_status")
        msg = str(d.get("result") or "")
        if status == 429:
            raise RateLimited(msg)
        if status in (401, 403, 404):
            raise Unavailable(msg)
        raise _classify_failure(msg)
    text = d.get("structured_output")
    text = json.dumps(text) if text is not None else d.get("result")
    u = d.get("usage") or {}
    tin = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                             "cache_creation_input_tokens")) or None
    tout = u.get("output_tokens")
    used = next(iter((d.get("modelUsage") or {}).keys()), None)
    cost = d.get("total_cost_usd") or None
    return text, used, tin, tout, cost


def _codex(prompt, system, model, schema, timeout, cfg):
    work = tempfile.mkdtemp(prefix="insideout-codex-")
    try:
        out = os.path.join(work, "last.txt")
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral",
               "-s", "read-only", "-o", out]
        if model:
            cmd += ["-m", model]
        if schema:
            sf = os.path.join(work, "schema.json")
            with open(sf, "w") as f:
                json.dump(schema, f)
            cmd += ["--output-schema", sf]
        full = ("<instructions>\n%s\n</instructions>\n\n%s" % (system, prompt)) if system else prompt
        cmd += [full]
        p = _run(cmd, None, timeout, work)
        text = None
        if os.path.exists(out):
            with open(out) as f:
                text = f.read().strip()
        tin = tout = None
        for line in (p.stdout or "").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            u = ev.get("usage") if isinstance(ev, dict) else None
            if isinstance(u, dict):
                tin = (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0)
                tout = u.get("output_tokens")
        if p.returncode != 0 and not text:
            raise _classify_failure(p.stderr or p.stdout)
        return text, model, tin, tout, None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _copilot(prompt, system, model, schema, timeout, cfg):
    full = ("<instructions>\n%s\n</instructions>\n\n%s" % (system, prompt)) if system else prompt
    if schema:
        full += "\n\nReply with JSON only, matching this JSON Schema:\n" + json.dumps(schema)
    cmd = ["copilot", "-p", full, "-s", "--no-custom-instructions", "--no-ask-user"]
    if model:
        cmd += ["--model", model]
    p = _run(cmd, None, timeout, _clean_dir())
    if p.returncode != 0:
        raise _classify_failure(p.stderr or p.stdout)
    return p.stdout.strip(), model, None, None, None


def _http_json(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 429:
            raise RateLimited(detail)
        if e.code in (401, 403, 404):
            raise Unavailable("HTTP %d: %s" % (e.code, detail))
        raise ModelError("HTTP %d: %s" % (e.code, detail))
    except urllib.error.URLError as e:
        if "timed out" in str(e.reason).lower():
            raise Timeout("No reply within %ds." % timeout)
        raise Unavailable("Can't reach %s (%s)." % (url, e.reason))
    except TimeoutError:
        raise Timeout("No reply within %ds." % timeout)


def _messages(prompt, system):
    msgs = [{"role": "system", "content": system}] if system else []
    return msgs + [{"role": "user", "content": prompt}]


def _ollama(prompt, system, model, schema, timeout, cfg):
    if not model:
        raise Unavailable("Pick an Ollama model in doctor, e.g. one you've pulled with `ollama pull`.")
    base = cfg.get("ollama_url") or "http://localhost:11434"
    body = {"model": model, "messages": _messages(prompt, system), "stream": False}
    if schema:
        body["format"] = schema
    if cfg.get("ollama_think") is not None:
        body["think"] = bool(cfg["ollama_think"])
    try:
        d = _http_json(base + "/api/chat", body, {}, timeout)
    except Unavailable as e:
        if "Can't reach" in str(e):
            raise Unavailable("Ollama isn't running. Start it with: ollama serve")
        raise Unavailable("%s (is the model pulled? try: ollama pull %s)" % (e, model))
    return (d.get("message") or {}).get("content"), d.get("model"), d.get("prompt_eval_count"), \
        d.get("eval_count"), None


def _openai(prompt, system, model, schema, timeout, cfg):
    base = (cfg.get("openai_base_url") or "http://localhost:1234/v1").rstrip("/")
    key_env = cfg.get("openai_key_env") or "OPENAI_API_KEY"
    headers = {"Authorization": "Bearer " + os.environ[key_env]} if os.environ.get(key_env) else {}
    body = {"model": model, "messages": _messages(prompt, system)}
    if schema:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "output", "schema": schema}}
    d = _http_json(base + "/chat/completions", body, headers, timeout)
    try:
        text = d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise BadReply("Unexpected reply shape: %s" % json.dumps(d)[:300])
    u = d.get("usage") or {}
    return text, d.get("model"), u.get("prompt_tokens"), u.get("completion_tokens"), None


def _fake(prompt, system, model, schema, timeout, cfg):
    if not _FAKE:
        raise Unavailable("The fake backend is only for checks.")
    text = _FAKE(prompt=prompt, system=system, schema=schema)
    return text, "fake", None, None, None


def reply_dict(r: Reply) -> dict:
    return asdict(r)
