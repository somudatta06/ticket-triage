# Find what breaks, fix the biggest group

Now the loop that the job is really about. Read the failures, sort them into groups, count the groups, fix the biggest one, and measure again. Guessing at prompt tweaks without this is how teams lose months.

## Do this

```
python3 insideout.py failures
```

For each wrong ticket, decide what went wrong in a few plain words, and add a line to `notes/failures.csv`:

```
T-0031,damaged item routed to billing
T-0040,tracking number taken as order id
```

Reuse the same words for the same problem so they group. Then count them:

```
python3 insideout.py failures --groups
```

Fix the biggest group in `triage.py`. Usually that means putting the guide's rules and definitions in your instructions, or adding a few examples from `data/examples.jsonl`. Then eval again **with the same model**.

Don't paste tickets from `data/dev.jsonl` into your prompt. The finish line uses tickets you've never seen, and it will show.

## Done when

You've tagged at least 10 real failures, and after changing triage.py the same model beats your first eval by at least 3 points on all four.

## Hints

1. Do the tagging yourself. Deciding what kind of mistake it is is the skill. Your AI assistant can show you tickets, but don't let it label them.

2. If most failures are one rule from the guide, put that rule in the system prompt in plain words, with one example.

3. Eval numbers move a little from run to run even with no change. If an improvement is only a point or two, run it again before you believe it.

4. If a field got *worse* after your change, look at what your new prompt added. Models copy what they see: put an example order number like 48213 in your instructions and some replies will return it for tickets that have no order at all. Compare `failures` before and after.
