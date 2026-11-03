"""
triage.py: your ticket router. This is the file you build up, one stage at a time.

A ticket looks like this (see data/examples.jsonl):
    {"id": "T-0012", "channel": "email", "subject": "...", "body": "...", "lang": "en"}

By the end, triage(ticket) returns the four things the team needs (docs/routing-guide.md):
    {"queue": "returns", "urgency": "normal", "order_id": "ORD-48213", "wants_refund": True}
"""
from llm import ask

QUEUES = ["billing", "shipping", "returns", "order_changes", "product", "account", "other"]
URGENCIES = ["urgent", "high", "normal"]


def triage(ticket: dict) -> dict:
    # Stage 2: ask your model which queue this ticket belongs in, and return {"queue": ...}.
    # Run it on one ticket with: python3 insideout.py try T-0001
    raise NotImplementedError("Stage 2: write your first model call here.")
