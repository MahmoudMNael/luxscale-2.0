# LuxScale 2.0 — `/calculate` API Integration & Visualization Guide

This specification defines the complete integration contract for the `POST /calculate` endpoint in **LuxScale 2.0**. It covers HTTP transport protocols, all request and response schemas, field-level constraints and defaults, multi-variant studies, compliance evaluation, and the exact mathematical formulas required to render 2D plan heatmaps, luminaire orientations, and wall elevation diagrams.

---

## Table of Contents
1. [Endpoint Overview & Protocols](#1-endpoint-overview--protocols)
2. [Coordinate System & Units](#2-coordinate-system--units)
3. [Request Payloads & Formats](#3-request-payloads--formats)
   - [Mode A: Multipart Form-Data (Photometry File Upload)](#mode-a-multipart-form-data-photometry-file-upload)
   - [Mode B: Application/JSON (Catalog Variant Study)](#mode-b-applicationjson-catalog-variant-study)
4. [Request Schema Reference (`CalculateRequest`)](#4-request-schema-reference-calculaterequest)
   - [Room Geometry & Environmental Reflectances](#room-geometry--environmental-reflectances)
   - [Grid Placement Modes (Mutually Exclusive)](#grid-placement-modes-mutually-exclusive)
   - [Free Placement Mode (`fixtures`)](#free-placement-mode-fixtures)
   - [Photometry & Multi-Variant Studies](#photometry--multi-variant-studies)
   - [Compliance Targets](#compliance-targets)
5. [Response Schema Reference (`CalculateResponse`)](#5-response-schema-reference-calculateresponse)
   - [Evaluation Metrics (`EvaluationDto`)](#evaluation-metrics-evaluationdto)
   - [Compliance Results (`ComplianceResultDto`)](#compliance-results-complianceresultdto)
   - [Placed Fixtures (`FixtureDto`)](#placed-fixtures-fixturedto)
   - [Patches & Matrix Representations](#patches--matrix-representations)
   - [Multi-Variant Study Array (`results`)](#multi-variant-study-array-results)
6. [Error Handling & Validation Codes](#6-error-handling--validation-codes)
7. [Frontend Visualization & Rendering Mathematical Guide](#7-frontend-visualization--rendering-mathematical-guide)
   - [Coordinate Normalization & Canvas Viewport Mapping](#coordinate-normalization--canvas-viewport-mapping)
   - [Rendering Floor Heatmaps & Patch Cells](#rendering-floor-heatmaps--patch-cells)
   - [Heatmap Color Interpolation](#heatmap-color-interpolation)
   - [Rendering Fixtures, Orientations & Aim Vectors](#rendering-fixtures-orientations--aim-vectors)
   - [Wall Elevation Unrolling](#wall-elevation-unrolling)
   - [Matrix Layering & Direct/Indirect Isolation](#matrix-layering--directindirect-isolation)
   - [Interactive Free Drag-and-Drop & Snapping Math](#interactive-free-drag-and-drop--snapping-math)

---

## 1. Endpoint Overview & Protocols

- **URL:** `http://<host>:8000/calculate`
- **Method:** `POST`
- **Supported Content-Types:**
  1. `multipart/form-data`: Used when uploading raw `.ies` photometry files from the client.
  2. `application/json`: Used when referencing catalog luminaire IDs (`variantIds`) or cached provider keys.
- **Swagger Documentation:** Available live at `/docs`.

---

## 2. Coordinate System & Units

LuxScale uses a **Right-Handed 3D Cartesian Coordinate System**:
- **Units:** All spatial distances are in **meters ($m$)**. Angles are in **degrees ($^\circ$)**. Light output is in **lux ($lx = lm/m^2$)**.
- **$X$-Axis:** Horizontal floor plane dimension (East-West).
- **$Y$-Axis:** Vertical floor plane dimension (North-South).
- **$Z$-Axis:** Vertical room height elevation ($Z=0$ is the finished floor level, $Z=H$ is the ceiling).
- **Polygons:** Defined as a continuous list of $(X, Y)$ vertices ordered counter-clockwise (CCW). The closing edge back to $(X_0, Y_0)$ is inferred automatically if omitted.

---

## 3. Request Payloads & Formats

### Mode A: Multipart Form-Data (Photometry File Upload)
When client uploads a local `.ies` file:
- **`Content-Type` Header:** `multipart/form-data`
- **Form Fields:**
  - `payload` *(string, required)*: A stringified JSON object matching the `CalculateRequest` schema.
  - `iesFile` *(file/blob, required)*: Standard ASCII text file conforming to **IES LM-63** (`TILT=NONE`).
  - `iesFiles` *(file array, optional)*: Additional IES files keyed by filename to match individual `fixtures[i].iesRef`.

#### Example `curl` Call:
```bash
curl -X POST "http://localhost:8000/calculate" \
  -F 'payload={"polygon":[{"x":0,"y":0},{"x":8,"y":0},{"x":8,"y":6},{"x":0,"y":6}],"ceilingHeight":3.0,"mountingHeight":3.0,"workPlaneHeight":0.8,"grid":{"count":{"countX":3,"countY":2,"offsetFraction":0.5}}}' \
  -F 'iesFile=@sample.ies'
```

### Mode B: Application/JSON (Catalog Variant Study & Heterogeneous Layouts)
When calculating catalog variants or cached fixture profiles:
- **`Content-Type` Header:** `application/json`
- **Body:** JSON object directly matching the `CalculateRequest` schema with `variantId` specified at the root (for grid layouts or shared defaults) and/or per-fixture `variantId` in `fixtures`.

#### Example `curl` Call (Default Variant with Grid):
```bash
curl -X POST "http://localhost:8000/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "polygon": [{"x":0,"y":0},{"x":8,"y":0},{"x":8,"y":6},{"x":0,"y":6}],
    "ceilingHeight": 3.0,
    "mountingHeight": 3.0,
    "workPlaneHeight": 0.8,
    "grid": {
      "count": { "countX": 3, "countY": 2, "offsetFraction": 0.5 }
    },
    "variantId": "var-panel-30w",
    "compliance": { "targetLux": 500, "targetUniformity": 0.6 }
  }'
```

#### Example `curl` Call (Heterogeneous Fixtures Layout):
```bash
curl -X POST "http://localhost:8000/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "polygon": [{"x":0,"y":0},{"x":8,"y":0},{"x":8,"y":6},{"x":0,"y":6}],
    "ceilingHeight": 3.0,
    "mountingHeight": 3.0,
    "workPlaneHeight": 0.8,
    "fixtures": [
      { "id": "F1", "x": 2.0, "y": 3.0, "variantId": "var-panel-30w" },
      { "id": "F2", "x": 6.0, "y": 3.0, "variantId": "var-spot-15w", "tiltAngle": 30.0 }
    ],
    "compliance": { "targetLux": 300, "targetUniformity": 0.4 }
  }'
```

---

## 4. Request Schema Reference (`CalculateRequest`)

### Room Geometry & Environmental Reflectances

| Field | Type | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `polygon` | `Array<{x: number, y: number}>` | **Required** | `min_length: 3` | Room perimeter vertices in meters. Must form a simple, non-self-intersecting polygon. |
| `ceilingHeight` | `number` | **Required** | `> 0` | Height of the suspended/finished ceiling plane in meters; walls extend to this height. |
| `mountingHeight` | `number` | **Required** | `> 0, <= ceilingHeight` | Z elevation of luminaire luminous openings in meters (must be $\le \text{ceilingHeight}$). |
| `workPlaneHeight` | `number` | `0.0` | `>= 0, < mountingHeight` | Calculation surface elevation in meters. Set to `0.0` for true floor; `0.75` or `0.85` for desk work planes (DIALux parity). |
| `floorZone` | `number \| null` | `0.5` | `>= 0` | Boundary margin inset for EN 12464 calculation grid on floor and ceiling (meters). Default `0.5m`. |
| `wallZone` | `number \| null` | `null` | `>= 0` | Boundary margin inset for wall calculation grids. When `null`, engine applies the standard 15% rule: $\min(0.15 \times \min(L, H), 0.5m)$. |
| `luminaireRotation` | `number` | `0.0` | `0.0` to `360.0` | Global in-room rotation angle (degrees) applied to all luminaires relative to $+X$ axis. |
| `wallReflectance` | `number \| null` | `0.5` | `0.0` to `1.0` | Wall reflectance coefficient ($\rho_w$). Standard office default: `0.5` (50%). |
| `floorReflectance` | `number \| null` | `0.2` | `0.0` to `1.0` | Floor reflectance coefficient ($\rho_f$). Standard office default: `0.2` (20%). |
| `ceilingReflectance` | `number \| null` | `0.7` | `0.0` to `1.0` | Ceiling reflectance coefficient ($\rho_c$). Standard office default: `0.7` (70%). |
| `maintenanceFactor` | `number \| null` | `0.8` | `> 0, <= 1.0` | Light Loss Factor ($MF$). Multiplied against all direct and inter-reflected illuminance. Standard clean interior default: `0.8`. |
| `bounces` | `number \| null` | `3` | `0` to `10` | Radiosity inter-reflection bounces. `0` = direct lighting only; `3` = full radiosity equilibrium. |
| `includeWallCeilingMatrices`| `boolean` | `true` | — | When `true`, returns individual wall and ceiling illuminance matrices. Set `false` for low-bandwidth scenarios. |

> **Important Rule:** Exactly one of `grid` or `fixtures` must be provided in every request. Supplying both or neither will result in a `422 Validation Error`.

---

### Grid Placement Modes (Mutually Exclusive)

The `grid` object allows 3 distinct layout paradigms:

#### 1. Count Grid Mode (`grid.count`)
Evenly distributes a discrete number of luminaires along X and Y axes within the room bounding box.
```json
"grid": {
  "count": {
    "countX": 3,
    "countY": 2,
    "offsetFraction": 0.5
  }
}
```
- **`countX`** *(integer, required, $\ge 1$)*: Number of luminaires along X axis.
- **`countY`** *(integer, required, $\ge 1$)*: Number of luminaires along Y axis.
- **`offsetFraction`** *(number, optional, $0.0$ to $1.0$, default `0.5`)*:
  - `0.5`: DIALux standard symmetric half-spacing. Wall distance equals half the fixture-to-fixture spacing ($d_{\text{wall}} = 0.5 \times S$).
  - **Formulas:**
    $$\text{Span}_x = X_{\max} - X_{\min}$$
    $$\text{Spacing } S_x = \frac{\text{Span}_x}{\text{countX} - 1 + 2 \times \text{offsetFraction}}$$
    $$\text{Offset } d_x = S_x \times \text{offsetFraction}$$
    $$\text{Positions along } X = [X_{\min} + d_x + i \times S_x \quad \text{for } i \in 0 \dots (\text{countX}-1)]$$

#### 2. Spacing Grid Mode (`grid.spacing`)
Specifies physical distances between fixtures, with optional automated centering.
```json
"grid": {
  "spacing": {
    "spacingX": 2.4,
    "spacingY": 2.5,
    "autoCenter": true,
    "offsetX": null,
    "offsetY": null
  }
}
```
- **`spacingX`** *(number, required, $> 0$)*: Desired distance along X axis in meters.
- **`spacingY`** *(number, required, $> 0$)*: Desired distance along Y axis in meters.
- **`autoCenter`** *(boolean, optional, default `true`)*:
  - When `true`: Computes fixture count $N = \max(1, \lfloor \text{Span} / \text{Spacing} \rfloor)$ and centers the grid within the room bounds with equal margin on both sides.
  - When `false`: Positions start at $(X_{\min} + \text{offsetX})$ and step by `spacingX` until $(X_{\max} - \text{offsetX})$.
- **`offsetX`** / **`offsetY`** *(number, optional, $\ge 0$)*: Boundary offset in meters when `autoCenter` is `false`.

#### 3. Axis Grid Mode (`grid.x` and `grid.y`)
Explicit step and asymmetric start/end offsets for DIALux XML export parity.
```json
"grid": {
  "x": { "spacing": 2.42, "offsetBeginning": 1.21, "offsetEnding": 1.0 },
  "y": { "spacing": 2.55, "offsetBeginning": 2.62, "offsetEnding": 1.0 }
}
```

---

### Free Placement Mode (`fixtures`)
When custom, irregular, or interactive drag-and-drop placement is active, omit `grid` and pass the `fixtures` array:

```json
"fixtures": [
  {
    "id": "F1",
    "x": 2.50,
    "y": 3.00,
    "z": 2.95,
    "rotation": 0.0,
    "tiltAngle": 15.0,
    "aimDirection": null,
    "iesRef": "accent-track.ies"
  }
]
```

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `id` | `string \| null` | `"F1"`, `"F2"`... | Identifier echoed in matrices and reports. |
| `x` | `number` | **Required** | Room X coordinate (m). |
| `y` | `number` | **Required** | Room Y coordinate (m). |
| `z` | `number \| null` | `mountingHeight` | Per-fixture mounting elevation override (m). Useful for staggered downlights or task lamps. |
| `rotation` | `number \| null` | `luminaireRotation` | Plan rotation in degrees ($0^\circ$ to $360^\circ$). |
| `tiltAngle` | `number \| null` | `0.0` | Tilt from straight down in degrees ($0^\circ$ = nadir downlight; $> 0^\circ$ = wall wash or accent). |
| `aimDirection`| `Vec3Dto \| null` | `null` | 3D unit aim vector `{"x": float, "y": float, "z": float}`. If omitted, engine calculates aim from `tiltAngle` and `rotation`. |
| `variantId` | `string \| null` | `null` | Catalog variant UUID assigned to this specific luminaire (enables heterogeneous layouts). |
| `iesRef` | `string \| null` | `null` | Photometry identifier matching an uploaded `iesFiles` filename or provider variant ID. |

---

### Photometry & Heterogeneous Layouts

The `/calculate` endpoint supports individual luminaire assignments across the same room:

1. **Root Default `variantId`:**
   ```json
   "variantId": "var-600x600-3000lm"
   ```
   Used as the default luminaire for `grid` layouts, or when individual fixtures in `fixtures` omit their own `variantId` or `iesRef`.

2. **Per-Fixture `variantId` / `iesRef` (Heterogeneous Rooms):**
   ```json
   "fixtures": [
     { "id": "F1", "x": 2.0, "y": 2.0, "variantId": "var-panel-30w" },
     { "id": "F2", "x": 6.0, "y": 2.0, "variantId": "var-downlight-15w", "tiltAngle": 25.0 },
     { "id": "F3", "x": 4.0, "y": 5.0, "iesRef": "accent-track.ies" }
   ]
   ```
   Each luminaire's photometrics, luminous dimensions (length, width, height), and rated wattage are retrieved and scaled individually. The engine simulates the combined interaction of all fixtures in the room.

3. **Total Power & Power Density:**
   The backend sums the rated wattage across all placed luminaires to return:
   - `powerW`: Total installed wattage ($W$).
   - `powerDensity`: Installed power density ($W/m^2$).

---

### Compliance Targets (`compliance`)

To evaluate EN 12464 lighting criteria:
```json
"compliance": {
  "activityId": "en12464_1_v2019_6_1_1",
  "targetLux": 500.0,
  "targetUniformity": 0.60,
  "maxOverdesign": 0.30
}
```
- **`activityId`** *(string, optional)*: Key looked up in standards catalog.
- **`targetLux`** *(number, optional, $> 0$)*: Maintained average illuminance ($E_m$, lux).
- **`targetUniformity`** *(number, optional, $0.0$ to $1.0$)*: Maintained uniformity ($U_0 = E_{\min} / E_{\text{avg}}$).
- **`maxOverdesign`** *(number, default `0.3`)*: Allowed ratio above target ($0.3 = +30\%$).

---

## 5. Response Schema Reference (`CalculateResponse`)

The root response returns the layout, direct/indirect flux distributions, patch geometry, and EN 12464 evaluation:

```typescript
interface CalculateResponse {
  fixtures: FixtureDto[];
  floorPatches: PatchDto[];
  wallPatches: Record<string, PatchDto[]>;
  ceilingPatches: PatchDto[];
  totalFloorIlluminance: MatrixDto;
  directFloorMatrices: Record<string, MatrixDto>;
  indirectFloorMatrices: Record<string, MatrixDto>;
  totalWallIlluminance: Record<string, MatrixDto>;
  directWallMatrices: Record<string, Record<string, MatrixDto>>;
  indirectWallMatrices: Record<string, Record<string, MatrixDto>>;
  totalCeilingIlluminance: MatrixDto | null;
  directCeilingMatrices: Record<string, MatrixDto>;
  indirectCeilingMatrices: Record<string, MatrixDto>;
  evaluation: EvaluationDto;
  wallEvaluations: Record<string, EvaluationDto>;
  ceilingEvaluation: EvaluationDto | null;
  compliance: ComplianceResultDto | null;
  powerW?: number | null;        // Total installed room power in Watts
  powerDensity?: number | null;  // Installed power density in W/m²
  results?: VariantResultDto[]; // Present during multi-variant study
  bounces: number;
  wallReflectance: number;
  floorReflectance: number;
  ceilingReflectance: number;
  ceilingHeight: number;
  mountingHeight: number;
}
```

### Evaluation Metrics (`EvaluationDto`)
Contains EN 12464 summary figures for the floor working plane:
- **`average`** *(float)*: Maintained average illuminance $E_{\text{avg}}$ in lux.
- **`minimum`** *(float)*: Minimum illuminance $E_{\min}$ across all valid working-plane sample points.
- **`maximum`** *(float)*: Maximum illuminance $E_{\max}$ across all valid working-plane sample points.
- **`uniformity`** *(float)*: Overall uniformity ratio $U_0 = E_{\min} / E_{\text{avg}}$ (e.g. `0.765`).
- **`minPoint`** / **`maxPoint`** *(`{x, y, z}`)*: 3D coordinates where $E_{\min}$ and $E_{\max}$ occur.
- **`nx`**, **`ny`** *(integer)*: EN 12464 grid density cells along X and Y.
- **`spacingX`**, **`spacingY`** *(float)*: Grid cell step size in meters (e.g. `0.551m`).

### Compliance Results (`ComplianceResultDto`)
- **`compliant`** *(boolean)*: `true` if $E_{\text{avg}} \ge \text{targetLux}$ AND $U_0 \ge \text{targetUniformity}$ AND $\text{overdesign} \le \text{maxOverdesign}$.
- **`targetLux`** *(float)*: The applied target maintained lux.
- **`targetUniformity`** *(float)*: The applied target uniformity ratio.
- **`luxGap`** *(float)*: $E_{\text{avg}} - \text{targetLux}$ ($> 0$ means target met).
- **`uniformityGap`** *(float)*: $U_0 - \text{targetUniformity}$ ($> 0$ means target met).
- **`overdesign`** *(float)*: Excess ratio $(E_{\text{avg}} / \text{targetLux}) - 1$.

### Placed Fixtures (`FixtureDto`)
```typescript
interface FixtureDto {
  id: string;               // e.g. "F1"
  position: { x: number; y: number; z: number };
  aimDirection: { x: number; y: number; z: number };
  rotation: number;         // degrees (0..360)
  length: number;           // Luminous opening C0 dimension (meters)
  width: number;            // Luminous opening C90 dimension (meters)
  height: number;           // Luminous box vertical height (meters)
  corners: Vec3Dto[];       // 4 world-space bounding corners (CCW order)
  elements: Vec3Dto[];      // Radiosity discretization sample points
  variantId?: string | null;// Catalog variant UUID if assigned
  iesRef?: string | null;   // Photometry reference key / IES filename
}
```

### Patches & Matrix Representations
- **`PatchDto`**: Defines an illuminance surface sensor:
  ```json
  {
    "id": "floor-0",
    "center": { "x": 1.25, "y": 0.85, "z": 0.80 },
    "normal": { "x": 0.0, "y": 0.0, "z": 1.0 },
    "size": 0.551,
    "area": 0.303
  }
  ```
- **`MatrixDto`**:
  ```json
  {
    "values": [314.5, 320.1, 350.8, ...],
    "metadata": { "kind": "total-floor", "patches": 56 }
  }
  ```
  > **Crucial 1-to-1 Indexing:** Array index `i` of `totalFloorIlluminance.values[i]` corresponds strictly to `floorPatches[i]`.

### Multi-Variant Study Array (`results`)
When `variantIds` was passed in the request, `response.results` contains one `VariantResultDto` per variant:
```typescript
interface VariantResultDto {
  variantId: string;
  evaluation: EvaluationDto;
  compliance: ComplianceResultDto | null;
  powerW: number | null;
  powerDensity: number | null; // Watts per square meter (W/m²)
  totalFloorIlluminance: MatrixDto;
  fixtures: FixtureDto[];
}
```

---

## 6. Error Handling & Validation Codes

All errors return JSON with HTTP status 400, 422, or 500 in this schema:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      { "field": "grid.count.countX", "issue": "Field required" }
    ],
    "requestId": "954b7d25-97ca-4e0e-bd93-794e9cb1c31f"
  }
}
```

| HTTP Status | Code | Cause | Frontend Action |
| :--- | :--- | :--- | :--- |
| **422** | `VALIDATION_ERROR` | Missing required fields, negative values, or invalid grid mode. | Inspect `details[i].field` and highlight the corresponding input. |
| **400** | `IES_PARSE` | IES file corrupt or declares `TILT` other than `TILT=NONE`. | Alert user to upload standard `TILT=NONE` IES LM-63 file. |
| **400** | `GEOMETRY_INVALID` | Polygon has $< 3$ points, collinear vertices, or zero area. | Alert user to adjust room polygon vertices. |
| **400** | `NO_FIXTURES` | Defined grid/offsets place all fixtures outside room boundaries. | Adjust spacing, offsets, or room vertices. |
| **400** | `IES_ENCODING` | IES file is binary instead of UTF-8 text. | Prompt user to upload text format IES file. |

---

## 7. Frontend Visualization & Rendering Mathematical Guide

### Coordinate Normalization & Canvas Viewport Mapping

To render the 2D floor plan onto a target canvas or SVG viewport with width $W_v$ and height $H_v$ while preserving the room's true aspect ratio and padding:

1. **Calculate Polygon Bounding Box:**
   $$X_{\min} = \min_{i} x_i, \quad X_{\max} = \max_{i} x_i, \quad W_{\text{box}} = \max(0.01, X_{\max} - X_{\min})$$
   $$Y_{\min} = \min_{i} y_i, \quad Y_{\max} = \max_{i} y_i, \quad H_{\text{box}} = \max(0.01, Y_{\max} - Y_{\min})$$

2. **Calculate Scale Factor with Margin $M$ (e.g. 30px):**
   $$S = \min\left(\frac{W_v - 2M}{W_{\text{box}}}, \frac{H_v - 2M}{H_{\text{box}}}\right)$$

3. **Compute Centering Offsets:**
   $$O_x = \frac{W_v - W_{\text{box}} \cdot S}{2} - X_{\min} \cdot S$$
   $$O_y = \frac{H_v - H_{\text{box}} \cdot S}{2} + Y_{\max} \cdot S$$

4. **World to Screen Coordinate Transformation:**
   For any world point $(x, y)$:
   $$X_s = x \cdot S + O_x$$
   $$Y_s = O_y - y \cdot S \quad \text{(inverts Y for standard screen coordinates where top-left is 0,0)}$$

---

### Rendering Floor Heatmaps & Patch Cells

Each point in `response.floorPatches[i]` represents an EN 12464 measurement cell with center $(x, y)$, width $d = \text{size}$, and lux value $E = \text{totalFloorIlluminance.values}[i]$.

1. **Compute Cell Top-Left and Dimensions in Screen Pixels:**
   $$\text{Left} = (x - d/2) \cdot S + O_x$$
   $$\text{Top} = O_y - (y + d/2) \cdot S$$
   $$\text{Pixel Width} = \max(2, d \cdot S)$$
   $$\text{Pixel Height} = \max(2, d \cdot S)$$

2. **Render Cell:**
   - Map lux $E$ to a color hex string via the interpolation function below.
   - Draw filled rectangle at $(\text{Left}, \text{Top}, \text{Pixel Width}, \text{Pixel Height})$.

---

### Heatmap Color Interpolation

Normalize lux value $E$ between $E_{\min}$ and $E_{\max}$:
$$t = \text{clamp}\left(\frac{E - E_{\min}}{E_{\max} - E_{\min}}, 0.0, 1.0\right)$$

#### Continuous Multi-Stop Gradient (Navy $\to$ Blue $\to$ Amber $\to$ White):
```javascript
function luxColor(t) {
  // t is clamped between 0.0 and 1.0
  const stops = [
    { t: 0.00, r: 11,  g: 28,  b: 51  }, // Deep Navy (#0b1c33)
    { t: 0.33, r: 31,  g: 111, b: 235 }, // Royal Blue (#1f6feb)
    { t: 0.66, r: 240, g: 162, b: 2   }, // Amber Gold (#f0a202)
    { t: 1.00, r: 255, g: 247, b: 204 }, // Soft White (#fff7cc)
  ];
  let i = 0;
  while (i < stops.length - 1 && stops[i + 1].t < t) i++;
  const s0 = stops[i], s1 = stops[i + 1];
  const factor = (t - s0.t) / (s1.t - s0.t);
  const r = Math.round(s0.r + factor * (s1.r - s0.r));
  const g = Math.round(s0.g + factor * (s1.g - s0.g));
  const b = Math.round(s0.b + factor * (s1.b - s0.b));
  return `rgb(${r}, ${g}, ${b})`;
}
```

---

### Rendering Fixtures, Orientations & Aim Vectors

For each luminaire in `response.fixtures`:

1. **Center Point on Screen:**
   $$C_x = f.position.x \cdot S + O_x, \quad C_y = O_y - f.position.y \cdot S$$

2. **Luminous Opening Corners:**
   Draw a filled polygon connecting `f.corners[0..3]` converted to screen coordinates:
   $$\text{CornerScreen}_i = (f.corners[i].x \cdot S + O_x, \quad O_y - f.corners[i].y \cdot S)$$
   Fill color: `#f0a202` (gold) with stroke `#fff`.

3. **Orientation & Aim Arrow (Tilt Visualization):**
   - When luminaire is tilted ($f.aimDirection.z > -1.0$ or $f.tiltAngle > 0$):
     - The aim vector in plan view has direction $(\Delta X, \Delta Y) = (f.aimDirection.x, f.aimDirection.y)$.
     - Draw an arrow starting at $(C_x, C_y)$ pointing to $(C_x + \Delta X \cdot 24, C_y - \Delta Y \cdot 24)$.
   - When downlight is untilted ($f.tiltAngle = 0^\circ$):
     - Draw a clean central crosshair or dot at $(C_x, C_y)$.

---

### Wall Elevation Unrolling

Each room perimeter edge from vertex $V_i=(x_i, y_i)$ to $V_{i+1}=(x_{i+1}, y_{i+1})$ represents a vertical wall plane with id `W0`, `W1`...
- **Wall Length:** $L = \sqrt{(x_{i+1} - x_i)^2 + (y_{i+1} - y_i)^2}$
- **Wall Height:** $H = \text{ceilingHeight}$
- **Unit Tangent Vector along wall:** $\mathbf{u} = \left(\frac{x_{i+1} - x_i}{L}, \frac{y_{i+1} - y_i}{L}\right)$

For each wall patch $P$ in `response.wallPatches[wallId]`:
- **Local Along-Wall Coordinate:** $s = (P.center.x - x_i) \cdot u_x + (P.center.y - y_i) \cdot u_y$
- **Local Vertical Elevation:** $z = P.center.z$
- **Render on 2D Elevation Canvas ($W_{\text{canvas}} \times H_{\text{canvas}}$):**
  $$X_w = \frac{s}{L} \cdot W_{\text{canvas}}, \quad Y_w = H_{\text{canvas}} - \frac{z}{H} \cdot H_{\text{canvas}}$$
  Draw cell colored by corresponding lux value in `response.totalWallIlluminance[wallId].values[patchIndex]`.

---

### Matrix Layering & Direct/Indirect Isolation

The frontend can isolate individual lighting components without making new API requests:

- **Total Floor Illuminance:**
  `response.totalFloorIlluminance.values`
- **Direct Illuminance from Fixture $F_k$:**
  `response.directFloorMatrices["Fk"].values`
- **Indirect Reflection Contribution (Walls/Ceiling Bounces):**
  $$E_{\text{indirect}}[i] = \sum_{\text{origin}} \text{response.indirectFloorMatrices}[\text{origin}].values[i]$$
- **Summing Active Matrices on Client:**
  To toggle specific fixtures or layers on/off in the UI:
  $$E_{\text{composite}}[i] = \sum_{m \in \text{SelectedMatrices}} m.values[i]$$

---

### Interactive Free Drag-and-Drop & Snapping Math

When implementing interactive placement on the plan canvas:

1. **Screen Pixel $(X_s, Y_s)$ to World Coordinate $(x_w, y_w)$:**
   $$x_w = \frac{X_s - O_x}{S}, \quad y_w = \frac{O_y - Y_s}{S}$$

2. **Grid Snapping (step $\Delta = 0.1m, 0.25m, 0.5m$):**
   $$x_{\text{snapped}} = \text{round}\left(\frac{x_w}{\Delta}\right) \times \Delta$$
   $$y_{\text{snapped}} = \text{round}\left(\frac{y_w}{\Delta}\right) \times \Delta$$

3. **Boundary Containment Check (Ray-Casting Algorithm):**
   Ensure $(x_{\text{snapped}}, y_{\text{snapped}})$ lies strictly inside the polygon before updating the fixture position:
   ```javascript
   function pointInPolygon(pt, poly) {
     let inside = false;
     for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
       const xi = poly[i].x, yi = poly[i].y;
       const xj = poly[j].x, yj = poly[j].y;
       const intersect = ((yi > pt.y) !== (yj > pt.y)) &&
         (pt.x < ((xj - xi) * (pt.y - yi)) / (yj - yi) + xi);
       if (intersect) inside = !inside;
     }
     return inside;
   }
   ```
4. **Trigger Fast Recalculation:**
   On drag release (`pointerup`), construct the payload with `fixtures: freeFixtures` and POST to `/calculate` to refresh the radiosity matrix and compliance badge.
