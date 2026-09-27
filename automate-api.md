# Automate API — Frontend Integration Contract

Single endpoint that designs a lighting layout for a room: pick the best
fixture grids for a lighting-standard target using real catalog variants.

- **Method/URL:** `POST {LUXSCALE_BASE_URL}/automate`
- **Body:** plain JSON (`Content-Type: application/json`). No multipart, no file uploads, no auth headers.
- **Synchronous, slow:** a typical run takes **10–90 s** (full-physics verification). Set the HTTP timeout to **≥ 180 s** and show a progress state. Do not retry on timeout without asking the user (runs are expensive).
- **Response:** `200` with the JSON below. Errors use `{ "error": { "code", "message", "details", "requestId" } }` (§6). Every response carries an `X-Request-ID` header — include it in bug reports.

Notation: **R** = required · **O** = optional (omit to use the default).

---

## 1. Request

```json
{
  "polygon": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}, {"x": 0, "y": 5}],
  "ceilingHeight": 4.0,
  "mountingHeight": 3.0,
  "activityId": "en12464_1_v2019_6_2_3",
  "variantIds": null,
  "workPlaneHeight": 0.0,
  "floorZone": 0.5,
  "wallZone": null,
  "wallReflectance": null,
  "floorReflectance": null,
  "ceilingReflectance": null,
  "maxOverdesign": null,
  "search": {
    "spacingX": null,
    "spacingY": null,
    "offsetFractions": [0.5],
    "rotations": [0.0],
    "maxFixtures": 64,
    "minWallClearance": 0.0,
    "shrMax": 1.5
  },
  "topK": 5,
  "stageB": 12
}
```

| Field | Req | Type | Default | Rules |
|---|---|---|---|---|
| `polygon` | R | `{x, y}[]`, 3+ points | — | Room footprint, meters. Closing vertex optional. Must have non-zero area |
| `ceilingHeight` | R | float `> 0` | — | Ceiling plane height, meters |
| `mountingHeight` | R | float `> 0` | — | Fixture hang height, meters. Must be `≤ ceilingHeight` |
| `activityId` | R | non-empty string | — | Standard id key, e.g. `"en12464_1_v2019_6_2_3"`. Use `GET {ADMIN}/api/v1/standards/?limit=50` to browse (`id`, `activity`, `parameters.em_r_lx`, `parameters.uo`) |
| `variantIds` | O | UUID string[] \| null | `null` = auto-list | Explicit variants, or omit/`[]` for all main-solution variants of the derived application |
| `workPlaneHeight` | O | float `≥ 0` | `0.0` | Calculation-surface height, meters (0 = floor) |
| `floorZone` | O | float ≥ 0 \| null | `0.5` | Floor boundary inset, meters |
| `wallZone` | O | float ≥ 0 \| null | auto (15% rule) | Wall boundary inset, meters |
| `wallReflectance` | O | 0–1 \| null | `0.5` | `null` = server default |
| `floorReflectance` | O | 0–1 \| null | `0.2` | `null` = server default |
| `ceilingReflectance` | O | 0–1 \| null | `0.7` | `null` = server default |
| `maxOverdesign` | O | float ≥ 0 \| null | `0.3` | Allowed average excess over target (0.3 = +30%). `null` = standard default |
| `search.spacingX/Y` | O | `{min, max, step}` \| null | `null` = auto | Explicit grid-spacing range (all `> 0`, `min ≤ max`), or omit for server auto (from room size + mounting height, capped at 2000 combos → else 422) |
| `search.offsetFractions` | O | float[0–1], 1+ | `[0.5]` | Symmetric grid offset as fraction of spacing |
| `search.rotations` | O | float[], 1+ | `[0.0, 90.0]` | In-room housing rotations, degrees |
| `search.maxFixtures` | O | int ≥ 1 | `64` | Layouts with more fixtures are skipped |
| `search.minWallClearance` | O | float ≥ 0 | `0.0` | Min grid offset from walls, meters |
| `search.shrMax` | O | float > 0 | `1.5` | Max spacing ÷ mounting-height ratio |
| `topK` | O | int 1–20 | `5` | Max solutions returned (compliant first, then flagged — never more than this total) |
| `stageB` | O | int 1–50 | `12` | Full-physics verifications **per variant**. Higher = more thorough, slower |

