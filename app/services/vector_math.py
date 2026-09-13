from __future__ import annotations

import math

from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

EPS = 1e-9
Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def cross_z(a: Vec2, b: Vec2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def norm(a: tuple[float, ...]) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3) -> Vec3:
    n = norm(a)
    if n < EPS:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def angle_deg(a: Vec3, b: Vec3) -> float:
    na, nb = norm(a), norm(b)
    if na < EPS or nb < EPS:
        return 90.0
    c = max(-1.0, min(1.0, dot(a, b) / (na * nb)))
    return math.degrees(math.acos(c))


def wrap_deg(phi: float) -> float:
    return phi % 360.0


def en12464_spacing(d: float) -> float:
    """EN 12464-1 maximum calculation-grid spacing: p = 0.2 × 5^log10(d)."""
    if d <= EPS:
        return 0.0
    return 0.2 * 5.0 ** math.log10(d)


def _room(polygon: list[Vec2]) -> Polygon:
    poly = Polygon(polygon)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def signed_area(polygon: list[Vec2]) -> float:
    poly = _room(polygon)
    if poly.is_empty:
        return 0.0
    exterior = poly.exterior
    if exterior is None:
        return 0.0
    return poly.area if exterior.is_ccw else -poly.area


def centroid_2d(polygon: list[Vec2]) -> Vec2:
    c = _room(polygon).centroid
    return (float(c.x), float(c.y))


def polygon_area(polygon: list[Vec2]) -> float:
    return float(_room(polygon).area)


def point_in_polygon(point: Vec2, polygon: list[Vec2]) -> bool:
    return bool(_room(polygon).covers(Point(point)))


def _ring(poly: Polygon) -> list[Vec2]:
    coords = [(float(x), float(y)) for x, y, *_ in poly.exterior.coords]
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def _rings(geom: BaseGeometry) -> list[list[Vec2]]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        ring = _ring(geom)
        return [ring] if len(ring) >= 3 else []
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        out: list[list[Vec2]] = []
        for part in geom.geoms:
            out.extend(_rings(part))
        return out
    return []


def inset_rings(polygon: list[Vec2], border: float) -> list[list[Vec2]]:
    """Interior offset of the room polygon. Empty if the inset collapses."""
    if border <= EPS:
        ring = _close_ring(polygon)
        return [ring] if len(ring) >= 3 else []
    return _rings(_room(polygon).buffer(-border, join_style=2, mitre_limit=5.0))


def _close_ring(polygon: list[Vec2]) -> list[Vec2]:
    if len(polygon) >= 2 and polygon[0] == polygon[-1]:
        return list(polygon[:-1])
    return list(polygon)


def clip_rect_to_polygon(rect: tuple[float, float, float, float], polygon: list[Vec2]) -> list[list[Vec2]]:
    """Return intersection rings of an axis-aligned cell with the room polygon."""
    xmin, ymin, xmax, ymax = rect
    if xmax - xmin < EPS or ymax - ymin < EPS:
        return []
    return _rings(box(xmin, ymin, xmax, ymax).intersection(_room(polygon)))
