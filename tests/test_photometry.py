from pathlib import Path

import pytest

from app.domain.exceptions import IesParseError, NoFixturesError
from app.domain.models import Fixture, Patch
from app.services.direct_illuminance_service import compute_direct_illuminance
from app.services.fixture_service import generate_fixture_grid, luminous_opening
from app.services.geometry_service import define_room
from app.services.ies_service import get_candela, load_ies
from app.schemas.grid import AxisGrid, GridInput
from tests.ies_sample import SAMPLE_IES, ies_with

_DEMO_IES = Path(__file__).resolve().parents[1] / "demo" / "sample.ies"


def _downlight(profile, z=3.0) -> Fixture:
    return Fixture(
        id="F1",
        position=(0.0, 0.0, z),
        aim_direction=(0.0, 0.0, -1.0),
        rotation=0.0,
        ies_profile=profile,
    )


def _nadir_patch() -> Patch:
    return Patch(
        id="p",
        surface_type="floor",
        parent_id="floor",
        center=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        area=1.0,
        size=1.0,
    )


def test_load_type_c_and_interpolate():
    profile = load_ies(SAMPLE_IES)
    assert profile.multiplier == 1.0
    nadir = get_candela(profile, 0, 0)
    mid = get_candela(profile, 45, 90)
    assert nadir == 1000
    assert 700 == mid or abs(mid - 700) < 1e-9


def test_ballast_factor_scales_candela():
    full = load_ies(SAMPLE_IES)
    half = load_ies(ies_with(ballast=0.5))
    assert get_candela(half, 0, 0) == pytest.approx(get_candela(full, 0, 0) * 0.5)


def test_feet_opening_converted_to_metres():
    profile = load_ies(ies_with(units=1, width=2, length=2))
    assert profile.width == pytest.approx(0.6096)
    assert profile.length == pytest.approx(0.6096)


def test_reject_tilt_include():
    try:
        load_ies("TILT=INCLUDE\n1 1 1 1 1 1 2 0 0 0\n1 1 1\n0\n0\n1\n")
    except IesParseError as exc:
        assert "TILT=NONE" in exc.message
    else:
        raise AssertionError("expected IesParseError")


def test_fixture_grid_and_empty():
    room = define_room([(0, 0), (4, 0), (4, 4), (0, 4)], 3)
    ies = load_ies(SAMPLE_IES)
    grid = GridInput(
        x=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
        y=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
    )
    fixtures = generate_fixture_grid(room, grid, room.height, ies)
    assert fixtures
    assert all(f.position[2] == 3 for f in fixtures)
    hung = load_ies(ies_with(height=0.2))
    dropped = generate_fixture_grid(room, grid, room.height, hung)
    assert all(f.position[2] == pytest.approx(2.9) for f in dropped)
    miss = GridInput(
        x=AxisGrid(spacing=10, offsetBeginning=9, offsetEnding=9),
        y=AxisGrid(spacing=10, offsetBeginning=9, offsetEnding=9),
    )
    try:
        generate_fixture_grid(room, miss, room.height, ies)
    except NoFixturesError:
        return
    raise AssertionError("expected NoFixturesError")


def test_zero_opening_is_one_element_at_centre():
    corners, elements = luminous_opening(_downlight(load_ies(SAMPLE_IES)))
    assert len(corners) == 4
    assert elements == [(0.0, 0.0, 3.0)]
    assert compute_direct_illuminance(_downlight(load_ies(SAMPLE_IES)), _nadir_patch()) == pytest.approx(1000 / 9)


def test_panel_opening_corners_and_elements():
    profile = load_ies(ies_with(width=0.55, length=0.55))
    corners, elements = luminous_opening(_downlight(profile))
    assert len(corners) == 4
    assert len(elements) == 9
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    assert max(xs) - min(xs) == pytest.approx(0.55)
    assert max(ys) - min(ys) == pytest.approx(0.55)
    assert sum(e[0] for e in elements) / 9 == pytest.approx(0.0)
    assert sum(e[1] for e in elements) / 9 == pytest.approx(0.0)


def test_area_source_nadir_below_point_source():
    point = _downlight(load_ies(SAMPLE_IES))
    panel = _downlight(load_ies(ies_with(width=0.55, length=0.55)))
    e_point = compute_direct_illuminance(point, _nadir_patch())
    e_panel = compute_direct_illuminance(panel, _nadir_patch())
    assert e_panel < e_point
    assert e_panel > 0


def test_demo_sample_ies_opening():
    profile = load_ies(_DEMO_IES.read_text())
    assert profile.width == pytest.approx(0.55)
    assert profile.length == pytest.approx(0.55)
    assert profile.height == pytest.approx(0.011)
    assert profile.ballast_factor == pytest.approx(1.0)
    _, elements = luminous_opening(_downlight(profile, z=3.0 - profile.height / 2.0))
    assert len(elements) == 9
