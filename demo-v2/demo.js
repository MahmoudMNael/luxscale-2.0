const API = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

const PRESETS = {
  rect: [
    [0, 0],
    [8, 0],
    [8, 6],
    [0, 6],
  ],
  l: [
    [0, 0],
    [8, 0],
    [8, 3],
    [3, 3],
    [3, 8],
    [0, 8],
  ],
  room: [
    [0, 0],
    [4.85, 0],
    [4.85, 5.26],
    [1.45, 5.26],
    [1.45, 4.33],
    [0.55, 4.33],
    [0.55, 1.63],
    [0, 1.63],
  ],
};

const els = {
  form: document.getElementById("form"),
  verts: document.querySelector("#verts tbody"),
  polyPreview: document.getElementById("polyPreview"),
  polyMeta: document.getElementById("polyMeta"),
  floorLayer: document.getElementById("floorLayer"),
  plan: document.getElementById("plan"),
  stats: document.getElementById("stats"),
  status: document.getElementById("status"),
  walls: document.getElementById("walls"),
  matrices: document.getElementById("matrices"),
  legMin: document.getElementById("legMin"),
  legMax: document.getElementById("legMax"),
  wallMargin: document.getElementById("wallMargin"),
  dialuxNearest: document.getElementById("dialuxNearest"),
  // Grid mode panels
  gridTabs: document.getElementById("gridModeTabs"),
  panelCount: document.getElementById("panelCount"),
  panelSpacing: document.getElementById("panelSpacing"),
  panelAxis: document.getElementById("panelAxis"),
  panelFree: document.getElementById("panelFree"),
  freeFixturesTable: document.querySelector("#freeFixturesTable tbody"),
  freeCountBadge: document.getElementById("freeCountBadge"),
  btnAddFree: document.getElementById("btnAddFree"),
  btnPopulateFromGrid: document.getElementById("btnPopulateFromGrid"),
  btnClearFree: document.getElementById("btnClearFree"),
  // Canvas Tools
  btnUnlockGrid: document.getElementById("btnUnlockGrid"),
  toolSelect: document.getElementById("toolSelect"),
  toolAdd: document.getElementById("toolAdd"),
  snapSelect: document.getElementById("snapSelect"),
  btnRecalc: document.getElementById("btnRecalc"),
  canvasNotice: document.getElementById("canvasOverlayNotice"),
  // Inspector
  inspectorPanel: document.getElementById("inspectorPanel"),
  inspEmpty: document.getElementById("inspEmpty"),
  inspControls: document.getElementById("inspControls"),
  inspTitle: document.getElementById("inspTitle"),
  inspBadge: document.getElementById("inspBadge"),
  inspX: document.getElementById("inspX"),
  inspY: document.getElementById("inspY"),
  inspZ: document.getElementById("inspZ"),
  inspRot: document.getElementById("inspRot"),
  inspRotVal: document.getElementById("inspRotVal"),
  inspTilt: document.getElementById("inspTilt"),
  inspTiltVal: document.getElementById("inspTiltVal"),
  inspVariantId: document.getElementById("inspVariantId"),
  inspIesRef: document.getElementById("inspIesRef"),
  inspAimVector: document.getElementById("inspAimVector"),
  btnInspDup: document.getElementById("btnInspDup"),
  btnInspDel: document.getElementById("btnInspDel"),
  btnInspRecalc: document.getElementById("btnInspRecalc"),
  // Study Source & Variants
  studyTabs: document.getElementById("studySourceTabs"),
  panelIesFile: document.getElementById("panelIesFile"),
  panelVariants: document.getElementById("panelVariants"),
  variantsShelf: document.getElementById("variantsShelf"),
  variantsList: document.getElementById("variantsList"),
  // Compliance
  complianceBanner: document.getElementById("complianceBanner"),
  compBadge: document.getElementById("compBadge"),
  compAvgLux: document.getElementById("compAvgLux"),
  compTargetLux: document.getElementById("compTargetLux"),
  compUniformity: document.getElementById("compUniformity"),
  compTargetU0: document.getElementById("compTargetU0"),
  compMinMax: document.getElementById("compMinMax"),
  compMF: document.getElementById("compMF"),
};

let vertices = PRESETS.room.map(([x, y]) => ({ x, y }));
let result = null;
let multiVariantResults = null;
let activeVariantIndex = 0;
let layers = [];

// Interactive Placement State
let gridMode = "count"; // 'count' | 'spacing' | 'axis' | 'free'
let studySource = "file"; // 'file' | 'variants'
let freeFixtures = []; // [{ id, x, y, z, rotation, tiltAngle }]
let selectedFixtureIndex = -1;
let activeTool = "select"; // 'select' | 'add'
let isDragging = false;
let dragOffset = { dx: 0, dy: 0 };
let lastPlanMapper = null;
let lastPlanBounds = null;

function num(id) {
  const el = document.getElementById(id);
  return el ? Number(el.value) : 0;
}

function optNum(id) {
  const el = document.getElementById(id);
  if (!el || el.value === "" || el.value == null) return null;
  const v = Number(el.value);
  return Number.isFinite(v) ? v : null;
}

function signedArea(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const q = pts[(i + 1) % pts.length];
    a += p.x * q.y - q.x * p.y;
  }
  return a / 2;
}

const EPS = 1e-9;

function distToSegment(p, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 < EPS * EPS) return Math.hypot(p.x - a.x, p.y - a.y);
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

function distToPolygon(p, poly) {
  let d = Infinity;
  for (let i = 0; i < poly.length; i++) {
    d = Math.min(d, distToSegment(p, poly[i], poly[(i + 1) % poly.length]));
  }
  return d;
}

function wallMargin() {
  const v = Number(els.wallMargin.value);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

function keptFloorIndices(patches) {
  const m = wallMargin();
  if (!(m > 0)) return patches.map((_, i) => i);
  const out = [];
  patches.forEach((p, i) => {
    if (distToPolygon(p.center, vertices) >= m - EPS) out.push(i);
  });
  return out;
}

function layerStats(values, indices) {
  if (!indices.length) return { min: 0, max: 0, avg: 0, minI: -1, maxI: -1, kept: 0 };
  let min = Infinity;
  let max = -Infinity;
  let sum = 0;
  let minI = indices[0];
  let maxI = indices[0];
  for (const i of indices) {
    const v = values[i];
    sum += v;
    if (v < min) {
      min = v;
      minI = i;
    }
    if (v > max) {
      max = v;
      maxI = i;
    }
  }
  return { min, max, avg: sum / indices.length, minI, maxI, kept: indices.length };
}

function parseXY(xid, yid) {
  const xs = document.getElementById(xid).value;
  const ys = document.getElementById(yid).value;
  if (xs === "" || ys === "") return null;
  const x = Number(xs);
  const y = Number(ys);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function nearestPatch(pt, patches) {
  let iBest = 0;
  let dBest = Infinity;
  patches.forEach((p, i) => {
    const d = Math.hypot(p.center.x - pt.x, p.center.y - pt.y);
    if (d < dBest) {
      dBest = d;
      iBest = i;
    }
  });
  return { i: iBest, d: dBest };
}

function fmtXY(p) {
  return p ? `(${p.x.toFixed(2)}, ${p.y.toFixed(2)})` : "(—, —)";
}

function onSegment(p, a, b) {
  const cross = (p.x - a.x) * (b.y - a.y) - (p.y - a.y) * (b.x - a.x);
  if (Math.abs(cross) > EPS) return false;
  return (
    Math.min(a.x, b.x) - EPS <= p.x &&
    p.x <= Math.max(a.x, b.x) + EPS &&
    Math.min(a.y, b.y) - EPS <= p.y &&
    p.y <= Math.max(a.y, b.y) + EPS
  );
}

function pointInPolygon(point, polygon) {
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    if (onSegment(point, polygon[i], polygon[(i + 1) % n])) return true;
  }
  let inside = false;
  const { x, y } = point;
  for (let i = 0; i < n; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % n];
    const intersects = a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y || EPS) + a.x;
    if (intersects) inside = !inside;
  }
  return inside;
}

