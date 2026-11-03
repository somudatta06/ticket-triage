# When the model fails

Real models time out, hit rate limits, go down and sometimes answer with nothing useful. A router that crashes on any of those drops a customer's ticket on the floor. You need to decide, for each kind of failure, whether to wait and try again or to stop and hand the ticket to a person.

## Do this

Update `triage()` so that:

- On `RateLimited` or `Timeout`: wait (`time.sleep`), then try again, longer each time. At most 3 calls in total.
- On `Unavailable`: don't retry. It won't help.
- On a reply `parse_reply` can't use: ask once more, as in stage 4.
- When it gives up for any reason, it returns `{"queue": "needs_human", "urgency": "normal", "order_id": None, "wants_refund": False}` instead of crashing.

The errors live in `llm.py`: `from llm import ask, RateLimited, Timeout, Unavailable`.

## Done when

`triage()` handles five scripted failures correctly. These use a fake model and a fake clock, so the check is instant.

## Hints

1. A loop over attempts with try/except, and a wait like `time.sleep(2 ** attempt)`, is all this needs.

2. Keep the repair attempt and the retries separate. A rate limit isn't the model's fault; a bad reply is.

3. One way to lay it out: a helper `call_with_retries(prompt)` that returns a Reply or raises, and `triage()` around it that parses, repairs once, and falls back to `needs_human`.
