"""Process-wide constants. Imported by calculate_service and logging setup only."""

WALL_REFLECTANCE_FACTOR = 0.5
FLOOR_REFLECTANCE_FACTOR = 0.2
CEILING_REFLECTANCE_FACTOR = 0.7
C0_ORIENTATION_OFFSET_DEG = 0.0  # native IES C0; Relux parity (no LDT rotation)
NUM_BOUNCES = 3  # interreflection bounces; 0 = direct only, 1 = single bounce.
# Calibrated to the Relux reference room (4x3x3, RC132V): 3 matches Relux
# avg/max within ~0.5% (5 overshoots avg ~2.5% against Relux's truncation).
# Raise for high-reflectance rooms needing deeper convergence.
MAINTENANCE_FACTOR = 0.8
WORK_PLANE_HEIGHT = 0.0
FLOOR_BORDER = 0.5
WALL_MIN_DIMENSION = 1.0
PATCH_SIZE = 0.1  # legacy wall radiosity mesh; evaluation grids use EN 12464 spacing
SOLVER_CELL = 0.3
MAX_SOLVER_PATCHES = 6000  # radiosity solver-mesh cap (all solver sources).
# A 10x10x3 m room at SOLVER_CELL needs ~3,700 patches (F ~= 110 MB); 6000
# keeps any 10x10 m room up to ~7 m ceilings at full 0.3 m resolution
# (F <= ~290 MB). Larger rooms adaptively coarsen (patches ~ 1/cell^2) so the
# dense F matrix (n^2 x 8 bytes) can never blow up memory.
LOG_LEVEL = "INFO"
