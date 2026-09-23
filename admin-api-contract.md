# Frontend API Integration Contract

Backend: FastAPI. Base URL prefix for all endpoints below: `/api/v1`.
No auth headers required.

Notation used in this file: **R** = required (non-nullable, must be sent) ·
**O** = optional/nullable (may be omitted or sent as `null` where the type allows it).

## 1. Global conventions

### 1.1 Success envelope

Every JSON response with a body uses this envelope (single object and list alike):

```json
{
  "success": true,
  "data": {},
  "pagination": null
}
```

- `success`: always `true`.
- `data`: the resource object, or an array for list endpoints.
- `pagination`: object on **list** endpoints only, otherwise `null`.

List endpoints return:

```json
{
  "success": true,
  "data": [],
  "pagination": {
    "total_count": 25,
    "page_size": 10,
    "current_page": 2,
    "total_pages": 3
  }
}
```

### 1.2 Pagination query params (all list endpoints)

| Param | Required | Type | Default | Constraints |
|---|---|---|---|---|
| `page` | O | integer | `1` | `>= 1` |
| `limit` | O | integer | `100` | `1–1000` |

### 1.3 Error format (no envelope)

All `4xx` errors return `{ "detail": "<message>" }` with no `success`/`data` wrapper.
`422` validation errors use the default FastAPI body (not `{detail}`).

### 1.4 Wire formats

| Type | Wire format |
|---|---|
| UUID | string, e.g. `"3fa85f64-5717-4562-b3fc-2c963f66afa6"` |
| datetime | ISO-8601 string, e.g. `"2026-09-22T10:00:00Z"` |
| Decimal (power_factor, cri, dimensions) | **JSON string** on responses, e.g. `"0.95"`. On requests both `"0.95"` and `0.95` are accepted |
| bool query params | `true` / `false` |
| `delete` endpoints | `204` with empty body |

### 1.5 Strict bodies

Almost all JSON request bodies reject unknown fields (`422`) and strip surrounding
whitespace on strings. `min_length=1` strings must be non-empty after stripping.

### 1.6 PATCH semantics (all modules)

- PATCH bodies are partial: send only fields to change. Omitted = unchanged.
- Sending an empty PATCH body (no fields) → `400 { "detail": "No fields provided to update" }`.
- Sending an explicitly unknown resource id → `404`.
- **Variant PATCH quirk (important):** `UpdateVariantRequest.ies_file_id` is
  **required** (non-nullable UUID, no default), so every `PATCH` variant call must
  include the current (or a new) `ies_file_id`, even when only changing e.g. `power`.

---

## 2. Assets (`/api/v1/assets`)

Files (IES files, 3D models, images) must be uploaded here first; the returned
asset `id` is then referenced by fixture/variant payloads.

### 2.1 `POST /assets/` — upload a file → `201`

- Body: `multipart/form-data` with a single file field named **`file`**.
- Response data: `AssetResponse`.

### 2.2 `GET /assets/` — list assets → `200` (paginated)

| Query | Required | Type | Notes |
|---|---|---|---|
| `page`, `limit` | O | — | §1.2 |
| `name` | O | string | partial, case-insensitive match on `original_filename` |

- Response data: `AssetResponse[]`.

### 2.3 `GET /assets/{asset_id}` — download file bytes → `200`

- Does **not** use the JSON envelope: returns the raw file stream with
  `Content-Disposition: attachment` and the stored `Content-Type` / `Content-Length`.
- Unknown id (or missing file on disk) → `404 { "detail": "Asset not found" }`.

### 2.4 `AssetResponse`

| Field | Nullability | Type | Notes |
|---|---|---|---|
| `id` | R | UUID | use as `*_file_id` reference |
| `relative_path` | R | string | internal storage path, do not build URLs from it |
| `original_filename` | R | string | |
| `mime_type` | R | string | |
| `size_bytes` | R | integer | `>= 0` |
| `created_at` | R | datetime | |

---

## 3. Standards (`/api/v1/standards`)

Standard `id` is a client-supplied deterministic string key
(e.g. `"en12464_1_v2019_6_1_1"`), **not** a UUID.

### 3.1 `POST /standards/` — create → `201`

- Body: `CreateStandardRequest`. Unknown fields are **ignored** (not rejected).
- Idempotent: same `id` + identical content returns `201` with the existing record.
- Same `id` with different content → `409`.
- `qdrant_point_id` already taken by another id → `409`.

### 3.2 `POST /standards/bulk` — async bulk ingest → `202`

- Body: `CreateManyStandardsRequest` (`items`: 1+ `CreateStandardRequest`).
- Duplicate ids or duplicate derived point ids **within the batch** → `400`.
- Returns immediately: `{ status: "accepted", item_count }`. Records are created in the background.

