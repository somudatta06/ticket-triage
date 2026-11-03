# Route your first ticket

The team gets hundreds of tickets a day and sorts each one into a queue by hand. Your first job: have the model do the sorting.

Start as simply as you can: one call, one answer. You'll see what the model gets right with almost no help, and that becomes the baseline everything later is measured against.

## Do this

In `triage.py`, make `triage(ticket)` ask your model which queue the ticket belongs in, and return `{"queue": "<one of QUEUES>"}`.

Try it on one ticket and read the call it made:

```
python3 insideout.py try T-0001
```

## Done when

`triage()` returns a valid queue for 3 tickets, using your model.

## Hints

1. `ask(prompt, system=...)` returns a Reply. The model's answer is `reply.text`.

2. Tell the model the allowed queues and ask for one word back. Then clean the answer: strip spaces, lowercase it, and check it's in `QUEUES`.

3. A shape that works:

```python
def triage(ticket):
    system = "You route support tickets. Reply with one word, one of: " + ", ".join(QUEUES)
    reply = ask(ticket["subject"] + "\n\n" + ticket["body"], system=system, tag=ticket["id"])
    queue = reply.text.strip().lower()
    return {"queue": queue if queue in QUEUES else "other"}
```
