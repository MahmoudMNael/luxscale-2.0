"""C++/Python parity for the luxcore physics backend.

Each test computes the same quantity through the pure-Python service
functions (bridge disabled via mock) and through the C++ extension
(via the OOP bridge) and asserts near-bitwise agreement. Skipped when
the extension is unavailable so checkouts without a compiler still pass.
"""

from unittest.mock import PropertyMock, patch

import pytest

from app.services._luxcore_bridge import LuxCoreRuntime
from tests.ies_sample import SAMPLE_IES

needs_luxcore = pytest.mark.skipif(
    not LuxCoreRuntime().is_available(), reason="luxcore extension not built")


def _profile():
    from app.services.ies_service import load_ies

    return load_ies(SAMPLE_IES)


@needs_luxcore
def test_candela_matches_python():
    import luxcore
    from app.services.ies_service import get_candela

    profile = _profile()
    cpp = luxcore.IesProfile.load(SAMPLE_IES)
    for th, ph in [(0, 0), (10, 30), (45, 90), (70, 180), (89.9, 270)]:
        assert cpp.sample(th, ph) == pytest.approx(get_candela(profile, th, ph), rel=1e-12)


@needs_luxcore
def test_luminous_opening_matches_python():
    import numpy as np

    import luxcore
    from app.domain.models import Fixture
    from app.services.fixture_service import luminous_opening

    profile = _profile()
    fix = Fixture(id="F1", position=(1.0, 2.0, 3.0), aim_direction=(0.0, 0.0, -1.0),
                  rotation=30.0, ies_profile=profile)
    with patch.object(LuxCoreRuntime, "module", new_callable=PropertyMock,
                      return_value=None):
        corners, elements = luminous_opening(fix)
    cc = np.asarray(luxcore.luminous_corners([1.0, 2.0, 3.0], 30.0, profile.length,
                                             profile.width)).tolist()
    ee = np.asarray(luxcore.luminous_elements([1.0, 2.0, 3.0], 30.0, profile.length,
                                              profile.width)).tolist()

    def flat(m):
        return [v for row in m for v in row]

    assert flat([list(c) for c in corners]) == pytest.approx(flat(cc), rel=1e-12)
    assert flat([list(e) for e in elements]) == pytest.approx(flat(ee), rel=1e-12)


@needs_luxcore
def test_direct_matrix_matches_python_convex_and_concave():
    from app.domain.models import Fixture, Patch
    from app.services.direct_illuminance_service import compute_direct_matrix
    from app.services._luxcore_bridge import LuxCoreDirectEngine

    profile = _profile()
    fix = Fixture(id="F1", position=(1.0, 1.0, 3.0), aim_direction=(0.0, 0.0, -1.0),
                  rotation=0.0, ies_profile=profile)
    patches = [
        Patch(id=f"p{i}", surface_type="floor", parent_id="floor",
              center=(0.5 * i, 0.25 * i, 0.0), normal=(0.0, 0.0, 1.0), area=0.25, size=0.5)
        for i in range(6)
    ]
    for poly in ([(0, 0), (4, 0), (4, 4), (0, 4)],
                 [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]):
        cpp_vals = LuxCoreDirectEngine().compute_values(fix, patches, room_polygon=list(poly))
        # Pure-Python reference (bridge disabled via mock).
        with patch.object(LuxCoreRuntime, "module", new_callable=PropertyMock,
                          return_value=None):
            # Clear cached C++ handles so nothing leaks across the mock.
            from app.services import _luxcore_bridge as bridge_mod

            bridge_mod.IesHandleCache.clear()
            ref = compute_direct_matrix(fix, patches, "floor", patch_size=0.5,
                                        room_polygon=list(poly)).values
        assert cpp_vals == pytest.approx(ref, rel=1e-9, abs=1e-12)


@needs_luxcore
def test_indirect_matches_python_two_wall_room():
    from app.domain.models import Patch
    from app.services.indirect_illuminance_service import (
        compute_indirect_per_target_per_origin,
    )
    from app.services._luxcore_bridge import LuxCoreRadiositySolver

    src = [
        Patch(id="w0", surface_type="wall", parent_id="W1", center=(0.0, 0.0, 1.0),
              normal=(1.0, 0.0, 0.0), area=1.0, size=1.0),
        Patch(id="w1", surface_type="wall", parent_id="W2", center=(2.0, 0.0, 1.0),
              normal=(-1.0, 0.0, 0.0), area=1.0, size=1.0),
    ]
    floor = [Patch(id="f0", surface_type="floor", parent_id="floor", center=(1.0, 1.0, 0.0),
                   normal=(0.0, 0.0, 1.0), area=1.0, size=1.0)]
    seeds = {"W1": [1000.0, 0.0], "W2": [0.0, 500.0]}
    poly = [(0, 0), (2, 0), (2, 2), (0, 2)]
    cpp = LuxCoreRadiositySolver().solve(src, seeds, {"floor": floor}, wall_reflectance=0.5,
                                         num_bounces=3, room_polygon=list(poly),
                                         floor_reflectance=0.2, ceiling_reflectance=0.7)
    with patch.object(LuxCoreRuntime, "module", new_callable=PropertyMock,
                      return_value=None):
        ref = compute_indirect_per_target_per_origin(
            src, seeds, {"floor": floor}, 0.5, 3, list(poly),
            floor_reflectance=0.2, ceiling_reflectance=0.7)
    for oid in seeds:
        assert cpp["floor"][oid] == pytest.approx(ref["floor"][oid], rel=1e-9, abs=1e-12)


@needs_luxcore
def test_apply_weights_matches_python():
    from app.services.geometry_service import apply_interp_weights
    from app.services._luxcore_bridge import LuxCoreGeometry

    weights = ([0, 2, 3], [0, 2, 1], [0.5, 0.5, 1.0], 2, 3)
    vals = [10.0, 20.0, 30.0]
    assert LuxCoreGeometry().apply_weights(vals, weights) == pytest.approx(
        apply_interp_weights(vals, weights))