### 3.3 `GET /standards/` — list → `200` (paginated)

| Query | Required | Type | Notes |
|---|---|---|---|
| `page`, `limit` | O | — | §1.2 |
| `standard_code` | O | string | exact match |
| `version_year` | O | string | exact match |
| `is_latest` | O | bool | exact match |
| `category_table_number` | O | string | exact match |
| `activity` | O | string | partial, case-insensitive |
| `keywords` | O | string[] (repeat param) | partial, case-insensitive matches against searchable text fields |
| `match_mode` | O | `"any"` \| `"all"` | default `"any"`; `"all"` = every keyword must match |

- Response data: `StandardResponse[]`.

### 3.4 `GET /standards/categories` — distinct categories → `200` (no pagination)

| Query | Required | Type |
|---|---|---|
| `standard_code`, `version_year`, `is_latest` | O | same semantics as §3.3 |

- Response data: `StandardCategoryResponse[]`, `pagination: null`.

### 3.5 `GET /standards/{standard_id}` → `200` · unknown id → `404 { "detail": "Standard not found" }`

### 3.6 `PATCH /standards/{standard_id}` → `200`

- Body: `UpdateStandardRequest` (all fields optional). Identity fields
  (`id`, `category_table_number`, `ref_number`, point id) are immutable and rejected if sent.
- Empty body → `400`. Unknown id → `404`.

### 3.7 `DELETE /standards/{standard_id}` → `204` · unknown id → `404`

### 3.8 Standard DTOs

`CreateStandardRequest` (create body):

| Field | Nullability | Type | Notes |
|---|---|---|---|
| `_id` | R | string, non-empty | natural key; `id` alias also accepted |
| `standard_metadata` | R | object | § below |
| `hierarchy` | R | object | § below |
| `activity` | R | string, non-empty | |
| `parameters` | R | object | § below (all inner fields optional) |
| `specific_requirements` | O | string \| null | |
| `searchable_text` | R | string, non-empty | keyword-searchable text |

`StandardMetadataDTO` (all R): `standard_code` string non-empty ·
`version_year` string non-empty · `is_latest` bool.

`StandardHierarchyDTO` (all R): `category_table_number` string non-empty ·
`category_title` string non-empty · `ref_number` string non-empty · `page` integer `>= 1`.

`StandardParametersDTO` (all O, nullable, all numbers `>= 0` unless noted):
`em_r_lx`, `em_u_lx`, `uo` (also `<= 1`), `ra` (also `<= 100`),
`ugr_rugl`, `ez_lx`, `em_wall_lx`, `em_ceiling_lx` — float | null.

`UpdateStandardRequest` (all O / nullable): `standard_metadata` (`{ is_latest?: bool }` only) ·
`hierarchy` (`{ category_title?: string non-empty, page?: int >= 1 }` only) ·
`activity?` string non-empty · `parameters?` full `StandardParametersDTO`
(replaces the whole parameters object) · `specific_requirements?` string | null ·
`searchable_text?` string non-empty.

`StandardResponse` (all R except `specific_requirements`):
`id` string · `qdrant_point_id` string (server-computed, never sent) ·
`standard_metadata`, `hierarchy`, `activity` string, `parameters` object ·
`specific_requirements` string | null · `searchable_text` string ·
`content_hash` string · `created_at`, `updated_at` datetime.

`StandardCategoryResponse` (all R): `standard_metadata` object ·
`category_table_number` string · `category_title` string.

`CreateManyStandardsRequest`: `items`: `CreateStandardRequest[]`, 1+ required.

`CreateManyStandardsAcceptedResponse`: `status`: `"accepted"` (always) ·
`item_count`: integer `>= 1`.

---

## 4. Fixtures (`/api/v1/fixtures`)

Enums: `FixtureApplication`: `"interior"` | `"industrial"` ·
`ElectricalProtection`: `"OV"` | `"OC"` | `"OT"`.

### 4.1 `POST /fixtures/` — create fixture → `201`

- Body: `CreateFixtureRequest`. Response data: `FixtureSummaryResponse` (no variants nested).

### 4.2 `GET /fixtures/` — list fixtures → `200` (paginated)

| Query | Required | Type | Notes |
|---|---|---|---|
| `page`, `limit` | O | — | §1.2 |
| `q` | O | string | partial, case-insensitive match on `manufacturer_name` and fixture `name` |
| `application` | O | `"interior"` \| `"industrial"` | fixture must include this application |
| `is_main_solution` | O | bool | exact match |

- Response data: `FixtureSummaryResponse[]` (no variants nested).

### 4.3 `GET /fixtures/{fixture_id}` — fixture with variants → `200` · unknown id → `404 { "detail": "Fixture not found" }`

