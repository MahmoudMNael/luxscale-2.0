# LuxScale 2.0 — Lighting Calculation Engine

FastAPI service that computes room illuminance (direct + interreflected)
from a floor-plan polygon, a luminaire grid, and an IES LM-63 photometry file.

Architecture:

- **Python** — HTTP layer: controllers, schemas, repositories, services
  orchestration (`app/`).
- **C++ (`luxcore` extension, nanobind + OpenMP)** — physics only:
  direct I/N-sum, radiosity solver, IES sampling, mesh/interpolation math.
  Python automatically falls back to a pure-Python implementation if the
  extension is missing or `LUXCORE_ENABLED=0`.

## Prerequisites

- Python **>= 3.11**
- A C++17 compiler with OpenMP (`g++` on Linux is fine)
- CMake **>= 3.28** — system (`sudo apt install cmake`) or pip (`pip install cmake`)
- Python headers for your interpreter (needed to compile the extension):
  `sudo apt install python3-dev`, or see the no-sudo fallback in
  `scripts/build_luxcore.py`

## Fresh-pull install

```bash
git pull
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"     # installs deps AND builds the luxcore extension
```

Verify the C++ backend is active:

```bash
python -c "import luxcore; print(luxcore.backend(), luxcore.get_threads())"
# luxcore-cpp-nanobind-openmp <n>
```

If you only change C++ sources afterwards, rebuild in place (no reinstall):

```bash
python scripts/build_luxcore.py        # fast incremental build
python scripts/build_luxcore.py --clean  # full rebuild
```

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://127.0.0.1:8000/docs
- Demo UI: http://127.0.0.1:8000/demo/
- `POST /calculate` — multipart form with two parts:
  - `payload`: JSON room/grid description
  - `iesFile`: IES LM-63 photometry file

Example request:

```bash
curl -X POST http://127.0.0.1:8000/calculate \
  -F 'payload={"polygon":[{"x":0,"y":0},{"x":8,"y":0},{"x":8,"y":6},{"x":0,"y":6}],"height":3.0,"grid":{"x":{"spacing":2.0,"offsetBeginning":1.0,"offsetEnding":1.0},"y":{"spacing":2.0,"offsetBeginning":1.0,"offsetEnding":1.0}}}' \
  -F "iesFile=@demo/sample.ies"
```

## Tests & verification

```bash
pytest                        # full suite (C++ backend when built)
LUXCORE_ENABLED=0 pytest      # pure-Python fallback path
python scripts/check_luxcore_parity.py   # C++ vs Python parity + speedup report
```

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `LUXCORE_ENABLED` | `1` | `0` forces the pure-Python physics path |
| `LUXCORE_THREADS` | `0` (auto) | OpenMP thread count for `luxcore` |
| `OMP_NUM_THREADS` | — | Fallback thread count if `LUXCORE_THREADS` is unset |

`luxcore.set_threads(n)` / `luxcore.get_threads()` do the same at runtime.

## Large rooms & solver scaling

The interreflection solver builds a dense n² transfer matrix, so the
physics mesh is capped at `MAX_SOLVER_PATCHES = 6000` sources
(`app/app_settings.py`):

- Rooms up to **10×10 m** keep full **0.3 m** resolution (~3,700 patches,
  bit-identical to before).
- Larger rooms (e.g. a 100×60 m hall, which would otherwise attempt a
  ~232 GiB matrix) **adaptively coarsen** just enough to stay under the cap
  (~1.7 m cell for 100×60 m) and complete in seconds.

The response flags this via `solverCell` (effective cell used) and
`solverDegraded` (`true` when coarsened). Evaluation grids are unaffected —
they already follow EN 12464 spacing — so reported averages stay on the
standard grid; only the interreflection resolution degrades, which is the
correct tradeoff at hall scale.

## Troubleshooting

- `import luxcore` fails → the extension wasn't built: install `cmake` and
  `python3-dev`, then `pip install -e ".[dev]"` again (or run
  `python scripts/build_luxcore.py` for the error log).
- `Could NOT find Python ... Development.Module` at configure time → missing
  Python headers; install `python3-dev` (see fallback in
  `scripts/build_luxcore.py` if you have no sudo).
- Wrong results suspected → run `scripts/check_luxcore_parity.py`; it asserts
  C++ vs Python agreement (~1e-16) and prints per-case speedups.