function axisPoints(lo, hi, spacing, offsetBeginning, offsetEnding) {
  if (!(spacing > 0)) return [];
  const start = lo + offsetBeginning;
  const stop = hi - offsetEnding;
  const points = [];
  for (let x = start; x <= stop + EPS; x += spacing) points.push(x);
  return points;
}

// Preview math supporting Count, Spacing, Axis, and Free modes
function previewFixtures(pts) {
  if (gridMode === "free") {
    return freeFixtures.map((f) => ({
      id: f.id,
      x: f.x,
      y: f.y,
      z: f.z,
      rotation: f.rotation,
      tiltAngle: f.tiltAngle,
    }));
  }

  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  const fixtures = [];
  let n = 1;
  const defaultRot = num("luminaireRotation") || 0;

  if (gridMode === "count") {
    const elX = document.getElementById("countX") || document.getElementById("countNx");
    const elY = document.getElementById("countY") || document.getElementById("countNy");
    const nx = Math.max(1, parseInt(elX ? elX.value : "1", 10) || 1);
    const ny = Math.max(1, parseInt(elY ? elY.value : "1", 10) || 1);
    const frac = optNum("offsetFraction") != null ? Number(document.getElementById("offsetFraction").value) : 0.5;
    const wx = Math.max(0.01, xmax - xmin);
    const wy = Math.max(0.01, ymax - ymin);

    let xPts = [];
    if (nx === 1) {
      xPts = [xmin + wx / 2];
    } else {
      const denomX = nx - 1 + 2 * frac;
      const sx = denomX > EPS ? wx / denomX : wx;
      const offX = sx * frac;
      for (let i = 0; i < nx; i++) xPts.push(xmin + offX + i * sx);
    }

    let yPts = [];
    if (ny === 1) {
      yPts = [ymin + wy / 2];
    } else {
      const denomY = ny - 1 + 2 * frac;
      const sy = denomY > EPS ? wy / denomY : wy;
      const offY = sy * frac;
      for (let j = 0; j < ny; j++) yPts.push(ymin + offY + j * sy);
    }

    for (const y of yPts) {
      for (const x of xPts) {
        if (!pointInPolygon({ x, y }, pts)) continue;
        fixtures.push({ id: `F${n}`, x, y, rotation: defaultRot, tiltAngle: 0 });
        n += 1;
      }
    }
  } else if (gridMode === "spacing") {
    const sx = Math.max(0.1, num("spacingX"));
    const sy = Math.max(0.1, num("spacingY"));
    const autoCenter = document.getElementById("spacingAutoCenter").checked;
    const wx = Math.max(0.01, xmax - xmin);
    const wy = Math.max(0.01, ymax - ymin);

    if (autoCenter) {
      const nx = Math.max(1, Math.round(wx / sx));
      const ny = Math.max(1, Math.round(wy / sy));
      const offX = (wx - (nx - 1) * sx) / 2;
      const offY = (wy - (ny - 1) * sy) / 2;
      const xPts = [];
      const yPts = [];
      for (let i = 0; i < nx; i++) xPts.push(xmin + offX + i * sx);
      for (let j = 0; j < ny; j++) yPts.push(ymin + offY + j * sy);
      for (const y of yPts) {
        for (const x of xPts) {
          if (!pointInPolygon({ x, y }, pts)) continue;
          fixtures.push({ id: `F${n}`, x, y, rotation: defaultRot, tiltAngle: 0 });
          n += 1;
        }
      }
    } else {
      const ox = optNum("spacingOffsetX") || 0;
      const oy = optNum("spacingOffsetY") || 0;
      for (let y = ymin + oy; y <= ymax - oy + EPS; y += sy) {
        for (let x = xmin + ox; x <= xmax - ox + EPS; x += sx) {
          if (!pointInPolygon({ x, y }, pts)) continue;
          fixtures.push({ id: `F${n}`, x, y, rotation: defaultRot, tiltAngle: 0 });
          n += 1;
        }
      }
    }
  } else {
    // Axis mode
    const gx = { spacing: num("xSpacing"), offB: num("xOffB"), offE: num("xOffE") };
    const gy = { spacing: num("ySpacing"), offB: num("yOffB"), offE: num("yOffE") };
    for (const y of axisPoints(ymin, ymax, gy.spacing, gy.offB, gy.offE)) {
      for (const x of axisPoints(xmin, xmax, gx.spacing, gx.offB, gx.offE)) {
        if (!pointInPolygon({ x, y }, pts)) continue;
        fixtures.push({ id: `F${n}`, x, y, rotation: defaultRot, tiltAngle: 0 });
        n += 1;
      }
    }
  }

  return fixtures;
}

