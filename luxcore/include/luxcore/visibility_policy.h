#pragma once
/// Visibility policies (Strategy pattern).
/// Python/Shapely still owns boolean buffer/inset ops (Hybrid); C++ owns the
/// hot per-segment predicate over the already-buffered ring vertices.

#include <memory>
#include <vector>

#include "luxcore/common.h"

namespace luxcore {

/// Abstract plan-view visibility predicate.
class IVisibilityPolicy {
  public:
    virtual ~IVisibilityPolicy() = default;
    virtual bool is_visible(const Vec2& a, const Vec2& b) const = 0;
    virtual bool blocks_anything() const = 0;
};

/// Convex rooms (or no polygon): everything visible.
class TransparentVisibilityPolicy final : public IVisibilityPolicy {
  public:
    bool is_visible(const Vec2&, const Vec2&) const override { return true; }
    bool blocks_anything() const override { return false; }
};

/// Concave rooms: segment must stay inside the buffered ring.
class BufferedRingVisibilityPolicy final : public IVisibilityPolicy {
  public:
    explicit BufferedRingVisibilityPolicy(std::vector<Vec2> buffered_ring)
        : ring_(std::move(buffered_ring)) {}

    bool is_visible(const Vec2& a, const Vec2& b) const override;
    bool blocks_anything() const override { return ring_.size() >= 3; }
    const std::vector<Vec2>& ring() const { return ring_; }

  private:
    std::vector<Vec2> ring_;
};

/// Factory selecting the right policy from Python-side inputs.
class VisibilityPolicyFactory final {
  public:
    VisibilityPolicyFactory() = delete;
    /// When convex==true (or ring empty) returns a transparent policy.
    static std::unique_ptr<IVisibilityPolicy> create(bool convex,
                                                    std::vector<Vec2> buffered_ring);
};

/// Batch visibility over deduplicated unique XY positions (mirrors
/// Python _union_plan_visibility but parallel with OpenMP).
/// Returns row-major mu x mu bool mask (true = visible). Diagonal: i==j -> false
/// when for_self_occlusion is set (source-source F matrix), else true.
class UnionVisibilityBuilder final {
  public:
    UnionVisibilityBuilder() = delete;
    static std::vector<char> build(const std::vector<Vec2>& uniq_xy,
                                   const IVisibilityPolicy& policy,
                                   bool self_occlusion, int num_threads);
};

}  // namespace luxcore
