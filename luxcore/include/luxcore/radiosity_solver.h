#pragma once
/// Radiosity (interreflection) solver: Neumann series over the F matrix with
/// near-field 2x2 refinement + enclosure conservation + plan-view occlusion.
/// Mirrors Python compute_indirect_per_target_per_origin exactly.

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "luxcore/patch_set.h"
#include "luxcore/visibility_policy.h"

namespace luxcore {

struct RadiosityConfig {
    double wall_reflectance{0.5};
    double floor_reflectance{0.2};
    double ceiling_reflectance{0.7};
    int num_bounces{3};
    int num_threads{0};  // 0 = auto
};

/// seeds: origin_id -> values[n_src]; targets: target_id -> PatchSet.
/// Returns values[target_id][origin_id] = vector[n_tgt].
using SeedMap = std::map<std::string, std::vector<double>>;
using TargetMap = std::map<std::string, PatchSet>;
using IndirectResult = std::map<std::string, std::map<std::string, std::vector<double>>>;

class RadiositySolver final {
  public:
    explicit RadiositySolver(RadiosityConfig config) : config_(config) {}

    void set_config(RadiosityConfig c) { config_ = c; }
    RadiosityConfig config() const { return config_; }

    IndirectResult solve(const PatchSet& sources, const SeedMap& seeds,
                         const TargetMap& targets, const IVisibilityPolicy& visibility,
                         const std::vector<Vec2>& uniq_xy_of_sources_and_targets,
                         const std::vector<std::int64_t>& src_unique_index,
                         const std::vector<std::vector<std::int64_t>>& target_unique_index) const;

    /// Simplified overload: builds unique-XY dedup internally from geometry.
    IndirectResult solve(const PatchSet& sources, const SeedMap& seeds,
                         const TargetMap& targets, const IVisibilityPolicy& visibility) const;

    // Exposed for unit parity (single bounce helper).
    std::vector<double> bounce_values(const PatchSet& sources, const std::vector<double>& src_vals,
                                      const PatchSet& targets, double reflectance,
                                      const IVisibilityPolicy& visibility) const;

    static double form_factor(const Vec3& sc, const Vec3& sn, double sa, const Vec3& tc,
                              const Vec3& tn);

  private:
    RadiosityConfig config_;
};

}  // namespace luxcore
