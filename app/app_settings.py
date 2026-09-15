"""Process-wide constants. Imported by calculate_service and logging setup only."""

WALL_REFLECTANCE_FACTOR = 0.5
FLOOR_REFLECTANCE_FACTOR = 0.2
CEILING_REFLECTANCE_FACTOR = 0.7
C0_ORIENTATION_OFFSET_DEG = 90.0  # added to photometric phi; aligns IES C0 with DIALux for LDT-converted files
BOUNCE_TOL_FLOOR_LUX = 0.1  # converge bounces when max floor change < this (lux); ~0.03% of typical levels
MAX_BOUNCES = 25  # safety cap on converged interreflection iterations (each bounce is ~0.2s)
MAINTENANCE_FACTOR = 0.8
WORK_PLANE_HEIGHT = 0.0
FLOOR_BORDER = 0.0
PATCH_SIZE = 0.1  # wall radiosity mesh; floor/ceiling sources use sizes below
FLOOR_RADIOSITY_SIZE = 0.1  # fine floor source mesh for interreflection (EN12464 grid stays report-only)
CEILING_RADIOSITY_SIZE = 0.1  # fine ceiling source mesh for interreflection
LOG_LEVEL = "INFO"
