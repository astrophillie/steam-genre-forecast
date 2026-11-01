# Historical v1 ML audit — 26 October 2026

This report records the original v1 workflow: source ingestion and preparation,
SQLite/Parquet tables, exploration, all forecast families, feature experiments,
nested tuning, frozen inference outputs, uncertainty, notebooks and regression
tests. Its September 2025 cutoff, model policy and test counts describe that
stage. The current v2 result is in [Notebook 20](../notebooks/20_fixed_cohort_2027_forecast.ipynb);
later verification is recorded in the [final project audit](FINAL_PROJECT_AUDIT.md).

## Result

The compiled data and existing v1 forecast values reconciled in the recorded
audit. Two agent-assisted review passes examined the implementation fixes and
source/version boundaries. Those automated reviews were not external
certification and did not establish independent predictive accuracy. The source
cutoff, retrospective cohort and reused development windows remained substantive
limitations.

The suite at that stage passed **229 tests**, including 26 additions to the
previous 203. The first adversarial test run reproduced 14 failures before
changes. These failures concerned malformed inputs, numerical overflow and
fail-closed checks; a later agent-assisted review also identified integer
wraparound and incomplete model inventories, subsequently covered by regression
tests. This historical count is not the current research-suite result.

## Requested checks

| Area | Evidence and action |
|---|---|
| Data leakage and split integrity | Past-only lag/rolling inputs, recursive prediction, target-date alignment and completed inner tuning windows inspected and tested. Changing future actuals cannot change predictions. No direct future-target leakage found in the inspected paths. |
| Scaling and preprocessing | Tree features are not globally scaled. Statistical normalisation uses training data only; its mean is now overflow-safe for extreme inputs. Data-driven preprocessing/PCA outside a split is absent. |
| Loss and gradients | No custom PyTorch/TensorFlow loss exists. The installed boosting squared-loss implementation is tested for zero loss/gradient on perfect predictions, positive wrong-prediction loss, finite gradients and agreement with numerical finite differences. No deep-learning dependency was added. |
| Data quality | Original raw hashes, all 20 cached pilot page hashes, SQLite integrity/foreign keys and prepared Parquet values passed. All 795 category-month exploration rows reconciled with SQL. Existing finite/nonnegative activity, duplicate ID/month, label and calendar checks were retained. Genuine spikes were not removed automatically. |
| Model assumptions and metrics | MAE remains primary; RMSE captures large misses; signed error indicates bias; zero-denominator WAPE stays unavailable. Added input/error reconciliation and overflow-safe numeric scoring. Added historical annual-mean and ranking diagnostics because the objective includes annual rankings. Classification metrics are not substituted for numeric errors. |
| Overfitting and selection | Training errors are compared with held-out recursive long-lead errors, with horizon/recursion/distribution differences explicitly noted. Existing cutoff variability, worsened tuning results and repeated development reuse remain visible. No final holdout is invented. |
| Inference and edge cases | New tests cover empty/missing fields, invalid dates, NaN/inf/negative predictions, wrong types, duplicate keys, incomplete model horizons, extreme numbers, unsigned/signed integer overflow, stale actuals and sources, missing outer outcomes and frozen inventory tampering. |
| Frozen artifacts and provenance | Forecast loading now requires all four expected files, including final-fit tuning evidence. Downstream comparisons validate upstream source fingerprints, actual outcomes and complete per-model/category/origin inventories before mixing reports. |

## Defects fixed

1. Cached model and feature reports could be combined after target data changed, creating an unfair comparison. Source hashes and exact target inventories now must match.
2. Missing individual forecast rows could be hidden by other models' rows or skipped by pandas averages. Each model/fold requires a complete lead set, required model/category/origin combinations are checked, and outer outcomes are validated before tuning starts.
3. Scoring could accept nonfinite values, stale error columns and duplicates. It now verifies input schema, finite nonnegative activity, error arithmetic, integer leads and date alignment.
4. Squaring extreme errors could overflow RMSE. Integer subtraction and absolute values could also wrap, even producing negative loss. Numeric columns are normalised to floating values and metrics use magnitude-scaled calculations.
5. Annual summaries accepted some invalid values or incomplete groups. They now require valid month starts, finite nonnegative predictions, nonempty groups and twelve distinct 2027 months. Datetime and string inputs are supported.
6. Extremely large tree inputs could overflow derived features; invalid-dimensional histories and non-month-start targets were insufficiently checked. These now fail explicitly before inference.
7. Statistical fits could return forecasts after unsuccessful optimisation. Those fits now stop rather than silently enter comparison. All 60 existing statistical fits converged and reproduced in this audit.
8. Empty or incomplete checksum inventories could bypass frozen-output verification, and final-fit tuning trials were not included. All four required artifact names and hashes are now checked.
9. Uncertainty construction could consume stale sources or an incomplete selected policy history. It now validates lineage, routes, chronology, actuals, inventories and frozen projection checksums.

