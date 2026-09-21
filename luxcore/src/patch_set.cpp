#include "luxcore/patch_set.h"

namespace luxcore {

void PatchSet::resize(std::size_t n) {
    cx_.assign(n, 0.0);
    cy_.assign(n, 0.0);
    cz_.assign(n, 0.0);
    nx_.assign(n, 0.0);
    ny_.assign(n, 0.0);
    nz_.assign(n, 0.0);
    area_.assign(n, 0.0);
    size_.assign(n, 0.0);
    surface_.assign(n, 0);
}

void PatchSet::push(const Patch& p) {
    cx_.push_back(p.center.x);
    cy_.push_back(p.center.y);
    cz_.push_back(p.center.z);
    nx_.push_back(p.normal.x);
    ny_.push_back(p.normal.y);
    nz_.push_back(p.normal.z);
    area_.push_back(p.area);
    size_.push_back(p.size);
    surface_.push_back(static_cast<std::int32_t>(p.surface));
}

Patch PatchSet::at(std::size_t i) const {
    Patch p;
    p.center = center(i);
    p.normal = normal(i);
    p.area = area_[i];
    p.size = size_[i];
    p.surface = surface_type_from_int(surface_[i]);
    return p;
}

PatchSet PatchSet::from_patches(const std::vector<Patch>& patches) {
    PatchSet out;
    out.resize(0);
    out.cx_.reserve(patches.size());
    out.cy_.reserve(patches.size());
    out.cz_.reserve(patches.size());
    out.nx_.reserve(patches.size());
    out.ny_.reserve(patches.size());
    out.nz_.reserve(patches.size());
    out.area_.reserve(patches.size());
    out.size_.reserve(patches.size());
    out.surface_.reserve(patches.size());
    for (const auto& p : patches) out.push(p);
    return out;
}

std::vector<Patch> PatchSet::to_patches() const {
    std::vector<Patch> out;
    out.reserve(size());
    for (std::size_t i = 0; i < size(); ++i) out.push_back(at(i));
    return out;
}

}  // namespace luxcore
