"""Process-wide constants. Imported by calculate_service and logging setup only."""

WALL_REFLECTANCE_FACTOR = 0.5
FLOOR_REFLECTANCE_FACTOR = 0.2
CEILING_REFLECTANCE_FACTOR = 0.7
C0_ORIENTATION_OFFSET_DEG = 0.0  # native IES C0; Relux parity (no LDT rotation)
NUM_BOUNCES = 5  # wall interreflection bounces; 0 = direct only, 1 = legacy single bounce
MAINTENANCE_FACTOR = 0.8
WORK_PLANE_HEIGHT = 0.0
FLOOR_BORDER = 0.5
WALL_MIN_DIMENSION = 1.0
PATCH_SIZE = 0.1  # legacy wall radiosity mesh; evaluation grids use EN 12464 spacing
SOLVER_CELL = 0.3  # Relux-like independent radiosity mesh (fixed raster, all surfaces reflect)
LOG_LEVEL = "INFO"
