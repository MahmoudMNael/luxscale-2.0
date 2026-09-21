#include "luxcore/direct_engine.h"

#include <cmath>
#ifdef _OPENMP
#include <omp.h>
#endif

#include "luxcore/vector_math.h"

namespace luxcore {

RayGeometry DirectEngine::ray_geometry(const FixtureDef& fixture, const Vec3& patch_center,
                                       const Vec3& patch_normal, const Vec3& origin) const {
    const double tx = patch_center.x - origin.x;
    const double ty = patch_center.y - origin.y;
    const double tz = patch_center.z - origin.z;
    const double distance = std::sqrt(tx * tx + ty * ty + tz * tz);
    const Vec3 to_patch{tx, ty, tz};
    const double theta_source = VectorMath::angle_deg(fixture.aim, to_patch);
    const Vec3 toward{origin.x - patch_center.x, origin.y - patch_center.y,
                      origin.z - patch_center.z};
    const double theta_inc = VectorMath::angle_deg(patch_normal, toward);
    // cross(aim, to_patch)
    const double cx = fixture.aim.y * tz - fixture.aim.z * ty;
    const double cy = fixture.aim.z * tx - fixture.aim.x * tz;
    const double cz = fixture.aim.x * ty - fixture.aim.y * tx;
    double phi = 0.0;
    if (std::sqrt(cx * cx + cy * cy + cz * cz) >= kEps) {
        phi = VectorMath::wrap_deg(std::atan2(ty, tx) * kRadToDeg + fixture.rotation_deg +
                                   config_.c0_offset_deg);
    }
    return RayGeometry{distance, theta_source, phi, theta_inc};
}

std::vector<double> DirectEngine::compute(const FixtureDef& fixture, const PatchSet& patches,
                                          const std::vector<Vec3>& origins,
                                          const IVisibilityPolicy& visibility) const {
    const std::size_t n = patches.size();
    std::vector<double> out(n, 0.0);
    if (n == 0 || origins.empty() || ies_ == nullptr) return out;
    const double inv_n = 1.0 / (double)origins.size();
    const bool check_vis = visibility.blocks_anything();
#ifdef _OPENMP
    if (config_.num_threads > 0) omp_set_num_threads(config_.num_threads);
#pragma omp parallel for schedule(static)
#endif
    for (long long p = 0; p < (long long)n; ++p) {
        const std::size_t pi = (std::size_t)p;
        const Vec3 pc{patches.cx_[pi], patches.cy_[pi], patches.cz_[pi]};
        const Vec3 pn{patches.nx_[pi], patches.ny_[pi], patches.nz_[pi]};
        double total = 0.0;
        for (const auto& o : origins) {
            if (check_vis) {
                const Vec2 a{o.x, o.y};
                const Vec2 b{pc.x, pc.y};
                if (!visibility.is_visible(a, b)) continue;
            }
            const RayGeometry ray = ray_geometry(fixture, pc, pn, o);
            if (ray.distance < kEps || ray.theta_incidence >= 90.0) continue;
            const double intensity = ies_->sample(ray.theta_source, ray.phi_source) * inv_n;
            total += (intensity / (ray.distance * ray.distance)) *
                     std::cos(ray.theta_incidence * kDegToRad);
        }
        out[pi] = total;
    }
    return out;
}

}  // namespace luxcore
