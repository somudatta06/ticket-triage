"""
score.py: how good is triage()? You write the scoring in stage 5.

preds: {ticket_id: the dict triage() returned, or None if it crashed}
gold:  {ticket_id: the team's label, e.g. {"queue": "billing", "urgency": "high", "order_id": None, "wants_refund": True}}
"""


def score(preds: dict, gold: dict) -> dict:
    # Stage 5: return the share of tickets right for each field, how many had all four right,
    # and a confusion table of queues. The stage brief has the exact shape.
    raise NotImplementedError("Stage 5")
