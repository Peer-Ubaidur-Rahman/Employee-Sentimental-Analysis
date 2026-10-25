# Dataset provenance and licence

| File | Rows | Purpose |
|------|------|---------|
| `employee_feedback.csv` | 732 | Training + held-out test split |
| `challenge_set.csv` | 45 | Handwritten sentences never used in training |
| `build_synthetic_dataset.py` | - | The script that generates both files (seed 42) |

**All data is SYNTHETIC.** It was written for this project by its author, partly from
sentence templates and partly by hand. It is **not** real employee feedback and was not
copied from any external dataset, website, or survey. It is released under **CC0 1.0**
(public domain), so there are no licensing restrictions on use.

## Why this matters for the metrics

* Template-generated sentences share phrases across the train/test split, so a random
  split is **very optimistic**. The score on it shows the pipeline is wired correctly; it
  does **not** show how the model will behave on real employee comments.
* `challenge_set.csv` is a harder check, but it is also synthetic and tiny (45 rows).
* To get a meaningful accuracy figure you must train and evaluate on real, consented,
  labelled feedback from your own organisation (or a properly licensed public dataset
  that you download and cite yourself), keeping the columns `feedback,sentiment`.