Send `null` (or omit the key) for every "empty = default" field. Never send `0`/`""` to mean "default" — those fail validation. `variantIds: []` is treated like `null` (auto-list).

### Derived rules (server-side, not inputs)

- **Application:** `mountingHeight ≤ 3.0 → "interior"`, else `"industrial"`. Decides which catalog variants are eligible. Echoed back as `application`.
- **Target:** average + uniformity come from the standard (`parameters.em_r_lx`, fallback `em_u_lx`; `parameters.uo`). Compliant window = `[avg, avg × (1 + maxOverdesign)]` plus uniformity.
- **One grid per variant:** each variant appears at most once across `solutions` + `closestMiss` (its best grid). `solutions` holds at most `topK` entries: compliant first, then flagged over-cap picks filling leftover slots. `closestMiss` is the nearest miss from a variant shown nowhere else, or `null`.

---

## 2. Response (`200`)

```json
{
  "target": {"avgLux": 300.0, "uniformity": 0.4, "maxOverdesign": 0.3},
  "application": "interior",
  "solutions": [ { "solution…" } ],
  "evaluatedA": 144,
  "evaluatedB": 38,
  "pruned": {"shr": 0, "clearance": 0, "outside": 0, "count": 0, "lumen": 124},
  "closestMiss": { "solution…" },
  "appliedSpacingX": {"min": 1.5, "max": 4.5, "step": 0.5},
  "appliedSpacingY": {"min": 1.5, "max": 4.5, "step": 0.5},
  "floorPatches": [ { "patch…" } ],
  "floorMeta": {"spacing": 0.53, "nx": 8.0, "ny": 8.0, "border": 0.5, "workPlaneHeight": 0.0}
}
```

| Field | Type | Meaning |
|---|---|---|
| `target` | object | Resolved target actually used (`avgLux`, `uniformity`, `maxOverdesign` incl. override) |
| `application` | `"interior"` \| `"industrial"` | Application actually used — if this surprises you, your mounting height crossed the 3.0 m rule |
| `solutions` | solution[] | Compliant first (`recommended: true`), then flagged over-cap (`recommended: false`). Max `topK` total. May be empty |
| `evaluatedA` | int | Candidates ranked with cheap direct-only light |
| `evaluatedB` | int | Candidates re-verified with full interreflection physics |
| `pruned` | `{shr, clearance, outside, count, lumen}` | Layouts discarded before physics + reason (`lumen` = hopelessly dim/absurd per the lumen pre-gate) |
| `closestMiss` | solution \| null | Nearest non-compliant layout from an otherwise-unshown variant, with `missReason`. `null` when nothing informative remains |
| `appliedSpacingX/Y` | `{min, max, step}` | Spacing range actually searched (explicit or auto) |
| `floorPatches` | patch[] | Shared EN 12464 floor grid (same for every solution — see §4) |
| `floorMeta` | object | Grid shape: `spacing`, `nx`, `ny`, `dx`, `dy`, bounds, `border`, `workPlaneHeight` |

### Solution object

| Field | Type | Meaning |
|---|---|---|
| `variantId` | UUID string | Catalog variant — fetch details via admin API (see §5) |
| `fixtureCount` | int | Number of physical fixtures |
| `placements` | placement[] | `{id, x, y, z, rotation, tiltAngle}` — world frame: X/Y plan meters, **Z = mounting height** (always filled), `tiltAngle` degrees from straight-down (`0` = downlight). No `iesRef`/`aimDirection` keys exist |
| `fixtures` | fixture[] | Engine-resolved geometry for drawing: `{id, position{x,y,z}, rotation, tiltAngle, length, width, height, corners[4]{x,y,z}, elements[]{x,y,z}}`. Position z is the luminous-plane height (mounting − height/2). No `aimDirection` key. `len == fixtureCount` |
| `grid` | object | Winning layout hint (`spacingX/Y`, `offsetX/Y`, `rotation`) |
| `average` / `minimum` / `maximum` | float (lx) | Maintained illuminance stats over the evaluation grid |
| `uniformity` | float | `minimum / average` |
| `overdesign` | float | `average / target − 1` (0.719 = +71.9%) |
| `powerW` / `powerDensity` | float \| null | Total watts / W per m² (from variant `power`, never the IES file) |
| `missReason` | `"under_target"` \| `"over_cap"` \| `"uniformity"` \| null | First failing check; `null` on recommended solutions |
| `recommended` | bool | `true` = passed all checks. `false` = shown for reference: flagged over-cap picks inside `solutions`, and every `closestMiss` entry (which additionally carries its `missReason`) |
| `totalFloor` | `{values: float[], metadata: {}}` \| null | Maintained total floor lux, 1:1 with `floorPatches` (§4). Solutions only; `null` on the miss |