function drawPolygonPreview() {
  const canvas = els.polyPreview;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const pts = vertices.filter((v) => Number.isFinite(v.x) && Number.isFinite(v.y));
  if (pts.length < 2) {
    els.polyMeta.textContent = "Need at least 2 vertices to preview.";
    return;
  }
  const fixtures = pts.length >= 3 ? previewFixtures(pts) : [];
  const b = boundsOf(pts);
  const to = mapper(canvas, b);
  const area = Math.abs(signedArea(pts));

  ctx.strokeStyle = "#2b3345";
  ctx.lineWidth = 1;
  const origin = to(b.xmin, b.ymin);
  const far = to(b.xmax, b.ymax);
  ctx.strokeRect(origin.x, far.y, far.x - origin.x, origin.y - far.y);

  ctx.fillStyle = "rgba(61, 139, 253, 0.15)";
  ctx.strokeStyle = "#3d8bfd";
  ctx.lineWidth = 2;
  ctx.beginPath();
  pts.forEach((v, i) => {
    const p = to(v.x, v.y);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  pts.forEach((v, i) => {
    const p = to(v.x, v.y);
    ctx.fillStyle = "#8b95ab";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#e8edf7";
    ctx.font = "10px sans-serif";
    ctx.fillText(String(i + 1), p.x + 5, p.y - 5);
  });

  fixtures.forEach((f) => {
    const p = to(f.x, f.y);
    ctx.fillStyle = "#e0a106";
    ctx.beginPath();
    ctx.moveTo(p.x, p.y - 4);
    ctx.lineTo(p.x + 4, p.y);
    ctx.lineTo(p.x, p.y + 4);
    ctx.lineTo(p.x - 4, p.y);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#fff7cc";
    ctx.font = "9px sans-serif";
    ctx.fillText(f.id, p.x + 5, p.y + 3);
  });

  els.polyMeta.textContent = `${pts.length} verts · ${fixtures.length} fixtures (${gridMode}) · bbox ${b.w.toFixed(2)}×${b.h.toFixed(2)} m · area ≈ ${area.toFixed(2)} m²`;
}

function renderVerts() {
  els.verts.innerHTML = vertices
    .map(
      (v, i) => `<tr>
        <td><input data-i="${i}" data-k="x" type="number" step="0.01" value="${v.x}" /></td>
        <td><input data-i="${i}" data-k="y" type="number" step="0.01" value="${v.y}" /></td>
        <td><button type="button" class="ghost del" data-i="${i}">×</button></td>
      </tr>`
    )
    .join("");
  drawPolygonPreview();
  if (result) renderAll();
}

els.verts.addEventListener("input", (ev) => {
  const el = ev.target;
  if (!el.dataset.i) return;
  vertices[Number(el.dataset.i)][el.dataset.k] = Number(el.value);
  drawPolygonPreview();
});
els.verts.addEventListener("click", (ev) => {
  if (!ev.target.classList.contains("del")) return;
  if (vertices.length <= 3) return;
  vertices.splice(Number(ev.target.dataset.i), 1);
  renderVerts();
});
document.getElementById("addVert").onclick = () => {
  const last = vertices[vertices.length - 1];
  vertices.push({ x: Number((last.x + 1).toFixed(2)), y: last.y });
  renderVerts();
};
document.getElementById("presetRect").onclick = () => {
  vertices = PRESETS.rect.map(([x, y]) => ({ x, y }));
  renderVerts();
};
document.getElementById("presetL").onclick = () => {
  vertices = PRESETS.l.map(([x, y]) => ({ x, y }));
  renderVerts();
};
document.getElementById("presetRoom").onclick = () => {
  vertices = PRESETS.room.map(([x, y]) => ({ x, y }));
  renderVerts();
};

els.form.addEventListener("input", (ev) => {
  if (ev.target.closest("#verts")) return;
  if (ev.target.type === "number" || ev.target.type === "checkbox") {
    drawPolygonPreview();
  }
});

// Grid Mode Switching
function setGridMode(mode) {
  gridMode = mode;
  document.querySelectorAll("#gridModeTabs .tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  els.panelCount.hidden = mode !== "count";
  els.panelSpacing.hidden = mode !== "spacing";
  els.panelAxis.hidden = mode !== "axis";
  els.panelFree.hidden = mode !== "free";
  els.canvasNotice.hidden = mode !== "free";

  if (mode === "free" && freeFixtures.length === 0) {
    populateFreeFromPreview();
  }
  drawPolygonPreview();
  if (result) renderAll();
}

document.querySelectorAll("#gridModeTabs .tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => setGridMode(btn.dataset.mode));
});

const spacingAutoCenterEl = document.getElementById("spacingAutoCenter");
if (spacingAutoCenterEl) {
  spacingAutoCenterEl.addEventListener("change", (ev) => {
    const offsetGrid = document.getElementById("spacingOffsetGrid");
    if (offsetGrid) offsetGrid.hidden = ev.target.checked;
    drawPolygonPreview();
  });
}

// Study Source Switching (Upload IES vs Multi-Variant JSON)
function setStudySource(src) {
  studySource = src;
  document.querySelectorAll("#studySourceTabs .tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.source === src);
  });
  els.panelIesFile.hidden = src !== "file";
  els.panelVariants.hidden = src !== "variants";
}

document.querySelectorAll("#studySourceTabs .tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => setStudySource(btn.dataset.source));
});

// Compliance Target Presets
document.querySelectorAll(".comp-preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.getElementById("targetLux").value = btn.dataset.lux;
    document.getElementById("minUniformity").value = btn.dataset.u0;
    if (result) renderAll();
  });
});

// Free Placement Helpers
function populateFreeFromPreview() {
  let pts = [];
  if (result && result.fixtures && result.fixtures.length > 0) {
    pts = result.fixtures.map((f, i) => ({
      id: f.id || `F${i + 1}`,
      x: Number(f.position.x.toFixed(3)),
      y: Number(f.position.y.toFixed(3)),
      z: f.position.z != null ? Number(f.position.z.toFixed(3)) : null,
      rotation: f.rotation || 0,
      tiltAngle: f.tiltAngle || 0,
    }));
  } else {
    pts = previewFixtures(vertices).map((f, i) => ({
      id: f.id || `F${i + 1}`,
      x: Number(f.x.toFixed(3)),
      y: Number(f.y.toFixed(3)),
      z: null,
      rotation: num("luminaireRotation") || 0,
      tiltAngle: 0,
    }));
  }
  freeFixtures = pts;
  selectedFixtureIndex = freeFixtures.length > 0 ? 0 : -1;
  renderFreeFixturesList();
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
}

function unlockGridToFree() {
  populateFreeFromPreview();
  setGridMode("free");
  showStatus("Grid unlocked! Fixtures are now free and draggable on the floor plan.", "ok");
}

els.btnUnlockGrid.addEventListener("click", unlockGridToFree);
els.btnPopulateFromGrid.addEventListener("click", populateFreeFromPreview);
els.btnClearFree.addEventListener("click", () => {
  freeFixtures = [];
  selectedFixtureIndex = -1;
  renderFreeFixturesList();
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
});

els.btnAddFree.addEventListener("click", () => {
  const b = boundsOf(vertices);
  const cx = Number(((b.xmin + b.xmax) / 2).toFixed(2));
  const cy = Number(((b.ymin + b.ymax) / 2).toFixed(2));
  addFreeFixture(cx, cy);
});

function addFreeFixture(x, y) {
  const id = `F${freeFixtures.length + 1}`;
  const defaultVar = (document.getElementById("variantId") || {}).value?.trim() || undefined;
  freeFixtures.push({
    id,
    x: Number(x.toFixed(3)),
    y: Number(y.toFixed(3)),
    z: null,
    rotation: num("luminaireRotation") || 0,
    tiltAngle: 0,
    variantId: defaultVar,
  });
  selectedFixtureIndex = freeFixtures.length - 1;
  renderFreeFixturesList();
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
}

function renderFreeFixturesList() {
  els.freeCountBadge.textContent = `${freeFixtures.length} fixture${freeFixtures.length === 1 ? "" : "s"}`;
  els.freeFixturesTable.innerHTML = freeFixtures
    .map(
      (f, i) => `<tr class="${i === selectedFixtureIndex ? "active-row" : ""}" data-idx="${i}">
        <td><strong>${f.id}</strong></td>
        <td><input type="number" step="0.05" class="ff-x" data-idx="${i}" value="${f.x}" /></td>
        <td><input type="number" step="0.05" class="ff-y" data-idx="${i}" value="${f.y}" /></td>
        <td><input type="number" step="5" min="0" max="360" class="ff-rot" data-idx="${i}" value="${f.rotation || 0}" /></td>
        <td><input type="number" step="5" min="0" max="90" class="ff-tilt" data-idx="${i}" value="${f.tiltAngle || 0}" /></td>
        <td><button type="button" class="ghost del-ff" data-idx="${i}">×</button></td>
      </tr>`
    )
    .join("");
}

els.freeFixturesTable.addEventListener("click", (ev) => {
  const tr = ev.target.closest("tr");
  if (!tr) return;
  const idx = Number(tr.dataset.idx);
  if (ev.target.classList.contains("del-ff")) {
    freeFixtures.splice(idx, 1);
    if (selectedFixtureIndex >= freeFixtures.length) selectedFixtureIndex = freeFixtures.length - 1;
    renderFreeFixturesList();
    updateInspector();
    drawPolygonPreview();
    if (result) renderAll();
    return;
  }
  selectedFixtureIndex = idx;
  renderFreeFixturesList();
  updateInspector();
  if (result) renderAll();
});

