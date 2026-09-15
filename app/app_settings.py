"""Process-wide constants. Imported by calculate_service and logging setup only."""

WALL_REFLECTANCE_FACTOR = 0.5
FLOOR_REFLECTANCE_FACTOR = 0.2
CEILING_REFLECTANCE_FACTOR = 0.7
C0_ORIENTATION_OFFSET_DEG = 90.0  # added to photometric phi; aligns IES C0 with DIALux for LDT-converted files
NUM_BOUNCES = 5  # wall interreflection bounces; 0 = direct only, 1 = legacy single bounce
MAINTENANCE_FACTOR = 0.8
WORK_PLANE_HEIGHT = 0.0
FLOOR_BORDER = 0.0
PATCH_SIZE = 0.1  # wall radiosity mesh only; floor uses EN 12464 spacing
LOG_LEVEL = "INFO"
