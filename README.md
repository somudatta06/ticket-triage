# Ticket Triage

Build the part of a support desk that reads every incoming ticket and decides where it goes: which queue, how urgent, which order, and whether the customer wants their money back. Then do what the job really is: measure it, read its failures, fix the biggest group, survive a flaky model, and pick the model you'd actually ship.

It runs on the model you already have: your Claude Code or Codex login, GitHub Copilot, a model on your own computer, or a key. insideout never sees your login and never pays for or meters your calls. The store, its customers and tickets are simulated.

## Start

With a coding agent (Claude Code, Codex, Copilot in VS Code, Cursor), open this folder and say:

> Read AGENTS.md and start the project.

Or on your own:

```
python3 insideout.py doctor      # choose the model you'll use
python3 insideout.py stage       # read what to do
python3 insideout.py check       # when you think it's done
```

You need Python 3.9 or newer. Nothing to install.

## What you'll build

1. Connect a model
2. Route your first ticket
3. Read the tickets yourself
4. Four answers, always valid
5. Measure it
6. Find what breaks, fix the biggest group
7. When the model fails
8. Pick a model
9. The finish line: tickets you've never seen

## What's here

| | |
|---|---|
| `triage.py`, `score.py` | Your code. |
| `notes/` | Your own judgments: what you noticed, how you grouped failures, which model you'd ship. |
| `docs/routing-guide.md` | The rules the team routes by. |
| `data/examples.jsonl` | Labelled tickets to read and to borrow examples from. |
| `data/dev.jsonl` | Labelled tickets your evals run on. |
| `llm.py` | `ask()`: one way to call whichever model you chose. Every call is written to `traces/`. |
| `insideout.py` | Stages, checks, evals, the trace viewer, the finish line. |

Your traces and progress stay on your computer.
