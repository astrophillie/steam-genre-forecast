# Source data

Keep the frozen source files unchanged. The active dataset is `fixed_sources_v2`, defined in [the scope config](../../config/project_scope.json). Its five history sources and metadata fingerprint are recorded in [the frozen registry](../../reports/fixed_sources_v2/source_registry.json). The original inputs below also support the historical v1 workflow.

| File | What it contains |
|---|---|
| `fronkon_metadata/games.parquet` | Steam game metadata from FronkonGames on Hugging Face |
| `monthly_players/steamcharts.csv` | Historical monthly players from Victor Laputsky / lunthu on Kaggle |
| `monthly_players/steam_monthly_players.zip` | Original downloaded player-data archive |
| `sources.json` | Original v1 source URLs, versions, download date, reported licenses, sizes, SHA-256 hashes |
| `fixed_sources_v2/aanomali_monthly.csv` | Frozen multiplayer research history; source 2 in the v2 registry |
| `fixed_sources_v2/liu_monthly.csv` | Frozen giveaway research history; source 3 in the v2 registry |

Source pages:

- https://huggingface.co/datasets/FronkonGames/steam-games-dataset
- https://www.kaggle.com/datasets/lunthu/steam-monthly-average-players

The original Connor Wynkoop dataset was last updated in 2021. The selected
lunthu dataset was updated on 30 October 2025 and includes Steam app IDs,
which makes it useful for joins. This original input ends in September 2025;
the active v2 workflow combines the frozen sources and uses a January 2026
cutoff for a provisional forecast of the fixed 519-game cohort.

The author reports missing low-audience games and some major games because
of collection limitations. This is a sample of Steam, not the complete market.
Partial-month labels must be inspected before modelling.

The metadata repository reports MIT; the player source reports CC0.
Downloaded `dataset_info.json` files retain those source declarations.
Metadata labels are a present-day snapshot, not historical genre assignments.

Reviews are intentionally deferred to the later extension in the guide.
Reviews have not been collected. A separate bounded direct SteamCharts pilot is cached under steamcharts_pilot/; its response pages and manifest remain separate from the two original model-input sources.

The remaining v2 history inputs are `database/steam.sqlite`,
`data/processed/supplemental_monthly_validated.parquet` and the existing
`reports/steamcharts_pilot/20261025T085419Z_52879d/monthly_players.csv`, all
relative to the repository root. The pilot's monthly table contributes to v2;
its cached response pages remain separate. No new collection is authorised by
the source registry.

## Reuse and publication

Reported repository or dataset licences are provenance evidence, not proof that
every upstream observation can be redistributed. The frozen registry records
unresolved terms for the Liu and Aakash inputs and an upstream-data caveat for
Aanomali. Preserve those notes. Raw inputs and local databases remain excluded
from Git; do not package the raw-data archive as a public source release while
these terms remain unresolved.

Source terms were reviewed on 27 October 2026:

- [Aanomali's pinned MIT licence](https://github.com/aanomali/steam-multiplayer-forecasting/blob/582dca92f49d4cb6ff57392a92750ae6024d3ffb/LICENSE) covers software and associated documentation. A separate grant for upstream monthly observations has not been verified.
- [Liu's pinned README](https://github.com/liunicholas/egs-steam-research-paper/blob/c920ccf9be4550b9e849423f9f137fbf62d26d8c/README.md) identifies SteamCharts scraping. No licence was identified in the pinned root directory or README; redistribution permission remains unverified.
- [Aakash's frozen release](https://github.com/Aakash-1107/Game-Market-Intelligence/releases/tag/data-2026-10-07) attributes monthly observations to SteamCharts. Its Mendeley CC BY and Kaggle CC0 declarations concern different inputs and do not establish terms for these monthly records.
- The reviewed SteamCharts [About](https://steamcharts.com/about) and [Privacy](https://steamcharts.com/privacy) pages did not establish an explicit redistribution grant. This limited review does not prove that reuse is prohibited or replace a complete rights review.

These findings clarify the existing caveats; they do not amend the frozen
registry or establish permission to publish raw observations.

The A002 checks reproduced the cohort and category totals from the frozen local
inputs and verified their fingerprints. They do not independently validate the
original collection process. See [the portfolio summary](../../reports/PORTFOLIO_SUMMARY.md#data-verification-and-remaining-limits)
for the distinction between verified data consistency and remaining research
limitations.