els.freeFixturesTable.addEventListener("input", (ev) => {
  const el = ev.target;
  const idx = Number(el.dataset.idx);
  if (Number.isNaN(idx) || !freeFixtures[idx]) return;
  if (el.classList.contains("ff-x")) freeFixtures[idx].x = Number(el.value);
  if (el.classList.contains("ff-y")) freeFixtures[idx].y = Number(el.value);
  if (el.classList.contains("ff-rot")) freeFixtures[idx].rotation = Number(el.value);
  if (el.classList.contains("ff-tilt")) freeFixtures[idx].tiltAngle = Number(el.value);
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
});

// Fixture Inspector
function updateInspector() {
  if (selectedFixtureIndex < 0 || selectedFixtureIndex >= freeFixtures.length) {
    els.inspEmpty.hidden = false;
    els.inspControls.hidden = true;
    els.inspTitle.textContent = "Fixture Inspector";
    els.inspBadge.textContent = "—";
    return;
  }
  const f = freeFixtures[selectedFixtureIndex];
  els.inspEmpty.hidden = true;
  els.inspControls.hidden = false;
  els.inspTitle.textContent = `Fixture ${f.id}`;
  els.inspBadge.textContent = `#${selectedFixtureIndex + 1}`;
  els.inspX.value = f.x;
  els.inspY.value = f.y;
  els.inspZ.value = f.z != null ? f.z : "";
  els.inspRot.value = f.rotation || 0;
  els.inspRotVal.textContent = `${f.rotation || 0}°`;
  els.inspTilt.value = f.tiltAngle || 0;
  els.inspTiltVal.textContent = `${f.tiltAngle || 0}°`;
  if (els.inspVariantId) els.inspVariantId.value = f.variantId || "";
  if (els.inspIesRef) els.inspIesRef.value = f.iesRef || "";

  // Compute aim vector:
  const rotRad = ((f.rotation || 0) * Math.PI) / 180;
  const tiltRad = ((f.tiltAngle || 0) * Math.PI) / 180;
  const aimX = Math.sin(tiltRad) * Math.cos(rotRad);
  const aimY = Math.sin(tiltRad) * Math.sin(rotRad);
  const aimZ = -Math.cos(tiltRad);
  els.inspAimVector.textContent = `(${aimX.toFixed(2)}, ${aimY.toFixed(2)}, ${aimZ.toFixed(2)})`;
}

els.inspX.addEventListener("input", (ev) => {
  if (selectedFixtureIndex < 0) return;
  freeFixtures[selectedFixtureIndex].x = Number(ev.target.value);
  renderFreeFixturesList();
  drawPolygonPreview();
  if (result) renderAll();
});
els.inspY.addEventListener("input", (ev) => {
  if (selectedFixtureIndex < 0) return;
  freeFixtures[selectedFixtureIndex].y = Number(ev.target.value);
  renderFreeFixturesList();
  drawPolygonPreview();
  if (result) renderAll();
});
els.inspZ.addEventListener("input", (ev) => {
  if (selectedFixtureIndex < 0) return;
  const v = ev.target.value;
  freeFixtures[selectedFixtureIndex].z = v !== "" ? Number(v) : null;
  if (result) renderAll();
});
els.inspRot.addEventListener("input", (ev) => {
  if (selectedFixtureIndex < 0) return;
  const r = Number(ev.target.value);
  freeFixtures[selectedFixtureIndex].rotation = r;
  els.inspRotVal.textContent = `${r}°`;
  updateInspector();
  renderFreeFixturesList();
  drawPolygonPreview();
  if (result) renderAll();
});
els.inspTilt.addEventListener("input", (ev) => {
  if (selectedFixtureIndex < 0) return;
  const t = Number(ev.target.value);
  freeFixtures[selectedFixtureIndex].tiltAngle = t;
  els.inspTiltVal.textContent = `${t}°`;
  updateInspector();
  renderFreeFixturesList();
  drawPolygonPreview();
  if (result) renderAll();
});
if (els.inspVariantId) {
  els.inspVariantId.addEventListener("input", (ev) => {
    if (selectedFixtureIndex < 0) return;
    freeFixtures[selectedFixtureIndex].variantId = ev.target.value.trim() || undefined;
  });
}
if (els.inspIesRef) {
  els.inspIesRef.addEventListener("input", (ev) => {
    if (selectedFixtureIndex < 0) return;
    freeFixtures[selectedFixtureIndex].iesRef = ev.target.value.trim() || undefined;
  });
}
els.btnInspDup.addEventListener("click", () => {
  if (selectedFixtureIndex < 0) return;
  const cur = freeFixtures[selectedFixtureIndex];
  const id = `F${freeFixtures.length + 1}`;
  freeFixtures.push({
    id,
    x: Number((cur.x + 0.3).toFixed(3)),
    y: Number((cur.y + 0.3).toFixed(3)),
    z: cur.z,
    rotation: cur.rotation,
    tiltAngle: cur.tiltAngle,
    variantId: cur.variantId,
    iesRef: cur.iesRef,
  });
  selectedFixtureIndex = freeFixtures.length - 1;
  renderFreeFixturesList();
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
});
els.btnInspDel.addEventListener("click", () => {
  if (selectedFixtureIndex < 0) return;
  freeFixtures.splice(selectedFixtureIndex, 1);
  selectedFixtureIndex = freeFixtures.length > 0 ? Math.min(selectedFixtureIndex, freeFixtures.length - 1) : -1;
  renderFreeFixturesList();
  updateInspector();
  drawPolygonPreview();
  if (result) renderAll();
});

// Canvas Interaction Tools (Move, Add, Snap)
els.toolSelect.addEventListener("click", () => {
  activeTool = "select";
  els.toolSelect.classList.add("active");
  els.toolAdd.classList.remove("active");
  els.plan.style.cursor = "default";
});
els.toolAdd.addEventListener("click", () => {
  activeTool = "add";
  els.toolAdd.classList.add("active");
  els.toolSelect.classList.remove("active");
  els.plan.style.cursor = "crosshair";
});

function getSnap() {
  return Number(els.snapSelect.value) || 0;
}

// Coordinate mapping
function boundsOf(points) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xmin = Math.min(...xs);
  const ymin = Math.min(...ys);
  const xmax = Math.max(...xs);
  const ymax = Math.max(...ys);
  return { xmin, ymin, xmax, ymax, w: Math.max(xmax - xmin, 0.01), h: Math.max(ymax - ymin, 0.01) };
}

function mapper(canvas, b) {
  const pad = 36;
  const s = Math.min((canvas.width - 2 * pad) / b.w, (canvas.height - 2 * pad) / b.h);
  return (x, y) => ({
    x: pad + (x - b.xmin) * s,
    y: canvas.height - pad - (y - b.ymin) * s,
    s,
  });
}

function unmapper(canvas, b) {
  const pad = 36;
  const s = Math.min((canvas.width - 2 * pad) / b.w, (canvas.height - 2 * pad) / b.h);
  return (px, py) => ({
    x: b.xmin + (px - pad) / s,
    y: b.ymin + (canvas.height - pad - py) / s,
  });
}

function luxColor(t) {
  const stops = [
    [13 / 255, 28 / 255, 51 / 255],
    [31 / 255, 111 / 255, 235 / 255],
    [240 / 255, 162 / 255, 2 / 255],
    [1, 247 / 255, 204 / 255],
  ];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  const c = a.map((v, k) => v + (b[k] - v) * f);
  return `rgb(${c.map((v) => Math.round(v * 255)).join(",")})`;
}

function stats(values) {
  if (!values.length) return { min: 0, max: 0, avg: 0 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return { min, max, avg };
}

// Mouse events on Plan Canvas for dragging, selection & adding
function getCanvasMousePos(canvas, ev) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return {
    px: (ev.clientX - rect.left) * scaleX,
    py: (ev.clientY - rect.top) * scaleY,
  };
}

