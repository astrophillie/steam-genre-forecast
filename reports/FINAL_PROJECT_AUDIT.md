# Final project audit — 27 October 2026

**Result: the inspected consistency checks passed, with documented analytical limits. No independent predictive validation is claimed.**

The review covers the original historical workflow, fixed-source v2 integration, model comparison, diagnostics, frozen 2027 projection and current portfolio narrative. No additional sources were collected, and the model routes and forecast values remain unchanged.

The initial scoped verification passed 263 non-website research tests in a fresh
Windows/Python 3.14.3 environment and again against an exported staged source
snapshot. It checked saved data and forecast consistency without retraining the
real-data models. Details are recorded in the follow-up section below.

## Earlier recorded verification

The table below records the earlier project audit, including its real-data
replay and 267-test run. That count included four historical HTML-builder tests
excluded from the later 263-test research run. These are different verification
scopes, not competing counts from the same run.

| Area | Evidence recorded in the earlier audit |
|---|---|
| Regression suite | 267 tests passed after the core audit fixes. |
| Core code review | Agent-assisted review examined 26 analytical source modules and 24 test modules; the additional presentation module received a bounded follow-up review. |
| Architecture | Agent-assisted review checked source/version boundaries and diagnostic-evidence protections. This was an implementation review, not external certification or independent validation of predictive accuracy. |
| Original historical workflow | Full replay reproduced baseline, statistical, boosting, feature and tuned forecasts and confirmed v1 checksums. |
| Sources | All five registered history-source hashes and the metadata hash match. |
| Relational archive | SQLite integrity and foreign-key checks pass; 632,576 unique app/month records cover 7,051 apps. |
| Modelling cohort | 519 eligible games, complete February 2021–January 2026 history; all 300 category/month totals independently recompute in SQL. |
| Exports | All three v2 Parquet datasets reconcile in full with SQLite. |
| Evaluation | Future-actual isolation, common-target inventory, chronological slicing, recursive features and finite metric guards were checked. |
| Forecast | The frozen policy, six final CSVs and nine diagnostic CSVs pass their fingerprints; the 230 monthly rows reproduce byte-for-byte. |
| Notebook consistency | All 96 code cells in 20 notebooks parse, with no saved error outputs. Notebook 20 was executed in order with nine code cells and retains both figures. |
| Presentation | PNG/SVG figures were inspected, including units, labels, observed/forecast separation and uncertainty wording. Figure builders reject missing fingerprints. |
| Documentation | The links available at that audit stage resolved, and displayed annual figures matched the frozen CSV. Interview and checkpoint handoff documents have since become local-only. |

Preserved machine-readable snapshots: [earlier project audit](final_audit/evidence.json)
and [historical v1 replay](full_audit/evidence.json). The first snapshot retains
the documentation-link claims made before interview and handoff notes became
local-only; it is not a current public-link inventory. These JSON records have
not been rewritten to describe later documentation changes.

## Findings repaired

| Finding | Repair and check |
|---|---|
| Extreme finite errors could overflow v2 RMSE or fold averages. | Scaled calculations handle unsafe ranges, and unrepresentable relative metrics fail explicitly. Regression cases cover errors around 1e154, 1e200 and two-fold 1e308 values. Current Steam-scale reports reproduce unchanged. |
| Incomplete offline pilot snapshots could attempt a robots request. | Missing cached access evidence now stops before session creation. A mocked-session regression verifies that offline recovery cannot initiate the request. |
| Diagnostic CSVs were outside the final forecast's evidence fingerprint set. | Nine diagnostic files are now pinned in the forecast manifest. Projection and diagnostic replay require the complete matching inventory before accepting or overwriting evidence. Edited and empty inventories are tested. The original frozen policy and six forecast CSVs retain their bytes. |
| A chart could consume a CSV omitted from an edited fingerprint inventory. | The builder requires all three consumed forecast CSV fingerprints before reading; the missing-inventory smoke check passed. |
| Baseline markers overlapped some chart labels. | Value labels now sit beyond both the policy bar and reference marker; the exported image was inspected. |

## Interpretation review

The final forecast uses a fixed January 2026 cutoff, with 23 steps through December 2027. Leads 12–23 supply the twelve target-year months. Annual summaries average monthly concurrent activity and preserve the original unit. The baseline repeats January 2026 activity, so percentage differences between approaches are separate from annual growth rates.

