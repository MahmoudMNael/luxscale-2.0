#include "luxcore/vector_math.h"

#include <cmath>

namespace luxcore {

double VectorMath::angle_deg(const Vec3& a, const Vec3& b) {
    const double na = norm(a);
    const double nb = norm(b);
    if (na < kEps || nb < kEps) return 90.0;
    double c = dot(a, b) / (na * nb);
    if (c > 1.0) c = 1.0;
    if (c < -1.0) c = -1.0;
    return std::acos(c) * kRadToDeg;
}

double VectorMath::en12464_spacing(double d) {
    if (d <= kEps) return 0.0;
    return 0.2 * std::pow(5.0, std::log10(d));
}

double VectorMath::perimeter_border(double shortest) {
    if (shortest <= kEps) return 0.0;
    const double v = 0.15 * shortest;
    return v < 0.5 ? v : 0.5;
}

namespace {
// Even-odd ray casting; boundary (within eps) counts as inside.
bool point_on_segment(double px, double py, double ax, double ay, double bx, double by) {
    const double cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
    if (std::fabs(cross) > 1e-9) return false;
    const double d2 = (bx - ax) * (bx - ax) + (by - ay) * (by - ay);
    if (d2 < kEps * kEps) {
        const double dx = px - ax, dy = py - ay;
        return dx * dx + dy * dy < 1e-12;
    }
    const double t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / d2;
    return t >= -1e-9 && t <= 1.0 + 1e-9;
}

int orient(double ax, double ay, double bx, double by, double cx, double cy) {
    const double v = (by - ay) * (cx - bx) - (bx - ax) * (cy - by);
    // Returns 0 collinear, 1 cw, 2 ccw with tolerance.
    if (std::fabs(v) < 1e-12) return 0;
    return (v > 0.0) ? 1 : 2;
}

bool seg_intersect_proper(double p1x, double p1y, double p2x, double p2y, double p3x,
                          double p3y, double p4x, double p4y) {
    const int o1 = orient(p1x, p1y, p2x, p2y, p3x, p3y);
    const int o2 = orient(p1x, p1y, p2x, p2y, p4x, p4y);
    const int o3 = orient(p3x, p3y, p4x, p4y, p1x, p1y);
    const int o4 = orient(p3x, p3y, p4x, p4y, p2x, p2y);
    if (o1 != o2 && o3 != o4) return true;
    return false;  // collinear touches are boundary grazes -> allowed
}
}  // namespace

bool VectorMath::point_in_ring(double px, double py, const std::vector<Vec2>& ring) {
    const std::size_t n = ring.size();
    if (n < 3) return false;
    // Boundary counts as inside (covers semantics).
    for (std::size_t i = 0; i < n; ++i) {
        const Vec2& a = ring[i];
        const Vec2& b = ring[(i + 1) % n];
        if (point_on_segment(px, py, a.x, a.y, b.x, b.y)) return true;
    }
    bool inside = false;
    for (std::size_t i = 0, j = n - 1; i < n; j = i++) {
        const double xi = ring[i].x, yi = ring[i].y;
        const double xj = ring[j].x, yj = ring[j].y;
        if ((yi > py) != (yj > py)) {
            const double xint = (xj - xi) * (py - yi) / (yj - yi) + xi;
            if (px < xint) inside = !inside;
        }
    }
    return inside;
}

bool VectorMath::point_in_rings(double px, double py,
                                const std::vector<std::vector<Vec2>>& rings) {
    for (const auto& r : rings) {
        if (point_in_ring(px, py, r)) return true;
    }
    return false;
}

bool VectorMath::segment_inside_ring(const Vec2& a, const Vec2& b,
                                     const std::vector<Vec2>& ring) {
    if (ring.size() < 3) return false;
    if (!point_in_ring(a.x, a.y, ring)) return false;
    if (!point_in_ring(b.x, b.y, ring)) return false;
    const std::size_t n = ring.size();
    const bool a_on_bdry = [&] {
        for (std::size_t i = 0; i < n; ++i) {
            if (point_on_segment(a.x, a.y, ring[i].x, ring[i].y, ring[(i + 1) % n].x,
                                 ring[(i + 1) % n].y))
                return true;
        }
        return false;
    }();
    const bool b_on_bdry = [&] {
        for (std::size_t i = 0; i < n; ++i) {
            if (point_on_segment(b.x, b.y, ring[i].x, ring[i].y, ring[(i + 1) % n].x,
                                 ring[(i + 1) % n].y))
                return true;
        }
        return false;
    }();
    for (std::size_t i = 0; i < n; ++i) {
        const Vec2& c = ring[i];
        const Vec2& d = ring[(i + 1) % n];
        // Edges incident to an endpoint lying exactly on the boundary share that
        // endpoint — touching there is not an occlusion.
        if (a_on_bdry && (point_on_segment(c.x, c.y, a.x, a.y, b.x, b.y) ||
                          point_on_segment(d.x, d.y, a.x, a.y, b.x, b.y))) {
            // Only skip when the ring edge actually meets the segment at a/b.
            // Fall through to the proper-intersection test which already
            // ignores collinear touches; skip only endpoint-touching edges.
            bool touches_a = (std::hypot(c.x - a.x, c.y - a.y) < 1e-9 ||
                              std::hypot(d.x - a.x, d.y - a.y) < 1e-9);
            bool touches_b = (std::hypot(c.x - b.x, c.y - b.y) < 1e-9 ||
                              std::hypot(d.x - b.x, d.y - b.y) < 1e-9);
            if (touches_a || touches_b) continue;
        }
        if (b_on_bdry) {
            bool touches_a = (std::hypot(c.x - a.x, c.y - a.y) < 1e-9 ||
                              std::hypot(d.x - a.x, d.y - a.y) < 1e-9);
            bool touches_b = (std::hypot(c.x - b.x, c.y - b.y) < 1e-9 ||
                              std::hypot(d.x - b.x, d.y - b.y) < 1e-9);
            if (touches_a || touches_b) continue;
        }
        if (seg_intersect_proper(a.x, a.y, b.x, b.y, c.x, c.y, d.x, d.y)) return false;
    }
    return true;
}

bool VectorMath::segment_inside_rings(const Vec2& a, const Vec2& b,
                                      const std::vector<std::vector<Vec2>>& rings) {
    if (rings.empty()) return true;
    if (rings.size() == 1) return segment_inside_ring(a, b, rings[0]);
    // Multiple inset domains (disjoint): visible only within a single domain.
    for (const auto& r : rings) {
        if (segment_inside_ring(a, b, r)) return true;
    }
    // Grazing case mirroring Python _segment_fraction halves is handled by the
    // caller (indirect path uses binary mask; direct path is binary too).
    return false;
}

}  // namespace luxcore
