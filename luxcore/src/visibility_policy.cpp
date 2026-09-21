#include "luxcore/visibility_policy.h"

#ifdef _OPENMP
#include <omp.h>
#endif
#include "luxcore/vector_math.h"

namespace luxcore {

bool BufferedRingVisibilityPolicy::is_visible(const Vec2& a, const Vec2& b) const {
    if (ring_.size() < 3) return true;
    return VectorMath::segment_inside_ring(a, b, ring_);
}

std::unique_ptr<IVisibilityPolicy> VisibilityPolicyFactory::create(
    bool convex, std::vector<Vec2> buffered_ring) {
    if (convex || buffered_ring.size() < 3)
        return std::make_unique<TransparentVisibilityPolicy>();
    return std::make_unique<BufferedRingVisibilityPolicy>(std::move(buffered_ring));
}

std::vector<char> UnionVisibilityBuilder::build(const std::vector<Vec2>& uniq_xy,
                                                const IVisibilityPolicy& policy,
                                                bool self_occlusion, int num_threads) {
    const std::size_t m = uniq_xy.size();
    std::vector<char> vis(m * m, 1);
    if (m == 0) return vis;
    if (!policy.blocks_anything()) {
        if (self_occlusion) {
            for (std::size_t i = 0; i < m; ++i) vis[i * m + i] = 0;
        }
        return vis;
    }
#ifdef _OPENMP
    if (num_threads > 0) omp_set_num_threads(num_threads);
#pragma omp parallel for schedule(static)
#endif
    for (long long t = 0; t < (long long)m; ++t) {
        for (std::size_t i = 0; i < m; ++i) {
            if (self_occlusion && i == (std::size_t)t) {
                vis[(std::size_t)t * m + i] = 0;
                continue;
            }
            if (i == (std::size_t)t) {
                vis[(std::size_t)t * m + i] = self_occlusion ? 0 : 1;
                continue;
            }
            vis[(std::size_t)t * m + i] =
                policy.is_visible(uniq_xy[i], uniq_xy[(std::size_t)t]) ? 1 : 0;
        }
    }
    return vis;
}

}  // namespace luxcore