Last value remains selected for Action/MMO, seasonal naive for Indie, and damped seasonal smoothing for RPG/Strategy. Gradient boosting remains part of the comparison rather than the final policy. In-sample one-step fit errors and recursive long-horizon forecast errors were reviewed as different tasks; their gap alone is insufficient evidence of overfitting. Custom neural-network losses and gradients are inapplicable because no such model is implemented.

Residual size, bias and exact baseline contribution accounting were reviewed without deleting large observations as presumed corruption. Classification false-positive/negative rates are inapplicable without a separately defined event and threshold. Source-label overlap is retained, and category totals are not presented as a distinct market-wide audience.

## Remaining limits

- The cohort and later-snapshot labels were selected retrospectively. Complete histories favour consistently observed games and exclude future releases and much of Steam.
- The two development cutoffs share most target months. There is no untouched holdout or broad independent validation, and the policy remains provisional.
- Historical-error sensitivity ranges have no validated predictive coverage. No annual confidence interval or ranking probability is claimed.
- Historical notebooks were syntax/output-checked rather than all rerun inside a native Jupyter kernel. The final notebook's cells ran sequentially with the project interpreter; the pinned environment lacks nbformat/nbclient.
- Raw files and databases remain local with redistribution caveats. Many project files remain uncommitted; no commit, push or publication was performed during this audit.

The remaining limits describe the supported project scope and do not establish a defect in the current saved projections.

## Final presentation artifacts

- [Final forecast notebook](../notebooks/20_fixed_cohort_2027_forecast.ipynb)
- [Annual policy/reference figure · PNG](../outputs/final_figures/annual_comparison.png) · [SVG](../outputs/final_figures/annual_comparison.svg)
- [Forecast paths and historical-error ranges · PNG](../outputs/final_figures/forecast_paths.png) · [SVG](../outputs/final_figures/forecast_paths.svg)
- [Portfolio summary](PORTFOLIO_SUMMARY.md)

No confirmed implementation defect remains from the checks described here.
The limitations above still bound the interpretation of the saved projections.

## A001–A004 follow-up — 27 October 2026

The setup guide now separates current v2 reproduction from historical v1
restoration, lists the frozen prerequisites and explains the unresolved raw-data
distribution boundary. The README presents current v2 results and links to the
historical notebooks without repeating checkpoint handoffs.
All 20 notebooks name the project kernel, with registration and checkout-move
instructions in the setup guide. DuckDB 1.5.0 is installed and opens the frozen
4,994-row supplemental monthly table read-only.

A new Windows/Python 3.14.3 environment installed successfully from the existing
lock and audit requirements; `pip check` and all 263 non-website research tests
passed. An export of the staged source snapshot also passed those 263 tests in
that environment. Its 22 checked input/evaluation/policy/output/diagnostic
fingerprints match. Git attributes preserve the exact bytes of pinned config
and CSV/JSON evidence rather than normalising their line endings. Root transfer
ZIPs remain local and ignored; research source and evidence are staged for
review, with no commit or push.

All 141 protected local data/evidence/figure files retained their SHA-256 hashes
during this work. Real-data models were not retrained. The two unexecuted
Notebook 04 cells embed historical HTML views and remain outside the technical
workstream. Full real-data notebook replay, other operating systems, historical
label reconstruction, independent future evaluation and raw redistribution
rights remain unverified; dependency installation and synthetic tests do not
resolve those scientific or access limits.

## Staged verification and sensitivity supplement — 28 October 2026

The final pre-analysis staged snapshot passed 263 research tests, 127 public
local-link checks and 28 input/output fingerprint checks. The separate
[cohort coverage and historical concentration analysis](fixed_cohort_sensitivity/README.md)
then added descriptive archive-coverage and shared-leader-exclusion scenarios.
Its baseline reconciles with the frozen category inputs; independent SQL
recomputed all five coverage rows and 900 scenario rows. Annual means,
endpoint changes and ranks were checked separately.

The expanded staged source export passed 276 research tests, including 13 new
sensitivity tests; four historical HTML-builder tests remain outside this
scope. All 141 original protected data/evidence/figure files retained their
SHA-256 hashes. This work did not refit research models, alter the 519-game
cohort or revise any frozen 2027 projection. The scenarios are retrospective
historical composition diagnostics, not independent forecast validation or
causal counterfactuals. No commit, push, history rewrite or publication occurred.