---

## 3. Status lines the UI should handle

| Situation | What you get | Show |
|---|---|---|
| Solutions found | `solutions: [...]` (all or leading entries `recommended: true`) | Best = first `recommended` entry; render the rest as alternatives |
| Only flagged entries | all `recommended: false` with amber "not recommended — over cap" | "No compliant layout — closest options exceed the cap by X%. Lower the target, allow more overdesign, or add dimmer variants." |
| Empty + miss | `solutions: []`, `closestMiss` with `missReason` | Reason-specific hint: `under_target` → "needs more/dimmer-distributed light"; `over_cap` → "smallest layouts already too bright — dimmer variants needed"; `uniformity` → "average OK but patchy — denser grid needed" |
| Empty, no miss | `solutions: [], closestMiss: null` | "Nothing viable — widen spacing steps or relax constraints" |

---

## 4. Drawing (plan view + heatmap)

- **Fixtures:** per selected solution use `fixtures[].corners` (world-space opening rectangles, top view = ignore z) + `placements` dots (x/y). `position.z` is the hang height if you do 3D.
- **Heatmap:** `solution.totalFloor.values[i]` ↔ top-level `floorPatches[i]` (strict order). Draw one rect per patch at `center` with size `size` (square) — works for any polygon including L-shapes (no patches exist outside the inset boundary, so no masking needed). Color-scale over `[solution.minimum, solution.maximum]`; extents/scale bar from `floorMeta` (`nx`, `ny`, `spacing`, `border`) + room `polygon` (not echoed — you sent it).
- **Payload size guide:** ≈ patches × solutions floats (a 5×5 m room ≈ 64 patches; 3 solutions ≈ 33 KB total). `topK` bounds it.

---

## 5. Variant details (admin API — for the card header)

Solutions carry only `variantId`. Enrich cards via `GET {ADMIN}/api/v1/fixtures/variants/?application={interior|industrial}&is_main_solution=true&limit=100` (paginated; match `id`). Useful fields: `name`, `power` (W), `efficacy` (lm/W, lumens = `power × efficacy`), `chip`, `driver`, `power_factor`, `cri`, protections, `dimension_*` (**millimeters** — divide by 1000 for meters), `ies_file.original_filename`, nested `fixture` (`manufacturer_name`, `name`, `is_main_solution`, `applications`). Note: there is no `GET /variants/{id}` — list + match by id.

---

## 6. Errors

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Request validation failed.",
  "details": [{"field": "mountingHeight", "issue": "..."}], "requestId": "…" } }
```

| HTTP | `code` | When |
|---|---|---|
| `422` | `VALIDATION_ERROR` | Bad input (`details[].field` uses dotted paths, e.g. `search.spacingX.min`) |
| `400` | `GEOMETRY_INVALID` / `NO_FIXTURES` / `IES_PARSE` / … | Degenerate polygon, grid misses room, unusable photometry |
| `502` | `PROVIDER_ERROR` | Admin backend unreachable, unknown `activityId`/`variantIds`, or no main-solution variants for the application |
| `500` | `INTERNAL_ERROR` | Anything else — report with `X-Request-ID` |

Interactive docs (when the server runs): `{LUXSCALE}/docs`. Test page (manual only, not an API): repo file `demo-automate.html` — open directly in a browser.
