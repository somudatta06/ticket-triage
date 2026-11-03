# Running models

This project never needs an API key from insideout, and insideout never pays for or sees your calls. Use whatever you already have. Run `python3 insideout.py doctor` to see what this computer has.

| Option | Costs you | Setup | Good for |
|---|---|---|---|
| **Claude Code** (`--use claude`) | Your Claude plan's usage | `claude`, log in once | Every stage |
| **Codex** (`--use codex`) | Your ChatGPT plan's usage | `codex login` | Every stage |
| **GitHub Copilot CLI** (`--use copilot`) | Your Copilot plan | `copilot`, log in once | Every stage. Doesn't report tokens |
| **Ollama** (`--use ollama`) | Nothing; it runs on your computer | Install Ollama, `ollama pull <model>` | Every stage, slower on small machines |
| **LM Studio** (`--use openai --url http://localhost:1234/v1`) | Nothing; on your computer | Install, load a model, start the server | Every stage |
| **Any OpenAI-compatible API** (`--use openai --url <base> --key-env <VAR>`) | That provider's prices or free tier | A key in an environment variable | Every stage |

## How much it uses

A full eval is about 80 to 160 short calls (one per ticket, plus repairs). On a laptop model that's roughly 5 to 15 minutes; through an agent tool's subscription it's usually a few minutes. Through the whole project you'll make a few hundred calls. On a subscription that's a small part of a normal day's usage. Pick a small, fast model: this project is about how you build around a model, not which one is biggest.

## Models on your own computer

Rough guide for Ollama or LM Studio. Smaller models are faster and still useful here, and the finish line judges them against a lower bar.

| Memory (RAM) | Model size that runs comfortably |
|---|---|
| 8 GB | about 1 to 4 billion parameters |
| 16 GB | up to about 8 billion |
| 32 GB or more | about 14 to 30 billion |

## Notes

- Agent tools (Claude Code, Codex, Copilot) are built for coding sessions, so each call takes a second or two longer than a raw API. That's fine for this project.
- `llm.py` runs them from an empty folder, so this project's AGENTS.md doesn't leak into the system you're testing. Your own personal settings for those tools (like a global CLAUDE.md) may still be included. For the cleanest numbers, compare models on the same tool.
- Free API tiers change often, and some use what you send to train their models. Read their terms before sending anything private.
