# Notebooks

Exploratory analysis and baseline experiments go here. Load processed data with:

```python
import pandas as pd  # not a project dependency; install in your own env
df = pd.read_json("data/processed/samples.jsonl", lines=True)
```

Rules:
- Split by participant (`interview-integrity split`) **before** fitting anything; never
  split augmented variants of one recording across partitions.
- Do not commit notebooks with embedded raw candidate transcripts or media in outputs —
  clear outputs before committing.
- The baseline model choice is still a pending team decision (see `docs/decisions.md`).