- Response data: `FixtureResponse` (= summary + `variants: VariantResponse[]`).

### 4.4 `PATCH /fixtures/{fixture_id}` → `200`

- Body: `UpdateFixtureRequest` (all fields optional). Empty body → `400`.
- Unknown id → `404`. Invalid applications array → `422`.

### 4.5 `DELETE /fixtures/{fixture_id}` → `204` (cascades to its variants and images) · unknown id → `404`

### 4.6 Fixture DTOs

`CreateFixtureRequest`:

| Field | Nullability | Type | Notes |
|---|---|---|---|
| `manufacturer_name` | R | string, non-empty | |
| `name` | R | string, non-empty | |
| `is_main_solution` | O | bool | default `false` |
| `applications` | R | enum[] | 1–2 items, values unique, each `"interior"` \| `"industrial"` |

`UpdateFixtureRequest` — same fields, all O/nullable (`applications`: 1–2 unique items when sent).

`FixtureSummaryResponse` (all R): `id` UUID · `manufacturer_name` string ·
`name` string · `is_main_solution` bool · `applications` string[]
(values `"interior"`/`"industrial"`) · `created_at`, `updated_at` datetime.

`FixtureResponse`: everything in `FixtureSummaryResponse` plus
`variants`: `VariantResponse[]` (R, may be empty).

---

## 5. Variants (`/api/v1/fixtures/...`)

### 5.1 `GET /fixtures/variants/` — list all variants → `200` (paginated)

| Query | Required | Type | Notes |
|---|---|---|---|
| `page`, `limit` | O | — | §1.2 |
| `q` | O | string | partial, case-insensitive match on **variant `name` only** |
| `application` | O | `"interior"` \| `"industrial"` | filters by the **parent fixture's** applications |
| `is_main_solution` | O | bool | filters by the **parent fixture's** flag |
| `fixture_id` | O | UUID | restrict to one fixture; unknown id → `404 { "detail": "Fixture not found" }` |

- Response data: `VariantDetailResponse[]`.

### 5.2 `GET /fixtures/{fixture_id}/variants/` — list one fixture's variants → `200` (paginated)

- Same queries as §5.1 except `fixture_id` comes from the path (no `fixture_id` query param).
- Unknown path `fixture_id` → `404`.

### 5.3 `POST /fixtures/{fixture_id}/variants/` — create variant → `201`

- Body: `CreateVariantRequest`. Response data: `VariantResponse`.
- Unknown fixture → `404`. Referenced asset ids must exist (missing `ies_file_id` asset → `404 { "detail": "IES file not found" }`, missing 3D asset → `404 { "detail": "Asset not found" }`).
- Duplicate variant `name` within the same fixture → `409 { "detail": "Variant name already exists on this fixture" }`.

### 5.4 `GET /fixtures/{fixture_id}/variants/{variant_id}` → `200`

- Response data: `VariantDetailResponse` (variant + parent `fixture` summary).
- Wrong parent (`variant` belongs to another fixture) or unknown ids → `404 { "detail": "Variant not found" }` (unknown fixture → `404 { "detail": "Fixture not found" }`).

### 5.5 `PATCH /fixtures/{fixture_id}/variants/{variant_id}` → `200`

- Body: `UpdateVariantRequest`. Response data: `VariantResponse`.
- Must always include `ies_file_id` (§1.6). Empty body (besides `ies_file_id`… in practice include a real change) risks `400`.
- Duplicate `name` on the fixture → `409`. Unknown ids → `404`.

### 5.6 `DELETE /fixtures/{fixture_id}/variants/{variant_id}` → `204` (cascades to its images) · unknown/mismatched ids → `404`

### 5.7 Variant DTOs

`CreateVariantRequest`:

| Field | Nullability | Type | Notes |
|---|---|---|---|
| `name` | R | string, non-empty | unique per fixture |
| `power` | R | integer `>= 0` | |
| `chip` | R | string, non-empty | |
| `driver` | R | string, non-empty | |
| `power_factor` | R | Decimal `0–1` | send `"0.95"` or `0.95` |
| `cri` | R | Decimal `>= 0` | |
| `efficacy` | R | integer `>= 0` | |
| `mechanical_protections` | O | string[] | default `[]`, values unique |
| `electrical_protections` | O | enum[] | default `[]`, values unique, each `"OV"` \| `"OC"` \| `"OT"` |
| `dimension_length` | O | Decimal `>= 0` \| null | default `null` |
| `dimension_width` | O | Decimal `>= 0` \| null | default `null` |
| `dimension_depth` | O | Decimal `>= 0` \| null | default `null` |
| `dimension_radius` | O | Decimal `>= 0` \| null | default `null` |
| `model_3d_file_id` | O | UUID \| null | asset id of 3D model, default `null` |
| `ies_file_id` | R | UUID | asset id of IES file |

