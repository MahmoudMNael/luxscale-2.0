#pragma once
/// Fixture definition + luminous-opening subdivision.
/// Pure value semantics; subdivision matches Python fixture_service exactly.

#include <utility>
#include <vector>

#include "luxcore/common.h"

namespace luxcore {

/// Fixture placement (position already includes height/2 drop).
struct FixtureDef {
    Vec3 position{0.0, 0.0, 0.0};
    Vec3 aim{0.0, 0.0, -1.0};
    double rotation_deg{0.0};
};

class LuminousOpening final {
  public:
    LuminousOpening() = delete;

    static constexpr double kElement = 0.2;

    /// Returns {corners(4), elements(N)} mirroring Python luminous_opening().
    static std::pair<std::vector<Vec3>, std::vector<Vec3>> compute(
        const FixtureDef& fixture, double length, double width);
    static std::vector<Vec3> elements(const FixtureDef& fixture, double length, double width);
    static std::vector<Vec3> corners(const FixtureDef& fixture, double length, double width);
};

}  // namespace luxcore
