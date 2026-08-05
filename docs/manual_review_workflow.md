# MANUAL_REVIEW workflow — what you can do

Layout-stage `MANUAL_REVIEW` means the pipeline generated a Lakeview widget but fidelity is incomplete (e.g. Measure Names approximated as a table, map → table fallback). It is **advisory**, not a hard deploy gate, unless your process treats it as one.

## Status values on conversion cards

| Status | Meaning |
|---|---|
| `SUCCESS` | Generated widget accepted as faithful enough |
| `MANUAL_REVIEW` | Generated; needs human decision |
| `UNSUPPORTED` | No Lakeview widget generated |
| `ACCEPTED` | Human acknowledged the gap (or applied an override/patch) |

## What you can do in the product

### Layout stage (`VisualConversionDetail`)

- View conversion cards + Manual Review Queue (reason, suggested fix, impact)
- Filter / search by status
- **Accept** a review card → status `ACCEPTED` (persisted on the job)
- **Override widget type** (table → bar / pie / heatmap / …) and rewrite Lakeview JSON
- **Patch encodings** (pick x / y / color / angle fields from the dataset)
- **Export** layout review queue CSV (`layout-review-cards`)
- Copy / download full `.lvdash.json` (also via `GET /api/v1/migrations/{id}/json`)
- Re-run the whole pipeline (Execute)

### Calc stage (`CalcLogicConversionDetail`)

- View formula review queue
- Export: Business Mapping, Transpiled SQL, Compatibility Specs
- Export: **Manual Review Items** CSV (`manual-review-items`)

## API allow-list

| Method | Path | Purpose |
|---|---|---|
| GET | `/migrations/{id}/exports/layout-review-cards` | Layout conversion_cards CSV |
| GET | `/migrations/{id}/exports/manual-review-items` | Calc unsupported CSV |
| GET | `/migrations/{id}/layout-review/cards/{card_id}/fields` | Field options + override types |
| POST | `/migrations/{id}/layout-review/cards/{card_id}/accept` | Accept card |
| POST | `/migrations/{id}/layout-review/cards/{card_id}/override` | Body: `{ widget_type, x_field?, y_field?, color_field? }` |
| POST | `/migrations/{id}/layout-review/cards/{card_id}/encodings` | Body: `{ encodings: { x, y, color, … } }` |
| GET | `/migrations/{id}/json` | Download current Lakeview JSON (includes overrides) |

Accept / override / encoding patches update:

1. `StageResult` artifacts (`conversion_cards`, metrics, `review_actions`)
2. `generated_code` / `lakeview_json_str`
3. On-disk `job.output_lvdash_path` (so deploy publishes the edited dashboard)

## Typical Insurance actions

| Sheet | Why MANUAL_REVIEW | Recommended action |
|---|---|---|
| Region - Claim Ratio | Measure Names → table | Accept table, or override to bar with one measure |
| Total Claims and Payout | Map → table | Accept table, or rebuild as bar/pie in Databricks |
| Others | SUCCESS | None |

## Out of scope

Full Tableau re-authoring, inventing geo maps, or fabricating dashboard actions. Fix those in Databricks AI/BI after download/deploy.
