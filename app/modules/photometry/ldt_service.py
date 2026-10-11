from __future__ import annotations

from app.domain.exceptions import IesParseError
from app.domain.models import IESProfile


def load_ldt(ldt_text: str) -> IESProfile:
    """Parses standard EULUMDAT (.ldt) photometric format into an IESProfile."""
    if not ldt_text.strip():
        raise IesParseError("LDT file is empty.")

    lines = [line.strip() for line in ldt_text.splitlines() if line.strip() != ""]
    if len(lines) < 26:
        raise IesParseError("LDT file header is incomplete.")

    try:
        mc = int(float(lines[3]))
        ng = int(float(lines[5]))

        length_m = max(0.01, float(lines[12]) / 1000.0)
        width_m = max(0.01, float(lines[13]) / 1000.0)
        height_m = max(0.01, float(lines[14]) / 1000.0)

        conversion_factor = float(lines[23])
        if conversion_factor <= 0:
            conversion_factor = 1.0

        n_lamp_sets = int(float(lines[25]))

        # Collect all remaining tokens across remaining lines
        tokens: list[str] = []
        for line in lines[26:]:
            for part in line.replace(",", " ").split():
                if part.strip():
                    tokens.append(part.strip())

        tok_idx = 0
        total_lumens = 0.0
        for _ in range(n_lamp_sets):
            n_lamps = int(float(tokens[tok_idx]))
            tok_idx += 1  # lamp count
            tok_idx += 1  # lamp type
            lumens = float(tokens[tok_idx])
            tok_idx += 1  # flux
            total_lumens += n_lamps * lumens
            tok_idx += 1  # color appearance
            tok_idx += 1  # CRI
            tok_idx += 1  # wattage

        if total_lumens <= 0:
            total_lumens = 1000.0

        # Skip 10 direct ratios for room indices
        tok_idx += 10

        # Read C-planes (mc values)
        c_angles: list[float] = []
        for _ in range(mc):
            c_angles.append(float(tokens[tok_idx]))
            tok_idx += 1

        # Read G-angles (ng values)
        g_angles: list[float] = []
        for _ in range(ng):
            g_angles.append(float(tokens[tok_idx]))
            tok_idx += 1

        # Read intensity values (mc * ng values in cd/klm)
        candela_table = [[0.0] * mc for _ in range(ng)]
        lumen_multiplier = (total_lumens / 1000.0) * conversion_factor

        for h in range(mc):
            for v in range(ng):
                cd = float(tokens[tok_idx]) * lumen_multiplier
                candela_table[v][h] = cd
                tok_idx += 1

        return IESProfile(
            vertical_angles=g_angles,
            horizontal_angles=c_angles,
            candela_table=candela_table,
            multiplier=1.0,
            ballast_factor=1.0,
            ballast_lamp_factor=1.0,
            flux_scale=1.0,
            width=width_m,
            length=length_m,
            height=height_m,
        )
    except (IndexError, ValueError) as exc:
        raise IesParseError(f"Failed to parse LDT file: {exc}") from exc
