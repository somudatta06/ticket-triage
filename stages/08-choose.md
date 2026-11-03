# Pick a model

Bigger isn't automatically better. A smaller model can match a big one on a narrow task like this at a fraction of the time and cost. Teams that ship pick with numbers, not with a leaderboard.

## Do this

Run a full eval on a second model or backend, for example a smaller and a larger model from the same tool, or your plan against a local model:

```
python3 insideout.py eval --model <another model>
python3 insideout.py eval --backend ollama --model qwen3:4b
python3 insideout.py compare
```

`compare` shows quality, p50 and p95 time per ticket, tokens per ticket and, when known, what 1,000 tickets would cost on a pay-per-token API. `python3 insideout.py trace` draws them on one chart.

Write `notes/decision.md`: which model you'd ship and why, using those numbers. Say what you'd give up.

## Done when

You've run full evals on two different models, and your decision names one and uses numbers.

## Hints

1. If the two are within a couple of points on quality, latency and cost usually decide it.

2. Look at *which* tickets each model gets wrong (`failures` after each eval). A model that misses urgent tickets is worse than its average says.
