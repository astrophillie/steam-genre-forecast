# Cohort coverage and historical concentration sensitivity

Analysis date: 28 October 2026. This is a descriptive supplement to the frozen
519-game forecast. It uses February 2021–January 2026 observations from the
existing archive. No models were fitted and no 2027 forecast was changed.

## Cohort coverage

The complete-history rule retains a small proportion of eligible labelled
archive games, but a much larger share of the activity actually observed at the
January 2026 cutoff. These are archive comparisons, not Steam-market coverage.

| Category | Cohort / eligible archive games | Cohort game share | Observed / missing games at cutoff | Cohort share of observed cutoff activity |
|---|---:|---:|---:|---:|
| Action | 308 / 2,945 | 10.46% | 403 / 2,542 | 84.40% |
| Indie | 260 / 3,616 | 7.19% | 347 / 3,269 | 79.99% |
| Massively Multiplayer | 71 / 290 | 24.48% | 81 / 209 | 75.70% |
| RPG | 144 / 1,368 | 10.53% | 187 / 1,181 | 80.00% |
| Strategy | 174 / 1,710 | 10.18% | 214 / 1,496 | 95.82% |

Eligible games meet the existing metadata-screening rule and have the relevant
label. A missing cutoff record remains unknown: it is neither zero activity nor
evidence that the game had stopped operating. Activity shares divide the cohort
total by the total among eligible category games with an observed cutoff record.
The large missing counts prevent interpreting those shares as complete archive
activity coverage. Category memberships overlap, so these rows cannot be added
as distinct games or audiences. Exact counts and numerators are in
[archive_coverage.csv](archive_coverage.csv).

## Shared leader exclusions

Leaders are selected once from the original January 2026 cohort activity, with
ascending AppID breaking ties. The union of the top game in each category has
four games: Counter-Strike 2, Rust, PUBG: BATTLEGROUNDS and Dota 2. Rust leads
both Indie and RPG under the frozen retrospective labels. The union of the top
five games per category has 17 distinct games. Each union is removed from every
category for every month; leaders are not reselected after removal.

| Category | Cutoff activity retained after four-game exclusion | After 17-game exclusion | Observed 2025 rank: full / four-game / 17-game |
|---|---:|---:|---:|
| Action | 39.61% | 29.52% | 1 / 1 / 1 |
| Indie | 86.17% | 60.88% | 5 / 3 / 2 |
| Massively Multiplayer | 48.61% | 30.43% | 4 / 5 / 5 |
| RPG | 87.61% | 53.66% | 3 / 2 / 3 |
| Strategy | 53.60% | 39.93% | 2 / 4 / 4 |

The retained-activity columns use January 2026 totals; the ranks use the mean of
the twelve observed 2025 months. They are different comparisons. Action remains
largest in both exclusions, while the lower-category ordering changes. This
describes historical category composition, not the robustness of the 2027 ranks.

Action's February 2021–January 2026 endpoint change is +6.30% for the full cohort,
−22.35% without the four-game union and −31.50% without the 17-game union.
Strategy changes from +18.78% to +4.69% and −9.11%, respectively. These changes
span the stated endpoints and are not annualised growth rates. Selecting games
at the final endpoint mechanically affects this comparison; it is a descriptive
stress test, not evidence of what would have happened if those games did not exist.

The leader membership table (`excluded_leaders.csv`; withheld from the public snapshot) records all 25 category/game
selections. [Monthly scenarios](scenario_monthly.csv) retain the complete
900-row grid; [scenario summaries](scenario_summary.csv) contain annual means,
endpoint changes and ranks. Ties share the minimum rank. An intentionally empty
category is marked explicitly and left unranked; percentages with a zero
reference remain unavailable.

## Interpretation and limits

The cohort is selective and historical activity depends heavily on a few games.
These diagnostics quantify two limitations; they do not remove survivor/coverage
bias, reconstruct historical labels, supply independent forecast outcomes or
calibrate uncertainty. They use no activity after January 2026. Excluded games
remain in the original database, cohort and forecast inputs. No app-level
forecast is invented to subtract from the aggregate model projections.

## Reproduce and verify

Run from the repository root with the existing project environment:

```powershell
.\.venv\Scripts\python.exe -B src\cohort_sensitivity.py
.\.venv\Scripts\python.exe -B -m pytest tests/test_cohort_sensitivity.py -q -p no:cacheprovider
```

The analysis reads the SQLite database in read-only mode, verifies its frozen
lineage and writes only this separate report folder's CSVs and manifest. The
[source script](../../src/cohort_sensitivity.py) contains the SQL and calculations;
the [manifest](manifest.json) records input paths, input/output hashes and rules.
The full-cohort scenario reconciles with all 300 frozen category/month totals.
Independent SQL checks also matched all five coverage rows and all 900 scenario
rows; annual means, changes and ranks reconciled separately. All 141 original
protected data/evidence/figure files retained their hashes. Thirteen targeted
tests passed, covering shared exclusions, ties, missing/zero observations,
complete calendars, exhausted categories and overlapping measurements.
The expanded staged source export passed all 276 non-website research tests.