`UpdateVariantRequest` — same fields but all optional **except `ies_file_id`, which stays required** (see §1.6). Nullable numeric/enum-list fields accept `null` to… note: sending `dimension_*` / list fields as explicit `null` writes `null`/default handling server-side; omit a field to leave it unchanged.

`VariantResponse`:

| Field | Nullability | Type |
|---|---|---|
| `id`, `fixture_id` | R | UUID |
| `name`, `chip`, `driver` | R | string |
| `power`, `efficacy` | R | integer |
| `power_factor`, `cri` | R | Decimal (response: string, e.g. `"0.95"`) |
| `mechanical_protections` | R | string[] |
| `electrical_protections` | R | string[] (`"OV"`/`"OC"`/`"OT"`) |
| `dimension_length`, `dimension_width`, `dimension_depth`, `dimension_radius` | R-nullable | Decimal-string \| null |
| `model_3d_file_id` | R-nullable | UUID \| null |
| `model_3d_file` | R-nullable | `AssetResponse` \| null |
| `ies_file_id` | R | UUID |
| `ies_file` | R | `AssetResponse` |
| `images` | R | `VariantImageResponse[]` (may be empty) |
| `created_at`, `updated_at` | R | datetime |

`VariantDetailResponse`: everything in `VariantResponse` plus `fixture`: `FixtureSummaryResponse` (R).

---

## 6. Variant images (`/api/v1/fixtures/{fixture_id}/variants/{variant_id}/images/...`)

### 6.1 `POST /…/images/` — attach image → `201`

- Body: `CreateVariantImageRequest`: `image_file_id`: UUID (R, must be an existing asset).
- Response data: `VariantImageResponse`.
- Unknown fixture/variant (or mismatched parent) → `404`. Missing asset → `404 { "detail": "Asset not found" }`.
- Same image already attached to the variant → `409 { "detail": "Image already attached to this variant" }`.

### 6.2 `DELETE /…/images/{image_id}` → `204`

- `image_id` is the **variant-image record id** (`VariantImageResponse.id`), not the asset id.
- Unknown/mismatched ids → `404` (`"Image not found"` when the record is missing or belongs to another variant).

### 6.3 `VariantImageResponse` (all R)

`id` UUID (record id — use for DELETE) · `variant_id` UUID ·
`image_file_id` UUID (asset id) · `image_file` `AssetResponse`.

---

## 7. Status / error catalog

| Endpoint | Success | Errors (`{detail}`) |
|---|---|---|
| `POST /assets/` | `201` envelope | `422` validation |
| `GET /assets/` | `200` envelope+pagination | — |
| `GET /assets/{id}` | `200` file bytes (no envelope) | `404 "Asset not found"` |
| `POST /standards/` | `201` envelope | `409` already-exists / point-id-taken; `422` |
| `POST /standards/bulk` | `202` envelope (`status`/`item_count`) | `400` duplicate ids/point-ids in batch; `422` |
| `GET /standards/` | `200` envelope+pagination | — |
| `GET /standards/categories` | `200` envelope, no pagination | — |
| `GET /standards/{id}` | `200` envelope | `404 "Standard not found"` |
| `PATCH /standards/{id}` | `200` envelope | `400` empty body; `404`; `422` |
| `DELETE /standards/{id}` | `204` empty | `404` |
| `POST /fixtures/` | `201` envelope | `422` |
| `GET /fixtures/` | `200` envelope+pagination | — |
| `GET /fixtures/variants/` | `200` envelope+pagination | `404` unknown `fixture_id` query |
| `GET /fixtures/{id}` | `200` envelope | `404 "Fixture not found"` |
| `PATCH /fixtures/{id}` | `200` envelope | `400` empty body / invalid asset ref; `404`; `422` |
| `DELETE /fixtures/{id}` | `204` empty | `404` |
| `GET /fixtures/{id}/variants/` | `200` envelope+pagination | `404` unknown fixture |
| `POST /fixtures/{id}/variants/` | `201` envelope | `404` fixture/asset/IES missing; `409` duplicate variant name; `422` |
| `GET /…/variants/{vid}` | `200` envelope | `404 "Variant not found"` / `"Fixture not found"` |
| `PATCH /…/variants/{vid}` | `200` envelope | `400` empty body; `404`; `409` duplicate name; `422` |
| `DELETE /…/variants/{vid}` | `204` empty | `404` |
| `POST /…/images/` | `201` envelope | `404` fixture/variant/asset missing; `409` already attached; `422` |
| `DELETE /…/images/{iid}` | `204` empty | `404 "Image not found"` (or parent) |
