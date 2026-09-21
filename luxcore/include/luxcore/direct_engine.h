#pragma once
/// Direct illuminance engine: point/area-source I/N sum with occlusion.
/// Owns config + photometry refs; compute() is const and thread-safe.

#include <vector>

#include "luxcore/common.h"
#include "luxcore/fixture.h"
#include "luxcore/ies_profile.h"
#include "luxcore/patch_set.h"
#include "luxcore/visibility_policy.h"

namespace luxcore {

struct DirectConfig {
    double c0_offset_deg{0.0};
    int num_threads{0};  // 0 = auto
};

struct RayGeometry {
    double distance{0.0};
    double theta_source{0.0};
    double phi_source{0.0};
    double theta_incidence{0.0};
};

class DirectEngine final {
  public:
    DirectEngine(DirectConfig config, const IesProfile* ies) : config_(config), ies_(ies) {}

    void set_config(DirectConfig c) { config_ = c; }
    DirectConfig config() const { return config_; }

    /// Ray geometry mirroring Python compute_ray_geometry().
    RayGeometry ray_geometry(const FixtureDef& fixture, const Vec3& patch_center,
                             const Vec3& patch_normal, const Vec3& origin) const;

    /// Direct illuminance for every patch (OpenMP over patches).
    /// origins: luminous element sample points. visibility: plan-view occlusion.
    std::vector<double> compute(const FixtureDef& fixture, const PatchSet& patches,
                                const std::vector<Vec3>& origins,
                                const IVisibilityPolicy& visibility) const;

  private:
    DirectConfig config_;
    const IesProfile* ies_;  // non-owning; lifetime managed by caller/binding
};

}  // namespace luxcore
