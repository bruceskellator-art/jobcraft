# eval/

This directory holds YAML-defined eval suites for JobCraft's AI components.

Eval suites are wired up and runnable in **Phase 5**. See spec §4.5 and §5 for the
full design.

## Planned suites (Phase 5+)

| Suite | What it tests |
|---|---|
| `resume_quality_v1` | Resume generation quality — groundedness, fit, ATS keywords, length |
| `extraction_accuracy_v1` | Structured job extraction — field accuracy against labelled JDs |
| `match_consistency_v1` | Matcher reproducibility and calibration against human-scored matches |
| `status_classification_v1` | Email status classifier — precision/recall against labelled email fixtures |

## Layout

```
eval/
  README.md          # this file
  suites/            # YAML test case files go here (Phase 5)
    .gitkeep
```

## Running evals (Phase 5+)

```bash
# Run a suite against the active prompt version
jobcraft eval run resume_quality_v1

# Run against a specific prompt version
jobcraft eval run resume_quality_v1 --prompt-version=resume_generation_v2

# View results in the admin dashboard
open http://localhost:3000/admin/evals
```

Eval results are stored in the `eval_runs` Postgres table and visualised at
`/admin/evals`. CI fails if aggregate scores drop below the baseline recorded
when the suite was first promoted.
