#pragma once
/// Small stateless math utilities. All methods are static so the class
/// acts as a namespace with a clear ownership boundary (OOP: utility class).

#include <cmath>
#include <vector>

#include "luxcore/common.h"

namespace luxcore {

class VectorMath final {
  public:
    VectorMath() = delete;

    static inline double dot(const Vec3& a, const Vec3& b) {
        return a.x * b.x + a.y * b.y + a.z * b.z;
    }
    static inline double norm(const Vec3& a) { return std::sqrt(dot(a, a)); }

    static inline Vec3 normalize(const Vec3& a) {
        const double n = norm(a);
        if (n < kEps) return Vec3{0.0, 0.0, 0.0};
        return Vec3{a.x / n, a.y / n, a.z / n};
    }

    /// Angle between two vectors in degrees (90 when degenerate, like Python).
    static double angle_deg(const Vec3& a, const Vec3& b);

    static inline double wrap_deg(double phi) {
        double r = std::fmod(phi, 360.0);
        if (r < 0.0) r += 360.0;
        // Match Python `phi % 360.0` for negative values; fmod path above does that.
        // Guard -0.0.
        return r == 0.0 ? 0.0 : r;
    }

    /// EN 12464-1 spacing: p = 0.2 * 5^log10(d).
    static double en12464_spacing(double d);

    static double perimeter_border(double shortest);

    // --- plan-view polygon helpers (fast path, no GEOS) ---

    /// Ray-casting point-in-ring; boundary counts as inside (covers semantics).
    static bool point_in_ring(double px, double py, const std::vector<Vec2>& ring);

    static bool point_in_rings(double px, double py,
                               const std::vector<std::vector<Vec2>>& rings);

    /// True when segment a->b stays inside the (buffered) ring.
    /// Both endpoints must be inside/on-boundary and the open segment must
    /// not cross any ring edge (touching at endpoints is allowed).
    static bool segment_inside_ring(const Vec2& a, const Vec2& b,
                                    const std::vector<Vec2>& ring);

    static bool segment_inside_rings(const Vec2& a, const Vec2& b,
                                     const std::vector<std::vector<Vec2>>& rings);
};

}  // namespace luxcore
