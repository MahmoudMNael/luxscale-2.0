#pragma once
/// Mesh generation + interpolation weights (Relux solver/eval semantics).
/// Stateless factory/utility class grouping the grid builders.

#include <cstdint>
#include <utility>
#include <vector>

#include "luxcore/common.h"
#include "luxcore/patch_set.h"

namespace luxcore {

struct PlanGridResult {
    std::vector<Patch> patches;
    GridMeta meta;
};

struct WallGridResult {
    std::vector<Patch> patches;
    GridMeta meta;
};

class GeometryEngine final {
  public:
    GeometryEngine() = delete;

    /// Fixed-raster solver mesh over room bbox, centres kept when inside ring(s).
    /// rings: one ring for convex rooms (Hybrid: Python passes inset domains).
    static PlanGridResult solver_plan_grid(const std::vector<Vec2>& bbox_polygon,
                                           const std::vector<std::vector<Vec2>>& inside_rings,
                                           double plane_z, SurfaceType surface, double cell,
                                           const Vec3& normal);

    /// Full-coverage wall solver mesh (no border, no neglect).
    static WallGridResult solver_wall_grid(const WallDef& wall, double cell);

    /// EN12464 wall evaluation mesh (border + 1m neglect when apply_neglect).
    static WallGridResult wall_grid(const WallDef& wall, double border, bool apply_neglect);

    // --- interpolation ---

    static CsrWeights build_plan_interp_weights(const std::vector<Patch>& full,
                                                const GridMeta& full_meta,
                                                const std::vector<Patch>& eval, double eval_dx,
                                                double eval_dy);

    static CsrWeights build_wall_interp_weights(const WallDef& wall,
                                                const std::vector<Patch>& full,
                                                const GridMeta& full_meta,
                                                const std::vector<Patch>& eval, double eval_ds,
                                                double eval_dz);

    static std::vector<double> apply_weights(const std::vector<double>& values,
                                             const CsrWeights& w);

    static std::vector<std::int64_t> sample_plan_to_eval(const std::vector<Patch>& full,
                                                         const GridMeta& full_meta,
                                                         const std::vector<Patch>& eval);
    static std::vector<std::int64_t> sample_wall_to_eval(const WallDef& wall,
                                                         const std::vector<Patch>& full,
                                                         const GridMeta& full_meta,
                                                         const std::vector<Patch>& eval);
};

}  // namespace luxcore
