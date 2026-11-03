# Connect a model

Everything in this project runs on a model you already have: your Claude Code or Codex login, GitHub Copilot, a model on your own computer, or a key. insideout never sees your login and never pays for or meters your calls.

`llm.py` gives you one function, `ask()`, that talks to whichever you choose. Every call it makes is written to `traces/calls.jsonl`, so you can always see exactly what was sent and what came back.

## Do this

Run `python3 insideout.py doctor`. It lists what this computer has. Pick one and test it:

```
python3 insideout.py doctor --use claude --model <a model your account has>
```

A small, fast model is the right choice here. It uses less of your plan, and this project is about how you build around a model, not which one is biggest.

## Done when

doctor has saved a backend and it has answered once.

## Hints

1. If doctor finds nothing, install one tool. Ollama is free and runs on your computer: install it, then `ollama pull qwen3:4b`. docs/running-models.md lists every option.

2. "Unavailable" usually means you're not logged in, or the model name isn't one your account has. Agent tools want the full model name, not a short alias. Leave out `--model` to use the tool's default.

3. With Claude Code: run `claude` once and log in, then `python3 insideout.py doctor --use claude`. With Codex: `codex login`, then `--use codex`.
