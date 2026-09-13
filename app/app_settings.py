"""Process-wide constants. Imported by calculate_service and logging setup only."""

WALL_REFLECTANCE_FACTOR = 0.5  # walls only; floor/ceiling never re-emit
NUM_BOUNCES = 3  # wall interreflection bounces; 0 = direct only, 1 = legacy single bounce
MAINTENANCE_FACTOR = 0.8
WORK_PLANE_HEIGHT = 0.0
FLOOR_BORDER = 0.25
PATCH_SIZE = 0.1  # wall radiosity mesh only; floor uses EN 12464 spacing
LOG_LEVEL = "INFO"