No source observations, original target totals or frozen point predictions were changed to improve scores. Earlier model values reproduce within the stated numerical tolerances. The checksum inventory was intentionally extended to protect the existing final-fit trial file.

## Overfitting evidence

For the original gradient-boosting model, mean training one-step MAE and development long-lead MAE across the four origins are:

| Category | Training one-step MAE | Held-out leads 16–27 MAE |
|---|---:|---:|
| Action | 45,443.99 | 341,764.52 |
| Indie | 16,712.36 | 54,346.87 |
| Massively Multiplayer | 20,575.72 | 66,380.81 |
| RPG | 24,083.75 | 58,620.57 |
| Strategy | 12,209.59 | 39,031.61 |

These gaps warrant caution but do not isolate overfitting: the training rows are in-sample one-step predictions, while the evaluation rows are distant recursive forecasts under changing conditions. They must not be described as directly comparable train/test accuracy. Existing shallow trees, leaf limits, limited search and chronological evaluation constrain complexity, but cannot guarantee generalisation.

The provisional policy's historical annual rankings match recorded rankings at two origins; two later origins each have two categories displaced by one rank. Those are development diagnostics of a policy chosen after inspecting related outcomes, not an independent estimate of ranking accuracy.

## Remaining limits

- **No untouched final performance estimate.** The four origins have informed model, feature and policy choices. Nested parameter selection prevents direct future-target use but cannot reverse this development reuse.
- **Retrospective metadata and cohort.** Later labels/eligibility define the historical targets; this is not a point-in-time reconstruction of the Steam catalog. Coverage diagnostics based on recorded spans remain interpretation fields, not supplied future features.
- **V1 target history ends September 2025.** Supplemental histories covered only part of the cohort and remained separate from v1 targets. These projections cannot claim complete current/future Steam coverage or predict unknown future hit releases reliably.
- **V1 uncertainty is exploratory.** Only one origin had enough earlier calibration errors for the band check, and MMO coverage was 50%. The bands were not reliable 90% intervals; no ranking probabilities or annual confidence bounds were claimed. This is separate from the current v2 historical-error sensitivity analysis.
- **False alarms and false negatives require an event task.** Outlier-screening flags are not ground-truth anomaly labels. No confusion matrix, precision/recall or threshold is presented as evaluating the continuous forecasts.

## Verification and reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe src\audit_project.py
.\.venv\Scripts\python.exe src\project_2027.py
.\.venv\Scripts\python.exe src\forecast_uncertainty.py
```

The recorded audit run reproduced 1,080 baseline rows, 2,700
statistical-comparison rows, 3,240 combined model rows, 2,160 feature-experiment
rows and 324 tuned predictions plus selected tuning candidates. These sets
overlap by design and should not be summed as independent forecasts. This
documentation update did not repeat that real-data replay.

At that stage, all source files and 68 code cells in 15 notebooks parsed, with
no saved error outputs. Notebook kernels and visual rendering were not rerun
end-to-end in this audit; numerical model pipelines were replayed directly. The
original pilot cache was also reparsed and reconciled. No new source retrieval
or cosmetic change was performed.

Evidence files:

- reports/full_audit/evidence.json
- reports/full_audit/training_forecast_gaps.csv
- reports/full_audit/annual_ranking_diagnostics.csv
- tests/test_audit_contracts.py

The recommendation at that stage was to clarify the forecast scope and
evaluation boundary before further presentation work or parameter searches.
The separately versioned v2 workflow followed; the original v1 results remain
historical evidence.
