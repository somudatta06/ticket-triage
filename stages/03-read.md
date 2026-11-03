# Read the tickets yourself

Before you write a better prompt, read the data. Practitioners who build these systems for a living say it plainly: the most common mistake is reaching for tools and prompts before looking at what you're dealing with.

You'll notice things no prompt template would tell you: tickets that look like billing but are returns, order numbers sitting next to tracking numbers, messages in Spanish, people who are angry but not urgent.

## Do this

Read at least 25 tickets: `python3 insideout.py show 25`. Then read `docs/routing-guide.md`, the rules the team routes by.

Write `notes/reading.md` in your own words:
- what kinds of tickets you see;
- three tickets you'd find hard to route, by id, and why;
- one rule in the guide that surprised you.

This one is yours. If you use an AI assistant, ask it to quiz you, not to write the notes.

## Done when

`notes/reading.md` has your notes (about 80 words or more) and names at least three real tickets.

## Hints

1. Look for tickets where the obvious queue is wrong once you apply the guide's rules. Rule 3 (damaged items) and rule 4 (cancel after shipping) catch a lot of people.

2. Try `python3 insideout.py try <id>` on a ticket you think is hard, and compare your first triage() with the team's label.
