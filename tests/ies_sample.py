"""Type-C IES with one horizontal angle (rotationally symmetric)."""

SAMPLE_IES = """IESNA:LM-63-2002
[TEST] luxscale synthetic
TILT=NONE
1 1000 1 5 1 1 2 0 0 0
1 1 1
0 45 90 135 180
0
1000 700 300 40 0
"""


def ies_with(*, ballast=1.0, blf=1.0, units=2, width=0.0, length=0.0, height=0.0) -> str:
    return (
        "IESNA:LM-63-2002\nTILT=NONE\n"
        f"1 1000 1 5 1 1 {units} {width} {length} {height}\n"
        f"{ballast} {blf} 1\n"
        "0 45 90 135 180\n"
        "0\n"
        "1000 700 300 40 0\n"
    )
