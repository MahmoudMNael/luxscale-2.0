#include "luxcore/fixture.h"

#include <cmath>

#include "luxcore/common.h"

namespace luxcore {

std::pair<std::vector<Vec3>, std::vector<Vec3>> LuminousOpening::compute(
    const FixtureDef& fixture, double length, double width) {
    return {corners(fixture, length, width), elements(fixture, length, width)};
}

std::vector<Vec3> LuminousOpening::corners(const FixtureDef& fixture, double length,
                                           double width) {
    const double rot = fixture.rotation_deg * kDegToRad;
    const double ux = std::cos(rot), uy = std::sin(rot);
    const double vx = -std::sin(rot), vy = std::cos(rot);
    const double hl = length / 2.0, hw = width / 2.0;
    const double cx = fixture.position.x, cy = fixture.position.y, cz = fixture.position.z;
    return {
        {cx - ux * hl - vx * hw, cy - uy * hl - vy * hw, cz},
        {cx + ux * hl - vx * hw, cy + uy * hl - vy * hw, cz},
        {cx + ux * hl + vx * hw, cy + uy * hl + vy * hw, cz},
        {cx - ux * hl + vx * hw, cy - uy * hl + vy * hw, cz},
    };
}

std::vector<Vec3> LuminousOpening::elements(const FixtureDef& fixture, double length,
                                            double width) {
    const double rot = fixture.rotation_deg * kDegToRad;
    const double ux = std::cos(rot), uy = std::sin(rot);
    const double vx = -std::sin(rot), vy = std::cos(rot);
    const double hl = length / 2.0, hw = width / 2.0;
    const double cx = fixture.position.x, cy = fixture.position.y, cz = fixture.position.z;
    int nx = (int)std::max(1.0, std::ceil(length / kElement - kEps));
    int ny = (int)std::max(1.0, std::ceil(width / kElement - kEps));
    const double dx = length / nx, dy = width / ny;
    std::vector<Vec3> out;
    out.reserve((std::size_t)nx * (std::size_t)ny);
    for (int j = 0; j < ny; ++j) {
        for (int i = 0; i < nx; ++i) {
            const double ox = ((i + 0.5) * dx - hl);
            const double oy = ((j + 0.5) * dy - hw);
            out.push_back({cx + ux * ox + vx * oy, cy + uy * ox + vy * oy, cz});
        }
    }
    return out;
}

}  // namespace luxcore
