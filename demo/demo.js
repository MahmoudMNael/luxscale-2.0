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
};

let vertices = PRESETS.rect.map(([x, y]) => ({ x, y }));
let result = null;
let layers = [];

function num(id) {
  return Number(document.getElementById(id).value);
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

function previewFixtures(pts) {
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  const gx = { spacing: num("xSpacing"), offB: num("xOffB"), offE: num("xOffE") };
  const gy = { spacing: num("ySpacing"), offB: num("yOffB"), offE: num("yOffE") };
  const fixtures = [];
  let n = 1;
  for (const y of axisPoints(ymin, ymax, gy.spacing, gy.offB, gy.offE)) {
    for (const x of axisPoints(xmin, xmax, gx.spacing, gx.offB, gx.offE)) {
      if (!pointInPolygon({ x, y }, pts)) continue;
      fixtures.push({ id: `F${n}`, x, y });
      n += 1;
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

  ctx.strokeStyle = "#2c3344";
  ctx.lineWidth = 1;
  const origin = to(b.xmin, b.ymin);
  const far = to(b.xmax, b.ymax);
  ctx.strokeRect(origin.x, far.y, far.x - origin.x, origin.y - far.y);

  ctx.fillStyle = "rgba(61, 139, 253, 0.18)";
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
    ctx.font = "11px sans-serif";
    ctx.fillText(String(i + 1), p.x + 6, p.y - 6);
  });

  fixtures.forEach((f) => {
    const p = to(f.x, f.y);
    ctx.fillStyle = "#e0a106";
    ctx.beginPath();
    ctx.moveTo(p.x, p.y - 5);
    ctx.lineTo(p.x + 5, p.y);
    ctx.lineTo(p.x, p.y + 5);
    ctx.lineTo(p.x - 5, p.y);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#fff7cc";
    ctx.font = "10px sans-serif";
    ctx.fillText(f.id, p.x + 6, p.y + 3);
  });

  els.polyMeta.textContent = `${pts.length} verts · ${fixtures.length} fixtures · bbox ${b.w.toFixed(2)}×${b.h.toFixed(2)} m · area ≈ ${area.toFixed(2)} m²`;
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
  vertices.push({ x: last.x + 1, y: last.y });
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
els.form.addEventListener("input", (ev) => {
  if (ev.target.closest("#verts")) return;
  if (ev.target.type === "number") drawPolygonPreview();
});

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

function stats(values) {
  if (!values.length) return { min: 0, max: 0, avg: 0 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return { min, max, avg };
}

function drawPlan(layer) {
  const canvas = els.plan;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const pts = result.floorPatches.map((p) => p.center);
  const extra = result.fixtures.flatMap((f) => [f.position, ...(f.corners || []), ...(f.elements || [])]);
  const b = boundsOf([...pts, ...extra, ...vertices]);
  const to = mapper(canvas, b);
  const { min, max } = stats(layer.values);
  els.legMin.textContent = min.toFixed(1);
  els.legMax.textContent = max.toFixed(1);
  const span = max - min || 1;

  result.floorPatches.forEach((p, i) => {
    const half = p.size / 2;
    const a = to(p.center.x - half, p.center.y - half);
    const c = to(p.center.x + half, p.center.y + half);
    ctx.fillStyle = luxColor((layer.values[i] - min) / span);
    ctx.fillRect(a.x, c.y, c.x - a.x, a.y - c.y);
  });

  ctx.strokeStyle = "#d5dced";
  ctx.lineWidth = 2;
  ctx.beginPath();
  vertices.forEach((v, i) => {
    const p = to(v.x, v.y);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.stroke();

  result.fixtures.forEach((f) => {
    const corners = f.corners || [];
    const degenerate = !(f.length > 0 || f.width > 0);
    if (corners.length >= 4 && !degenerate) {
      ctx.beginPath();
      corners.forEach((c, i) => {
        const p = to(c.x, c.y);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      ctx.fillStyle = "rgba(224, 161, 6, 0.35)";
      ctx.strokeStyle = "#e0a106";
      ctx.lineWidth = 1.5;
      ctx.fill();
      ctx.stroke();
    }
    (f.elements || []).forEach((e) => {
      const p = to(e.x, e.y);
      ctx.fillStyle = "#e0a106";
      ctx.beginPath();
      ctx.arc(p.x, p.y, degenerate ? 4 : 2, 0, Math.PI * 2);
      ctx.fill();
    });
    const p = to(f.position.x, f.position.y);
    ctx.fillStyle = "#fff7cc";
    ctx.font = "11px sans-serif";
    ctx.fillText(
      `${f.id}  z=${f.position.z.toFixed(3)}  ${Number(f.length).toFixed(2)}×${Number(f.width).toFixed(2)}`,
      p.x + 8,
      p.y - 6
    );
  });
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

function matrixTable(title, matrix, patches) {
  const rows = matrix.values
    .map((v, i) => {
      const p = patches[i];
      const loc = p ? `${p.id} (${p.center.x.toFixed(2)}, ${p.center.y.toFixed(2)}, ${p.center.z.toFixed(2)})` : i;
      return `<tr><td>${loc}</td><td>${v.toFixed(3)}</td></tr>`;
    })
    .join("");
  return `<article class="matrix">
    <h3>${title}</h3>
    <div class="meta">${JSON.stringify(matrix.metadata)}</div>
    <table><thead><tr><th>patch</th><th>lux</th></tr></thead><tbody>${rows}</tbody></table>
  </article>`;
}

function sumMatrices(matrices) {
  if (!matrices.length) return { values: [], metadata: { kind: "sum-client" } };
  const values = matrices[0].values.map((_, i) => matrices.reduce((acc, m) => acc + m.values[i], 0));
  return { values, metadata: { kind: "sum-client" } };
}

function rebuildLayers() {
  layers = [{ id: "total", label: "Total floor", matrix: result.totalFloorIlluminance, patches: result.floorPatches }];
  for (const [fid, matrix] of Object.entries(result.directFloorMatrices)) {
    layers.push({ id: `df-${fid}`, label: `Direct floor · ${fid}`, matrix, patches: result.floorPatches });
  }
  for (const [wid, matrix] of Object.entries(result.indirectFloorMatrices)) {
    layers.push({ id: `if-${wid}`, label: `Indirect floor · ${wid}`, matrix, patches: result.floorPatches });
  }
  els.floorLayer.innerHTML = layers.map((l) => `<option value="${l.id}">${l.label}</option>`).join("");
  els.floorLayer.disabled = false;
}

function renderAll() {
  const layer = layers.find((l) => l.id === els.floorLayer.value) || layers[0];
  const s = stats(layer.matrix.values);
  els.stats.textContent = `${result.fixtures.length} fixtures · ${result.floorPatches.length} floor patches · ${layer.label} min ${s.min.toFixed(1)} / avg ${s.avg.toFixed(1)} / max ${s.max.toFixed(1)} lux`;
  drawPlan(layer.matrix);

  els.walls.innerHTML = "";
  for (const [wid, patches] of Object.entries(result.wallPatches)) {
    const perFix = result.directWallMatrices[wid] || {};
    const total = sumMatrices(Object.values(perFix));
    const card = document.createElement("div");
    card.className = "wall-card";
    card.innerHTML = `<strong>${wid}</strong> · ${patches.length} patches · total direct (sum of fixtures)<canvas width="320" height="160"></canvas>`;
    els.walls.appendChild(card);
    drawWall(card.querySelector("canvas"), patches, total.values);
  }

  const blocks = [matrixTable("totalFloorIlluminance", result.totalFloorIlluminance, result.floorPatches)];
  for (const [fid, matrix] of Object.entries(result.directFloorMatrices)) {
    blocks.push(matrixTable(`directFloorMatrices[${fid}]`, matrix, result.floorPatches));
  }
  for (const [wid, matrix] of Object.entries(result.indirectFloorMatrices)) {
    blocks.push(matrixTable(`indirectFloorMatrices[${wid}]`, matrix, result.floorPatches));
  }
  for (const [wid, byFix] of Object.entries(result.directWallMatrices)) {
    const patches = result.wallPatches[wid] || [];
    for (const [fid, matrix] of Object.entries(byFix)) {
      blocks.push(matrixTable(`directWallMatrices[${wid}][${fid}]`, matrix, patches));
    }
  }
  els.matrices.innerHTML = `<article class="matrix"><h3>fixtures</h3><table>
    <thead><tr><th>id</th><th>x</th><th>y</th><th>z</th><th>L×W×H</th><th>elements</th><th>aim</th><th>rot</th></tr></thead>
    <tbody>${result.fixtures
      .map(
        (f) =>
          `<tr><td>${f.id}</td><td>${f.position.x}</td><td>${f.position.y}</td><td>${f.position.z}</td><td>${f.length}×${f.width}×${f.height}</td><td>${(f.elements || []).length}</td><td>(${f.aimDirection.x}, ${f.aimDirection.y}, ${f.aimDirection.z})</td><td>${f.rotation}</td></tr>`
      )
      .join("")}</tbody></table></article>${blocks.join("")}`;
}

els.floorLayer.addEventListener("change", renderAll);

function showStatus(text, kind) {
  els.status.hidden = false;
  els.status.className = `status ${kind}`;
  els.status.textContent = text;
}

function payload() {
  return {
    polygon: vertices.map((v) => ({ x: v.x, y: v.y })),
    height: num("height"),
    grid: {
      x: { spacing: num("xSpacing"), offsetBeginning: num("xOffB"), offsetEnding: num("xOffE") },
      y: { spacing: num("ySpacing"), offsetBeginning: num("yOffB"), offsetEnding: num("yOffE") },
    },
  };
}

async function iesBlob() {
  const file = document.getElementById("iesFile").files[0];
  if (file) return file;
  const res = await fetch("sample.ies");
  if (!res.ok) throw new Error("Could not load sample.ies");
  return new File([await res.blob()], "sample.ies", { type: "text/plain" });
}

els.form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const run = document.getElementById("run");
  run.disabled = true;
  showStatus("Calculating…", "");
  try {
    const body = new FormData();
    body.append("payload", JSON.stringify(payload()));
    body.append("iesFile", await iesBlob());
    const res = await fetch(`${API}/calculate`, { method: "POST", body });
    const data = await res.json();
    if (!res.ok) {
      const err = data.error || data;
      throw new Error(`${err.code || res.status}: ${err.message || JSON.stringify(data)}`);
    }
    result = data;
    rebuildLayers();
    renderAll();
    showStatus(`OK · ${res.headers.get("X-Request-ID") || ""}`, "ok");
  } catch (err) {
    showStatus(String(err.message || err), "err");
  } finally {
    run.disabled = false;
  }
});

renderVerts();
