#pragma once
/// Patch layout in struct-of-arrays form for SIMD/OpenMP friendliness.
/// Owns its storage (RAII); views are passed as const refs to engines.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "luxcore/common.h"

namespace luxcore {

/// Single patch in array-of-structs form (used for mesh generation output).
struct Patch {
    Vec3 center{0.0, 0.0, 0.0};
    Vec3 normal{0.0, 0.0, 0.0};
    double area{0.0};
    double size{0.0};
    SurfaceType surface{SurfaceType::Floor};
};

/// Owning SoA container. Engines operate on this, never on Python objects.
class PatchSet final {
  public:
    PatchSet() = default;
    explicit PatchSet(std::size_t n) { resize(n); }

    void resize(std::size_t n);
    std::size_t size() const { return area_.size(); }
    bool empty() const { return area_.empty(); }

    // Structure-of-arrays storage (public for OpenMP kernels, logically
    // encapsulated by the class invariant: all vectors share one length).
    std::vector<double> cx_, cy_, cz_;
    std::vector<double> nx_, ny_, nz_;
    std::vector<double> area_;
    std::vector<double> size_;
    std::vector<std::int32_t> surface_;  // 0 wall, 1 floor, 2 ceiling

    Vec3 center(std::size_t i) const { return Vec3{cx_[i], cy_[i], cz_[i]}; }
    Vec3 normal(std::size_t i) const { return Vec3{nx_[i], ny_[i], nz_[i]}; }

    void push(const Patch& p);
    Patch at(std::size_t i) const;

    static PatchSet from_patches(const std::vector<Patch>& patches);
    std::vector<Patch> to_patches() const;
};

}  // namespace luxcore
