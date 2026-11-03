# Measure it

You can't tell whether a change helped by reading three outputs. You need a number you trust, on tickets the team has already labelled. That number is your eval, and from here on every change gets judged by it.

## Do this

Write `score(preds, gold)` in `score.py`. It returns:

```python
{
  "queue": 0.0,          # share of gold tickets with the right queue
  "urgency": 0.0,
  "order_id": 0.0,
  "wants_refund": 0.0,
  "all_four": 0.0,       # share with all four right
  "confusion": {"billing": {"billing": 31, "returns": 2}, ...}   # gold queue → your queue → count
}
```

A ticket whose prediction is `None` (triage crashed) counts as wrong on every field. In the confusion table its queue is `"error"`.

Then, before you run it, write down what you expect:

```
python3 insideout.py predict "about 75% of queues right, urgency worse"
python3 insideout.py eval
```

## Done when

`score()` gets a test case exactly right, and you've run a full eval with a prediction written first.

## Hints

1. Loop over `gold`, not `preds`: a ticket triage() skipped still counts.

2. For the confusion table, use `confusion.setdefault(g["queue"], {})` and then count `p["queue"]` (or `"error"` when `p` is None).

3. The eval prints the reference score too. If yours disagrees, yours has a bug.
