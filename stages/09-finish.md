# The finish line

Your evals used tickets you've seen. The finish line uses tickets you haven't, scored the same way. This is where a prompt that memorised the dev set gets found out.

The bar depends on the size of model you're using, so a laptop model and a frontier model are judged fairly. You set that in doctor with `--class small|mid|frontier`.

## Do this

```
python3 insideout.py submit
```

You can submit more than once. Your best counts.

## Done when

You're over the bar for your model class.

## Hints

1. If you're close, look at which fields are low in the result. Order ids and refunds are often the cheapest points.

2. If the finish line is much lower than your dev evals, your prompt is fitted to the dev tickets. Take dev examples out and use rules and examples from data/examples.jsonl instead.
