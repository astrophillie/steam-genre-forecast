# Public snapshot exclusions and notebook copies

This curated release contains 247 files: 245 selected project files, including the public notebook copies, plus this notice and the README website screenshot. The original research checkout and its local history remain separate. File counts refer to the release contents, not Git internals or temporary validation files.

## Files withheld from this snapshot

The following 13 observation-level CSVs and historical setup report are absent from the public copy. Their original local files are preserved; none was deleted or rewritten to prepare this release.

- `reports/steamcharts_pilot/20261025T085419Z_52879d/monthly_players.csv`
- `reports/fixed_cohort_diagnostics/case_app_contributions.csv`
- `reports/fixed_cohort_diagnostics/top_case_changes.csv`
- `reports/fixed_cohort_diagnostics/top_seasonal_changes.csv`
- `reports/baseline_peak_leaders.csv`
- `reports/enrichment/supplemental_overlap.csv`
- `reports/exploration_bridge_apps.csv`
- `reports/exploration_top_games.csv`
- `reports/fixed_cohort_sensitivity/excluded_leaders.csv`
- `reports/refresh_gate/overlap.csv`
- `reports/refresh_readiness/catalog.csv`
- `reports/refresh_readiness/collection_queue.csv`
- `reports/steamcharts_pilot/20261025T085419Z_52879d/overlap_comparison.csv`
- `reports/setup_check.json`

Other exclusions inherited from the curated scope include raw input datasets, processed input tables, databases, the virtual environment, personal learning materials, editor/workspace files and unapproved interactive prototypes. Source notes, frozen manifests and selected evidence are retained even when they record a path to a withheld local input.

## Saved notebook outputs omitted from public copies

Cell positions below are one-based positions in the selected source snapshot. Each listed cell retains its original source, execution count, order and metadata; only its saved `outputs` list was cleared in the public copy. Both the HTML and plain-text representations were removed together. Merely hiding an output would not remove it from a downloadable notebook.

| Notebook | Cells | Cell ID where present | Omitted saved output |
|---|---|---|---|
| `notebooks/01_understanding_the_data.ipynb` | 7 and 17 | Not assigned in the selected source cells | Monthly activity sample and unmatched-app activity examples |
| `notebooks/02_data_preparation.ipynb` | 8 | Not assigned in the selected source cell | Flagged-app activity examples |
| `notebooks/04_exploratory_analysis.ipynb` | 10 | Not assigned in the selected source cell | Named leading-game activity table |
| `notebooks/19_fixed_cohort_error_review.ipynb` | 16 | `checkpoint19-10` | Per-game reference and observed activity contributions |

These are five saved-output bundles across four notebook copies. No cell was executed. No models were fitted, forecasts recalculated or figures regenerated. Explanatory text, scientific conclusions, code and execution counts remain intact. All other saved output bundles, scientific images, tables and legends remain unchanged.

Notebook 04's source is the previously curated Git-index version. Its two unrelated local working-copy additions are not part of this release.

## Public-only link adjustments

Three links to withheld CSVs were replaced with a filename and a withheld-file notice. The surrounding scientific explanation is retained:

- `notebooks/07_refresh_readiness.ipynb`, cell 6, ID `refresh-readiness-5`: historical coverage catalog.
- `notebooks/07_refresh_readiness.ipynb`, cell 9, ID `queue-checkpoint`: historical collection queue.
- `reports/fixed_cohort_sensitivity/README.md`: leader membership table, formerly linked at line 59 in the selected source.

These are public-copy link adjustments, not changes to the original local files or to their scientific claims.

## Notebook hash comparison

The original hashes identify the selected source notebooks before public-copy changes. Public hashes identify the resulting files here. Notebook 07 changes only the two links above; the other four changes are the selected saved-output omissions. Other notebooks are unchanged from their selected sources.

| Notebook | Selected source SHA-256 | Public copy SHA-256 |
|---|---|---|
| `notebooks/01_understanding_the_data.ipynb` | `8ba3d7c70fc94004cb742e02d6e9237f02227fc555bf26b382b990ca6f2e7ab9` | `7b73b2281e17132812c7f5577a6d63eb5437608fdb78957200ec75ecdc30949f` |
| `notebooks/02_data_preparation.ipynb` | `396da70f1051474851c66cba38de1cf005ed5df2e0a74fd71f84dd43f4270864` | `11b511f4e28112f5be5708ac611c347e70be1a46b1c350a3b2c1fb961fdc8d0a` |
| `notebooks/04_exploratory_analysis.ipynb` | `de348742310d4731cdee3d2bd9a5fb5ff3952069eafb0c835caac3c813972203` | `644d18be87a91c07cf1295a688039bebebaf5937c65eb9e8c91df2e8111f6742` |
| `notebooks/07_refresh_readiness.ipynb` | `6fb2ad99f480149d13b82f6bfd902bd80905e0eb04c4bf6371f6a84373b68e86` | `123c63eedc8425a33d6e365dedba4cc8949175d05c5b9faa41f4c32a721d0a11` |
| `notebooks/19_fixed_cohort_error_review.ipynb` | `8304aeee751634c0a6294950dfe6dacfc0b1dca89c8fd33c56d31c21f8ec636a` | `ac2ffff4ba2150ec3d6aa64ffff9b9c9062a3e0872a5c8728fccdd3a959975fc` |

## Reproduction and frozen-evidence limits

A fresh public checkout is not a complete research-replay package. The missing raw inputs, processed tables, databases, pilot history and diagnostic exports are deliberate exclusions. Review [START_HERE.md](START_HERE.md) and [the source notes](data/raw/README.md) before attempting any research commands. Commands that rebuild research may write artifacts and require the original frozen local prerequisites; the website preview does neither.

The included Python source, notebook code and provenance records still name withheld files when those files are genuine inputs or outputs of the original workflow. For example, Notebook 06, source integration and the refresh gate require the withheld pilot monthly table. These paths are historical and computational provenance, not promises that every prerequisite is included here.

Frozen research outputs, policy, scientific figures and manifests remain unchanged. In particular, the forecast manifest retains the original diagnostic output hashes even though selected diagnostic CSVs are withheld. Do not rewrite those hashes or remove source records to make the public copy appear complete. Full reproduction or checks that require missing files must use the preserved local evidence and its recorded fingerprints.

## Remaining publication and reuse uncertainty

This snapshot retains category-level historical observations, forecasts, derived summaries, game names and metadata, cohort decisions, concentration shares and scenario results. Aggregate totals, shares or differences between scenarios may allow information about individual games to be inferred. Omitting selected CSVs and notebook outputs is not a guarantee that individual values cannot be reconstructed.

Neither these exclusions nor the project's non-commercial purpose establish permission to redistribute the remaining observations, metadata or derived results.

No project-wide reuse license has been selected or supplied. Third-party font notices remain in place; no blanket license is granted for datasets or other third-party material.