function getActiveFixtures() {
  if (gridMode === "free") return freeFixtures;
  if (result && result.fixtures && result.fixtures.length > 0) {
    return result.fixtures.map((f) => ({
      id: f.id,
      x: f.position.x,
      y: f.position.y,
      z: f.position.z,
      rotation: f.rotation,
      tiltAngle: f.tiltAngle,
    }));
  }
  return previewFixtures(vertices);
}

function hitTestFixture(px, py, to, fixtures) {
  for (let i = fixtures.length - 1; i >= 0; i--) {
    const f = fixtures[i];
    const p = to(f.x, f.y);
    if (Math.hypot(p.x - px, p.y - py) <= 18) {
      return i;
    }
  }
  return -1;
}

els.plan.addEventListener("mousedown", (ev) => {
  if (!lastPlanMapper || !lastPlanBounds) return;
  const { px, py } = getCanvasMousePos(els.plan, ev);
  const unmap = unmapper(els.plan, lastPlanBounds);
  const roomPos = unmap(px, py);
  const fixtures = getActiveFixtures();
  const hit = hitTestFixture(px, py, lastPlanMapper, fixtures);

  if (hit >= 0) {
    // If not in free mode yet, switch to free mode automatically so user can drag!
    if (gridMode !== "free") {
      unlockGridToFree();
    }
    selectedFixtureIndex = hit;
    isDragging = true;
    dragOffset = {
      dx: freeFixtures[hit].x - roomPos.x,
      dy: freeFixtures[hit].y - roomPos.y,
    };
    els.plan.style.cursor = "grabbing";
    renderFreeFixturesList();
    updateInspector();
    renderAll();
  } else {
    if (activeTool === "add") {
      if (gridMode !== "free") unlockGridToFree();
      const snap = getSnap();
      let nx = roomPos.x;
      let ny = roomPos.y;
      if (snap > 0) {
        nx = Math.round(nx / snap) * snap;
        ny = Math.round(ny / snap) * snap;
      }
      addFreeFixture(nx, ny);
    } else {
      selectedFixtureIndex = -1;
      updateInspector();
      renderFreeFixturesList();
      renderAll();
    }
  }
});

els.plan.addEventListener("mousemove", (ev) => {
  if (!lastPlanMapper || !lastPlanBounds) return;
  const { px, py } = getCanvasMousePos(els.plan, ev);
  const unmap = unmapper(els.plan, lastPlanBounds);
  const roomPos = unmap(px, py);

  if (isDragging && selectedFixtureIndex >= 0 && selectedFixtureIndex < freeFixtures.length) {
    let nx = roomPos.x + dragOffset.dx;
    let ny = roomPos.y + dragOffset.dy;
    const snap = getSnap();
    if (snap > 0) {
      nx = Math.round(nx / snap) * snap;
      ny = Math.round(ny / snap) * snap;
    }
    freeFixtures[selectedFixtureIndex].x = Number(nx.toFixed(3));
    freeFixtures[selectedFixtureIndex].y = Number(ny.toFixed(3));
    updateInspector();
    renderAll();
  } else {
    const fixtures = getActiveFixtures();
    const hit = hitTestFixture(px, py, lastPlanMapper, fixtures);
    if (hit >= 0) {
      els.plan.style.cursor = "grab";
    } else if (activeTool === "add") {
      els.plan.style.cursor = "crosshair";
    } else {
      els.plan.style.cursor = "default";
    }
  }
});

window.addEventListener("mouseup", () => {
  if (isDragging) {
    isDragging = false;
    els.plan.style.cursor = "grab";
    renderFreeFixturesList();
    drawPolygonPreview();
  }
});

function drawPlan(layer, s, kept) {
  const canvas = els.plan;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const patches = result?.floorPatches || [];
  const pts = patches.map((p) => p.center);
  const fixtures = getActiveFixtures();
  const extra = fixtures.map((f) => ({ x: f.x, y: f.y }));
  const b = boundsOf([...pts, ...extra, ...vertices]);
  lastPlanBounds = b;
  const to = mapper(canvas, b);
  lastPlanMapper = to;

  els.legMin.textContent = s.kept ? `${s.min.toFixed(1)} lx` : "0 lx";
  els.legMax.textContent = s.kept ? `${s.max.toFixed(1)} lx` : "0 lx";
  const span = s.max - s.min || 1;
  const keptSet = new Set(kept);

  // 1. Heatmap patches
  if (patches.length && layer && layer.values) {
    patches.forEach((p, i) => {
      const half = p.size / 2;
      const a = to(p.center.x - half, p.center.y - half);
      const c = to(p.center.x + half, p.center.y + half);
      if (keptSet.has(i) && s.kept) {
        ctx.fillStyle = luxColor((layer.values[i] - s.min) / span);
      } else {
        ctx.fillStyle = "rgba(232, 237, 247, 0.05)";
      }
      ctx.fillRect(a.x, c.y, c.x - a.x, a.y - c.y);
    });
  }

  // 2. Room polygon boundary
  ctx.strokeStyle = "#d5dced";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  vertices.forEach((v, i) => {
    const p = to(v.x, v.y);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.stroke();

  // 3. Fixtures with tilt vectors and selection indicators
  fixtures.forEach((f, idx) => {
    const p = to(f.x, f.y);
    const isSel = idx === selectedFixtureIndex;
    const rot = f.rotation || 0;
    const tilt = f.tiltAngle || 0;

    // Fixture body
    ctx.fillStyle = isSel ? "#00d2ff" : "#e0a106";
    ctx.strokeStyle = isSel ? "#ffffff" : "#e0a106";
    ctx.lineWidth = isSel ? 2 : 1.5;

    ctx.beginPath();
    ctx.moveTo(p.x, p.y - 7);
    ctx.lineTo(p.x + 7, p.y);
    ctx.lineTo(p.x, p.y + 7);
    ctx.lineTo(p.x - 7, p.y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Tilt & Aim direction vector arrow:
    if (tilt > 0) {
      const rotRad = (rot * Math.PI) / 180;
      const tiltRad = (tilt * Math.PI) / 180;
      // In 2D plan, screen Y is inverted relative to room Y
      const dirX = Math.cos(rotRad);
      const dirY = -Math.sin(rotRad);
      const arrowLen = 18 + 26 * Math.sin(tiltRad);
      const endX = p.x + dirX * arrowLen;
      const endY = p.y + dirY * arrowLen;

      // Draw light beam cone/triangle
      const perpX = -dirY * 8 * Math.sin(tiltRad);
      const perpY = dirX * 8 * Math.sin(tiltRad);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(endX + perpX, endY + perpY);
      ctx.lineTo(endX - perpX, endY - perpY);
      ctx.closePath();
      ctx.fillStyle = isSel ? "rgba(0, 210, 255, 0.22)" : "rgba(255, 213, 107, 0.2)";
      ctx.fill();

      // Main aim arrow
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(endX, endY);
      ctx.strokeStyle = isSel ? "#00d2ff" : "#ffd56b";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Arrow head
      ctx.beginPath();
      ctx.arc(endX, endY, 3, 0, Math.PI * 2);
      ctx.fillStyle = isSel ? "#00d2ff" : "#ffd56b";
      ctx.fill();

      // Tilt angle label
      ctx.fillStyle = isSel ? "#00d2ff" : "#ffd56b";
      ctx.font = "bold 9px sans-serif";
      ctx.fillText(`${tilt}°`, endX + 4, endY - 3);
    }

    // Selection halo & resize/drag circle
    if (isSel) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 14, 0, Math.PI * 2);
      ctx.strokeStyle = "#00d2ff";
      ctx.lineWidth = 2;
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Fixture ID & Z label
    ctx.fillStyle = isSel ? "#00d2ff" : "#fff7cc";
    ctx.font = isSel ? "bold 11px sans-serif" : "10px sans-serif";
    const zStr = f.z != null ? ` z=${f.z.toFixed(2)}` : "";
    ctx.fillText(`${f.id}${zStr}`, p.x + 9, p.y - 7);
  });

  // 4. Min / Max indicators
  function ring(i, color) {
    if (i < 0 || !patches[i]) return;
    const q = to(patches[i].center.x, patches[i].center.y);
    ctx.beginPath();
    ctx.arc(q.x, q.y, 7, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ring(s.minI, "#3d8bfd");
  ring(s.maxI, "#fff7cc");
}

function drawWall(canvas, patches, values) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!patches.length) return;
  const { min, max } = stats(values);
  const span = max - min || 1;
  const s0 = patches[0];
  const ux = s0.normal.y;
  const uy = -s0.normal.x;
  const along = patches.map((p) => p.center.x * ux + p.center.y * uy);
  const zs = patches.map((p) => p.center.z);
  const b = {
    xmin: Math.min(...along),
    xmax: Math.max(...along),
    ymin: Math.min(...zs),
    ymax: Math.max(...zs),
  };
  b.w = Math.max(b.xmax - b.xmin, 0.01);
  b.h = Math.max(b.ymax - b.ymin, 0.01);
  const to = mapper(canvas, b);
  patches.forEach((p, i) => {
    const s = p.center.x * ux + p.center.y * uy;
    const half = p.size / 2;
    const a = to(s - half, p.center.z - half);
    const c = to(s + half, p.center.z + half);
    ctx.fillStyle = luxColor((values[i] - min) / span);
    ctx.fillRect(a.x, c.y, Math.max(c.x - a.x, 2), Math.max(a.y - c.y, 2));
  });
}

function drawPlanMini(canvas, patches, values) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!patches.length || !values.length) return;
  const { min, max } = stats(values);
  const span = max - min || 1;
  const pts = patches.map((p) => p.center);
  const b = boundsOf(pts);
  const to = mapper(canvas, b);
  patches.forEach((p, i) => {
    const half = p.size / 2;
    const a = to(p.center.x - half, p.center.y - half);
    const c = to(p.center.x + half, p.center.y + half);
    ctx.fillStyle = luxColor((values[i] - min) / span);
    ctx.fillRect(a.x, c.y, Math.max(c.x - a.x, 2), Math.max(a.y - c.y, 2));
  });
}

