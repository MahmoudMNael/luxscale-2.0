from app.domain.exceptions import IesParseError, NoFixturesError
from app.services.fixture_service import generate_fixture_grid
from app.services.geometry_service import define_room
from app.services.ies_service import get_candela, load_ies
from app.schemas.grid import AxisGrid, GridInput
from tests.ies_sample import SAMPLE_IES


def test_load_type_c_and_interpolate():
    profile = load_ies(SAMPLE_IES)
    assert profile.multiplier == 1.0
    nadir = get_candela(profile, 0, 0)
    mid = get_candela(profile, 45, 90)
    assert nadir == 1000
    assert 700 == mid or abs(mid - 700) < 1e-9


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
    miss = GridInput(
        x=AxisGrid(spacing=10, offsetBeginning=9, offsetEnding=9),
        y=AxisGrid(spacing=10, offsetBeginning=9, offsetEnding=9),
    )
    try:
        generate_fixture_grid(room, miss, room.height, ies)
    except NoFixturesError:
        return
    raise AssertionError("expected NoFixturesError")
