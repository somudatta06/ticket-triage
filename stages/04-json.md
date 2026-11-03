# Four answers, always valid

The team needs four things per ticket, not one: the queue, the urgency, the order id and whether the customer wants a refund (docs/routing-guide.md). The code that receives your answer will break on anything that isn't clean, so "usually valid" isn't good enough.

Models wrap JSON in code fences, add a friendly sentence, write "Returns" with a capital R, or invent a queue that doesn't exist. Your job is to make that never reach the rest of the system.

## Do this

In `triage.py`, write two helpers and use them in `triage()`:

`normalize_order_id(text)` returns `"ORD-48213"` for any way a customer or model writes an order id (`#48213`, `order 48213`, `ORD48213`, `ord-48213`, `48213`). It returns `None` for anything else: empty, "null", tracking numbers, invoice numbers, six digits. If there are several, it returns the first.

`parse_reply(text)` finds the JSON object in the model's reply and returns exactly:

```json
{"queue": "...", "urgency": "...", "order_id": "ORD-..." or null, "wants_refund": true or false}
```

- `queue` and `urgency` are required. Lowercase them, treat spaces and hyphens as underscores, and they must be in `QUEUES` / `URGENCIES`.
- `order_id` goes through `normalize_order_id`. Missing means `None`.
- `wants_refund` must end up `True` or `False`. Accept the strings "true" and "false". Missing means `False`.
- Raise `ValueError` if the reply has no JSON object, the JSON is broken, or a value isn't allowed.

Then `triage()` asks for all four fields and parses the reply. If `parse_reply` raises, ask once more and say what was wrong. If you like, pass a JSON Schema to `ask(..., schema=...)`; backends that support it will stick to it.

## Done when

Both helpers pass a set of messy test replies, and `triage()` asks again, once, when the first reply can't be used. These checks use a scripted fake model, so they're exact and don't use your plan.

## Hints

1. Find the JSON with the first `{` and the last `}` in the text, then `json.loads` that slice.

2. For order ids, a regular expression does it: optional `ORD`, `order` or `#`, optional space or hyphen, then exactly five digits that aren't part of a longer number.

3. The repair call can be short: give the model its previous reply and the error message, and ask for only the JSON.

4. A shape for triage():

```python
def triage(ticket):
    prompt = ticket["subject"] + "\n\n" + ticket["body"]
    reply = ask(prompt, system=SYSTEM, tag=ticket["id"])
    try:
        return parse_reply(reply.text)
    except ValueError as e:
        fix = ask(prompt + "\n\nYour last reply was:\n" + reply.text + "\n\nIt couldn't be used: " + str(e)
                  + "\nReply with only the JSON object.", system=SYSTEM, tag=ticket["id"])
        return parse_reply(fix.text)
```