function matrixTable(title, matrix, patches) {
  if (!matrix || !matrix.values) return "";
  const rows = matrix.values
    .slice(0, 100) // preview first 100 for DOM speed
    .map((v, i) => {
      const p = patches[i];
      const loc = p ? `${p.id} (${p.center.x.toFixed(2)}, ${p.center.y.toFixed(2)}, ${p.center.z.toFixed(2)})` : i;
      return `<tr><td>${loc}</td><td>${v.toFixed(3)}</td></tr>`;
    })
    .join("");
  const truncated = matrix.values.length > 100 ? `<div class="hint">Showing first 100 of ${matrix.values.length} patches</div>` : "";
  return `<article class="matrix">
    <h3>${title}</h3>
    <div class="meta">${JSON.stringify(matrix.metadata || {})}</div>
    <table><thead><tr><th>patch</th><th>lux</th></tr></thead><tbody>${rows}</tbody></table>
    ${truncated}
  </article>`;
}

function sumMatrices(matrices) {
  if (!matrices.length) return { values: [], metadata: { kind: "sum-client" } };
  const values = matrices[0].values.map((_, i) => matrices.reduce((acc, m) => acc + (m.values ? m.values[i] : 0), 0));
  return { values, metadata: { kind: "sum-client" } };
}

function rebuildLayers() {
  if (!result) return;
  layers = [{ id: "total", label: "Total floor", matrix: result.totalFloorIlluminance, patches: result.floorPatches || [] }];
  for (const [fid, matrix] of Object.entries(result.directFloorMatrices || {})) {
    layers.push({ id: `df-${fid}`, label: `Direct floor · ${fid}`, matrix, patches: result.floorPatches });
  }
  for (const [wid, matrix] of Object.entries(result.indirectFloorMatrices || {})) {
    const b = matrix.metadata?.bounces ?? result.bounces ?? "?";
    const rw = matrix.metadata?.wallReflectance ?? result.wallReflectance ?? "?";
    const rf = matrix.metadata?.floorReflectance ?? result.floorReflectance ?? "?";
    const rc = matrix.metadata?.ceilingReflectance ?? result.ceilingReflectance ?? "?";
    layers.push({ id: `if-${wid}`, label: `Indirect floor · ${wid} · ${b} bounces · ρw=${rw} ρf=${rf} ρc=${rc}`, matrix, patches: result.floorPatches });
  }
  els.floorLayer.innerHTML = layers.map((l) => `<option value="${l.id}">${l.label}</option>`).join("");
  els.floorLayer.disabled = false;
}

function dialuxCompare(values) {
  const patches = result?.floorPatches || [];
  if (!patches.length) return;
  const parts = [];
  function one(label, xid, yid) {
    const pt = parseXY(xid, yid);
    if (!pt) return;
    const { i, d } = nearestPatch(pt, patches);
    const p = patches[i];
    parts.push(
      `${label} ${fmtXY(pt)} → ${p.id} ${fmtXY(p.center)} ${values[i].toFixed(1)} lux · Δ ${d.toFixed(3)} m`
    );
  }
  one("Dialux min", "dxMinX", "dxMinY");
  one("Dialux max", "dxMaxX", "dxMaxY");
  els.dialuxNearest.textContent = parts.length
    ? parts.join(" · ")
    : "Enter DIALux min/max coordinates to compare lux at the nearest patch (no re-run).";
}

function updateComplianceBanner(ev, comp) {
  els.complianceBanner.hidden = false;
  const targetL = optNum("targetLux") || 500;
  const targetU = optNum("minUniformity") || 0.6;
  const avg = ev ? ev.average : comp?.actualLux || 0;
  const u0 = ev ? ev.uniformity : comp?.actualUniformity || 0;
  const min = ev ? ev.minimum : 0;
  const max = ev ? ev.maximum : 0;

  const isCompliant = comp ? comp.compliant : (avg >= targetL && u0 >= targetU);
  els.compBadge.className = `badge ${isCompliant ? "badge-pass" : "badge-fail"}`;
  els.compBadge.textContent = isCompliant ? "✓ COMPLIANT" : "✗ NON-COMPLIANT";

  els.compAvgLux.textContent = `${avg.toFixed(1)} lx`;
  els.compTargetLux.textContent = `target ≥ ${targetL} lx`;
  els.compUniformity.textContent = u0.toFixed(3);
  els.compTargetU0.textContent = `target ≥ ${targetU.toFixed(2)}`;
  els.compMinMax.textContent = `${min.toFixed(1)} / ${max.toFixed(1)} lx`;
  els.compMF.textContent = (result.maintenanceFactor != null ? result.maintenanceFactor : (num("maintenanceFactor") || 0.8)).toFixed(2);
}

function renderVariantsShelf() {
  if (!multiVariantResults || multiVariantResults.length <= 1) {
    els.variantsShelf.hidden = true;
    return;
  }
  els.variantsShelf.hidden = false;
  els.variantsList.innerHTML = multiVariantResults
    .map((vr, i) => {
      const vid = vr.variantId || `Variant ${i + 1}`;
      const ev = vr.evaluation;
      const comp = vr.compliance;
      const pass = comp ? comp.compliant : true;
      const avg = ev ? ev.average.toFixed(1) : "—";
      const u0 = ev ? ev.uniformity.toFixed(3) : "—";
      const pw = vr.powerW != null ? `${vr.powerW.toFixed(1)} W` : "";
      const pd = vr.powerDensity != null ? `${vr.powerDensity.toFixed(2)} W/m²` : "";
      return `<div class="variant-card ${i === activeVariantIndex ? "active" : ""}" data-idx="${i}">
        <div class="variant-title">
          <span>${vid}</span>
          <span class="badge ${pass ? "badge-pass" : "badge-fail"}" style="font-size:0.65rem;padding:0.1rem 0.35rem">${pass ? "PASS" : "FAIL"}</span>
        </div>
        <div class="variant-metrics">
          <div>Avg: <strong>${avg} lx</strong> · U0: <strong>${u0}</strong></div>
          ${pw || pd ? `<div>${pw} ${pd ? `(${pd})` : ""}</div>` : ""}
        </div>
      </div>`;
    })
    .join("");

  els.variantsList.querySelectorAll(".variant-card").forEach((card) => {
    card.addEventListener("click", () => {
      activeVariantIndex = Number(card.dataset.idx);
      result = multiVariantResults[activeVariantIndex];
      rebuildLayers();
      renderAll();
      renderVariantsShelf();
    });
  });
}

function renderAll() {
  if (!result) return;
  const layer = layers.find((l) => l.id === els.floorLayer.value) || layers[0];
  const values = layer ? layer.matrix.values : [];
  const kept = keptFloorIndices(result.floorPatches || []);
  const s = layerStats(values, kept);
  const ev = result.evaluation;

  updateComplianceBanner(ev, result.compliance);

  const z = result.floorPatches?.[0]?.center.z;
  const zBit = Number.isFinite(z) ? ` · work plane z=${z.toFixed(2)}` : "";
  const evBit = ev
    ? ` · EN12464 ${ev.nx}×${ev.ny} px=${Number(ev.spacingX ?? ev.spacing).toFixed(3)} py=${Number(ev.spacingY ?? ev.spacing).toFixed(3)} Emin ${Number(ev.minimum).toFixed(1)} Emax ${Number(ev.maximum).toFixed(1)} U0=${Number(ev.uniformity).toFixed(3)}`
    : "";
  const minBit = s.kept ? `min ${s.min.toFixed(1)}` : "min —";
  const maxBit = s.kept ? `max ${s.max.toFixed(1)}` : "max —";
  const fixCount = (result.fixtures || freeFixtures).length;
  els.stats.textContent = `${fixCount} fixtures · ${result.bounces ?? num("bounces")} bounces · ρw=${result.wallReflectance ?? num("wallReflectance")} ρf=${result.floorReflectance ?? num("floorReflectance")} ρc=${result.ceilingReflectance ?? num("ceilingReflectance")} · MF=${result.maintenanceFactor ?? num("maintenanceFactor")}${zBit}${evBit} · ${layer?.label || "Total"} ${minBit} / avg ${s.avg.toFixed(1)} / ${maxBit} lux`;

  drawPlan(layer?.matrix, s, kept);
  dialuxCompare(values);

  // Wall Elevation Cards
  els.walls.innerHTML = "";
  for (const [wid, patches] of Object.entries(result.wallPatches || {})) {
    const perFix = (result.directWallMatrices || {})[wid] || {};
    const total = sumMatrices(Object.values(perFix));
    const card = document.createElement("div");
    card.className = "wall-card";
    card.innerHTML = `<strong>${wid}</strong> · ${patches.length} patches · total direct<canvas width="320" height="160"></canvas>`;
    els.walls.appendChild(card);
    drawWall(card.querySelector("canvas"), patches, total.values);
  }

  // Floor / Ceiling Mini Cards
  if ((result.floorPatches || []).length) {
    const total = sumMatrices(Object.values(result.directFloorMatrices || {}));
    if (total.values.length) {
      const { avg } = stats(total.values);
      const card = document.createElement("div");
      card.className = "wall-card";
      card.innerHTML = `<strong>Floor (direct)</strong> · ${result.floorPatches.length} patches · avg ${avg.toFixed(1)} lux<canvas width="320" height="160"></canvas>`;
      els.walls.appendChild(card);
      drawPlanMini(card.querySelector("canvas"), result.floorPatches, total.values);
    }
  }

  const ceilingPatches = result.ceilingPatches || [];
  if (ceilingPatches.length) {
    const total = sumMatrices(Object.values(result.directCeilingMatrices || {}));
    if (total.values.length) {
      const { avg } = stats(total.values);
      const card = document.createElement("div");
      card.className = "wall-card";
      card.innerHTML = `<strong>Ceiling (direct)</strong> · ${ceilingPatches.length} patches · avg ${avg.toFixed(1)} lux<canvas width="320" height="160"></canvas>`;
      els.walls.appendChild(card);
      drawPlanMini(card.querySelector("canvas"), ceilingPatches, total.values);
    }
  }

  // Raw Matrices
  const blocks = [matrixTable("totalFloorIlluminance", result.totalFloorIlluminance, result.floorPatches || [])];
  for (const [fid, matrix] of Object.entries(result.directFloorMatrices || {})) {
    blocks.push(matrixTable(`directFloorMatrices[${fid}]`, matrix, result.floorPatches || []));
  }
  for (const [fid, matrix] of Object.entries(result.directCeilingMatrices || {})) {
    blocks.push(matrixTable(`directCeilingMatrices[${fid}]`, matrix, ceilingPatches));
  }
  for (const [wid, matrix] of Object.entries(result.indirectFloorMatrices || {})) {
    blocks.push(matrixTable(`indirectFloorMatrices[${wid}]`, matrix, result.floorPatches || []));
  }
  for (const [wid, byFix] of Object.entries(result.directWallMatrices || {})) {
    const patches = (result.wallPatches || {})[wid] || [];
    for (const [fid, matrix] of Object.entries(byFix)) {
      blocks.push(matrixTable(`directWallMatrices[${wid}][${fid}]`, matrix, patches));
    }
  }
  const fixturesList = result.fixtures || [];
  els.matrices.innerHTML = `<article class="matrix"><h3>fixtures (${fixturesList.length})</h3><table>
    <thead><tr><th>id</th><th>x</th><th>y</th><th>z</th><th>L×W×H</th><th>rot</th><th>tilt</th><th>aim</th></tr></thead>
    <tbody>${fixturesList
      .map(
        (f) =>
          `<tr><td>${f.id}</td><td>${f.position.x.toFixed(3)}</td><td>${f.position.y.toFixed(3)}</td><td>${f.position.z.toFixed(3)}</td><td>${f.length ?? 0}×${f.width ?? 0}×${f.height ?? 0}</td><td>${f.rotation}°</td><td>${f.tiltAngle ?? 0}°</td><td>(${f.aimDirection ? `${f.aimDirection.x.toFixed(2)}, ${f.aimDirection.y.toFixed(2)}, ${f.aimDirection.z.toFixed(2)}` : "—"})</td></tr>`
      )
      .join("")}</tbody></table></article>${blocks.join("")}`;
}

els.floorLayer.addEventListener("change", renderAll);
els.wallMargin.addEventListener("input", () => {
  if (result) renderAll();
});
["dxMinX", "dxMinY", "dxMaxX", "dxMaxY"].forEach((id) => {
  document.getElementById(id).addEventListener("input", () => {
    if (result) dialuxCompare((layers.find((l) => l.id === els.floorLayer.value) || layers[0]).matrix.values);
  });
});

function showStatus(text, kind) {
  els.status.hidden = false;
  els.status.className = `status ${kind}`;
  els.status.textContent = text;
}

function buildPayload() {
  const body = {
    polygon: vertices.map((v) => ({ x: v.x, y: v.y })),
    ceilingHeight: num("ceilingHeight") || 3.0,
    mountingHeight: num("mountingHeight") || 3.0,
    workPlaneHeight: num("workPlaneHeight"),
    wallReflectance: num("wallReflectance") || 0.5,
    floorReflectance: num("floorReflectance") || 0.2,
    ceilingReflectance: num("ceilingReflectance") || 0.7,
    maintenanceFactor: num("maintenanceFactor") || 0.8,
    bounces: parseInt(document.getElementById("bounces").value, 10),
    includeWallCeilingMatrices: document.getElementById("includeMatrices").checked,
  };
  const rot = optNum("luminaireRotation");
  if (rot != null) body.luminaireRotation = rot;
  const fz = optNum("floorZone");
  if (fz != null) body.floorZone = fz;
  const wz = optNum("wallZone");
  if (wz != null) body.wallZone = wz;

  // Compliance target
  const targetL = optNum("targetLux");
  const minU0 = optNum("minUniformity");
  if (targetL != null) {
    body.compliance = {
      targetLux: targetL,
      minUniformity: minU0 != null ? minU0 : 0.6,
    };
  }

  // Grid or Free Placements
  if (gridMode === "free") {
    body.fixtures = freeFixtures.map((f, i) => {
      const item = {
        id: f.id || `F${i + 1}`,
        x: Number(f.x),
        y: Number(f.y),
        rotation: Number(f.rotation || 0),
        tiltAngle: Number(f.tiltAngle || 0),
      };
      if (f.z != null) item.z = Number(f.z);
      if (f.variantId) item.variantId = f.variantId;
      if (f.iesRef) item.iesRef = f.iesRef;
      return item;
    });
    body.grid = null;
  } else if (gridMode === "count") {
    const elX = document.getElementById("countX") || document.getElementById("countNx");
    const elY = document.getElementById("countY") || document.getElementById("countNy");
    body.grid = {
      count: {
        countX: parseInt(elX ? elX.value : "1", 10) || 1,
        countY: parseInt(elY ? elY.value : "1", 10) || 1,
        offsetFraction: optNum("offsetFraction") != null ? Number(document.getElementById("offsetFraction").value) : 0.5,
      },
    };
  } else if (gridMode === "spacing") {
    const autoCenter = document.getElementById("spacingAutoCenter").checked;
    const spacingObj = {
      spacingX: num("spacingX"),
      spacingY: num("spacingY"),
      autoCenter: autoCenter,
    };
    if (!autoCenter) {
      const ox = optNum("spacingOffsetX");
      const oy = optNum("spacingOffsetY");
      if (ox != null) spacingObj.offsetX = ox;
      if (oy != null) spacingObj.offsetY = oy;
    }
    body.grid = { spacing: spacingObj };
  } else {
    // Axis mode
    body.grid = {
      x: { spacing: num("xSpacing"), offsetBeginning: num("xOffB"), offsetEnding: num("xOffE") },
      y: { spacing: num("ySpacing"), offsetBeginning: num("yOffB"), offsetEnding: num("yOffE") },
    };
  }

  // Default variant ID from catalog tab
  if (studySource === "variants") {
    const el = document.getElementById("variantId") || document.getElementById("variantIds");
    const v = el ? el.value.trim() : "";
    if (v) body.variantId = v;
  }

  return body;
}

async function iesBlob() {
  const file = document.getElementById("iesFile").files[0];
  if (file) return file;
  const res = await fetch("sample.ies");
  if (!res.ok) throw new Error("Could not load sample.ies");
  return new File([await res.blob()], "sample.ies", { type: "text/plain" });
}

async function executeCalculation() {
  const runBtn = document.getElementById("run");
  runBtn.disabled = true;
  els.btnRecalc.disabled = true;
  els.btnInspRecalc.disabled = true;
  showStatus("Calculating radiosity & illuminance…", "");

  try {
    const payload = buildPayload();
    let res;

    const hasVariants = payload.variantId || (payload.fixtures && payload.fixtures.some((f) => f.variantId));
    const iesInput = document.getElementById("iesFile");
    const hasUploadedIes = iesInput && iesInput.files && iesInput.files.length > 0;

    if (studySource === "variants" || (hasVariants && !hasUploadedIes)) {
      // Pure JSON calculation
      res = await fetch(`${API}/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      // Multipart upload with IES file
      const body = new FormData();
      body.append("payload", JSON.stringify(payload));
      body.append("iesFile", await iesBlob());
      res = await fetch(`${API}/calculate`, { method: "POST", body });
    }

    const data = await res.json();
    if (!res.ok) {
      const err = data.error || data;
      throw new Error(`${err.code || res.status}: ${err.message || JSON.stringify(data)}`);
    }

    if (data.results && data.results.length > 0) {
      multiVariantResults = data.results;
      activeVariantIndex = 0;
      result = data.results[0];
      renderVariantsShelf();
    } else {
      multiVariantResults = null;
      els.variantsShelf.hidden = true;
      result = data;
    }

    // Sync freeFixtures if in Free Mode or update positions from response
    if (gridMode === "free") {
      // keep current freeFixtures, update z, variantId, iesRef if returned
      if (result.fixtures && result.fixtures.length === freeFixtures.length) {
        result.fixtures.forEach((rf, i) => {
          if (freeFixtures[i].z == null) freeFixtures[i].z = rf.position.z;
          if (rf.variantId && !freeFixtures[i].variantId) freeFixtures[i].variantId = rf.variantId;
          if (rf.iesRef && !freeFixtures[i].iesRef) freeFixtures[i].iesRef = rf.iesRef;
        });
      }
    } else {
      // If was in grid mode, we can prepopulate free fixtures array
      if (result.fixtures) {
        freeFixtures = result.fixtures.map((f, i) => ({
          id: f.id || `F${i + 1}`,
          x: Number(f.position.x.toFixed(3)),
          y: Number(f.position.y.toFixed(3)),
          z: f.position.z != null ? Number(f.position.z.toFixed(3)) : null,
          rotation: f.rotation || 0,
          tiltAngle: f.tiltAngle || 0,
          variantId: f.variantId,
          iesRef: f.iesRef,
        }));
        renderFreeFixturesList();
      }
    }

    rebuildLayers();
    renderAll();
    showStatus(`Calculation Complete · Request ID: ${res.headers.get("X-Request-ID") || "OK"}`, "ok");
  } catch (err) {
    showStatus(String(err.message || err), "err");
  } finally {
    runBtn.disabled = false;
    els.btnRecalc.disabled = false;
    els.btnInspRecalc.disabled = false;
  }
}

els.form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await executeCalculation();
});

els.btnRecalc.addEventListener("click", executeCalculation);
els.btnInspRecalc.addEventListener("click", executeCalculation);

// Initialization
renderVerts();
updateInspector();
