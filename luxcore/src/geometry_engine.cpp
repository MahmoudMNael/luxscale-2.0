#include "luxcore/geometry_engine.h"

#include <cmath>
#include <limits>
#include <map>
#include <utility>

#include "luxcore/vector_math.h"

namespace luxcore {
namespace {

struct LatticeKey {
    long long x, y;
    bool operator<(const LatticeKey& o) const {
        return x < o.x || (x == o.x && y < o.y);
    }
};

}  // namespace

PlanGridResult GeometryEngine::solver_plan_grid(
    const std::vector<Vec2>& bbox_polygon, const std::vector<std::vector<Vec2>>& inside_rings,
    double plane_z, SurfaceType surface, double cell, const Vec3& normal) {
    PlanGridResult out;
    out.meta = GridMeta{};
    if (bbox_polygon.empty() || cell <= kEps) return out;
    double xmin = bbox_polygon[0].x, xmax = xmin, ymin = bbox_polygon[0].y, ymax = ymin;
    for (const auto& p : bbox_polygon) {
        xmin = std::min(xmin, p.x);
        xmax = std::max(xmax, p.x);
        ymin = std::min(ymin, p.y);
        ymax = std::max(ymax, p.y);
    }
    const double width = xmax - xmin, height = ymax - ymin;
    if (width <= kEps || height <= kEps) return out;
    const long long nx = std::max(1LL, (long long)std::ceil(width / cell - kEps));
    const long long ny = std::max(1LL, (long long)std::ceil(height / cell - kEps));
    const double dx = width / nx, dy = height / ny;
    const double area = dx * dy, size = std::max(dx, dy);
    out.patches.reserve((std::size_t)nx * (std::size_t)ny);
    for (long long j = 0; j < ny; ++j) {
        const double cy = ymin + (j + 0.5) * dy;
        for (long long i = 0; i < nx; ++i) {
            const double cx = xmin + (i + 0.5) * dx;
            if (!VectorMath::point_in_rings(cx, cy, inside_rings)) continue;
            out.patches.push_back(Patch{{cx, cy, plane_z}, normal, area, size, surface});
        }
    }
    out.meta.spacing = out.meta.spacing_x = out.meta.spacing_y = cell;
    out.meta.nx = (double)nx;
    out.meta.ny = (double)ny;
    out.meta.dx = dx;
    out.meta.dy = dy;
    out.meta.xmin = xmin;
    out.meta.xmax = xmax;
    out.meta.ymin = ymin;
    out.meta.ymax = ymax;
    return out;
}

WallGridResult GeometryEngine::solver_wall_grid(const WallDef& wall, double cell) {
    WallGridResult out;
    out.meta = GridMeta{};
    if (wall.length <= kEps || wall.height <= kEps || cell <= kEps) return out;
    const long long ns = std::max(1LL, (long long)std::ceil(wall.length / cell - kEps));
    const long long nz = std::max(1LL, (long long)std::ceil(wall.height / cell - kEps));
    const double ds = wall.length / ns, dz = wall.height / nz;
    const double ux = (wall.end.x - wall.start.x) / wall.length;
    const double uy = (wall.end.y - wall.start.y) / wall.length;
    out.patches.reserve((std::size_t)ns * (std::size_t)nz);
    for (long long k = 0; k < nz; ++k) {
        const double zm = (k + 0.5) * dz;
        for (long long i = 0; i < ns; ++i) {
            const double sm = (i + 0.5) * ds;
            out.patches.push_back(
                Patch{{wall.start.x + ux * sm, wall.start.y + uy * sm, zm},
                      {wall.normal.x, wall.normal.y, 0.0},
                      ds * dz,
                      std::max(ds, dz),
                      SurfaceType::Wall});
        }
    }
    out.meta.spacing = out.meta.spacing_x = out.meta.spacing_y = cell;
    out.meta.nx = (double)ns;
    out.meta.ny = (double)nz;
    out.meta.dx = ds;
    out.meta.dy = dz;
    out.meta.xmax = wall.length;
    out.meta.ymax = wall.height;
    return out;
}

WallGridResult GeometryEngine::wall_grid(const WallDef& wall, double border, bool apply_neglect) {
    WallGridResult out;
    out.meta = GridMeta{};
    out.meta.border = border;
    if (apply_neglect && std::min(wall.length, wall.height) <= 1.0 + kEps) return out;
    const double eff_l = wall.length - 2.0 * border;
    const double eff_h = wall.height - 2.0 * border;
    if (eff_l <= kEps || eff_h <= kEps) return out;
    const double spacing = VectorMath::en12464_spacing(std::max(eff_l, eff_h));
    if (spacing <= kEps) return out;
    const long long ns = std::max(1LL, (long long)std::ceil(eff_l / spacing - kEps));
    const long long nz = std::max(1LL, (long long)std::ceil(eff_h / spacing - kEps));
    const double ds = eff_l / ns, dz = eff_h / nz;
    const double ux = (wall.end.x - wall.start.x) / wall.length;
    const double uy = (wall.end.y - wall.start.y) / wall.length;
    out.patches.reserve((std::size_t)ns * (std::size_t)nz);
    for (long long k = 0; k < nz; ++k) {
        const double zm = border + (k + 0.5) * dz;
        for (long long i = 0; i < ns; ++i) {
            const double sm = border + (i + 0.5) * ds;
            out.patches.push_back(
                Patch{{wall.start.x + ux * sm, wall.start.y + uy * sm, zm},
                      {wall.normal.x, wall.normal.y, 0.0},
                      ds * dz,
                      std::max(ds, dz),
                      SurfaceType::Wall});
        }
    }
    out.meta.spacing = out.meta.spacing_x = out.meta.spacing_y = spacing;
    out.meta.nx = (double)ns;
    out.meta.ny = (double)nz;
    out.meta.dx = ds;
    out.meta.dy = dz;
    out.meta.xmin = border;
    out.meta.xmax = border + eff_l;
    out.meta.ymin = border;
    out.meta.ymax = border + eff_h;
    return out;
}

namespace {

std::map<LatticeKey, std::int64_t> lattice_map_plan(const std::vector<Patch>& full,
                                                    double xmin, double ymin, double dx,
                                                    double dy) {
    std::map<LatticeKey, std::int64_t> m;
    for (std::size_t n = 0; n < full.size(); ++n) {
        // NOTE: std::nearbyint (banker's, FE_TONEAREST) matches Python round().
        const long long ix =
            (long long)std::nearbyint((full[n].center.x - xmin) / dx - 0.5);
        const long long iy =
            (long long)std::nearbyint((full[n].center.y - ymin) / dy - 0.5);
        m[{ix, iy}] = (std::int64_t)n;
    }
    return m;
}

std::int64_t nearest_patch(const std::vector<Patch>& v, double cx, double cy, double cz) {
    std::int64_t best = 0;
    double bd = std::numeric_limits<double>::infinity();
    for (std::size_t n = 0; n < v.size(); ++n) {
        const double dx = v[n].center.x - cx, dy = v[n].center.y - cy, dz = v[n].center.z - cz;
        const double d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < bd) {
            bd = d2;
            best = (std::int64_t)n;
        }
    }
    return best;
}

}  // namespace

CsrWeights GeometryEngine::build_plan_interp_weights(const std::vector<Patch>& full,
                                                     const GridMeta& fm,
                                                     const std::vector<Patch>& eval, double eval_dx,
                                                     double eval_dy) {
    CsrWeights w;
    w.n_eval = (std::int64_t)eval.size();
    w.n_full = (std::int64_t)full.size();
    w.indptr.assign(eval.size() + 1, 0);
    if (full.empty() || eval.empty() || fm.nx <= 0 || fm.ny <= 0 || fm.dx <= kEps ||
        fm.dy <= kEps)
        return w;
    const long long nx = (long long)fm.nx, ny = (long long)fm.ny;
    auto lattice = lattice_map_plan(full, fm.xmin, fm.ymin, fm.dx, fm.dy);
    auto footprint = [&](double cx, double cy, std::vector<std::pair<std::int64_t, double>>& taps) {
        taps.clear();
        if (eval_dx <= kEps || eval_dy <= kEps) return false;
        const long long ilo =
            std::max(0LL, (long long)std::ceil((cx - eval_dx / 2 - fm.xmin) / fm.dx - 0.5 - kEps));
        const long long ihi = std::min(
            nx - 1, (long long)std::floor((cx + eval_dx / 2 - fm.xmin) / fm.dx - 0.5 + kEps));
        const long long jlo =
            std::max(0LL, (long long)std::ceil((cy - eval_dy / 2 - fm.ymin) / fm.dy - 0.5 - kEps));
        const long long jhi = std::min(
            ny - 1, (long long)std::floor((cy + eval_dy / 2 - fm.ymin) / fm.dy - 0.5 + kEps));
        if (ihi < ilo || jhi < jlo) return false;
        for (long long j = jlo; j <= jhi; ++j)
            for (long long i = ilo; i <= ihi; ++i) {
                auto it = lattice.find({i, j});
                if (it != lattice.end()) taps.emplace_back(it->second, 1.0);
            }
        if (taps.empty()) return false;
        const double wt = 1.0 / taps.size();
        for (auto& t : taps) t.second = wt;
        return true;
    };
    std::vector<std::pair<std::int64_t, double>> taps;
    for (std::size_t e = 0; e < eval.size(); ++e) {
        taps.clear();
        if (!footprint(eval[e].center.x, eval[e].center.y, taps)) {
            taps.clear();
            const double fx = (eval[e].center.x - fm.xmin) / fm.dx - 0.5;
            const double fy = (eval[e].center.y - fm.ymin) / fm.dy - 0.5;
            const long long i0 = (long long)std::floor(fx), j0 = (long long)std::floor(fy);
            const double tx = fx - i0, ty = fy - j0;
            const long long ci[4] = {i0, i0 + 1, i0, i0 + 1};
            const long long cj[4] = {j0, j0, j0 + 1, j0 + 1};
            const double cw[4] = {(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty};
            double s = 0.0;
            for (int k = 0; k < 4; ++k) {
                if (cw[k] <= 0.0) continue;
                auto it = lattice.find({ci[k], cj[k]});
                if (it != lattice.end()) {
                    taps.emplace_back(it->second, cw[k]);
                    s += cw[k];
                }
            }
            if (taps.empty()) {
                taps.emplace_back(nearest_patch(full, eval[e].center.x, eval[e].center.y,
                                                eval[e].center.z),
                                  1.0);
            } else {
                for (auto& t : taps) t.second /= s;
            }
        }
        for (auto& t : taps) {
            w.indices.push_back(t.first);
            w.data.push_back(t.second);
        }
        w.indptr[e + 1] = (std::int64_t)w.indices.size();
    }
    return w;
}

CsrWeights GeometryEngine::build_wall_interp_weights(const WallDef& wall,
                                                     const std::vector<Patch>& full,
                                                     const GridMeta& fm,
                                                     const std::vector<Patch>& eval, double eval_ds,
                                                     double eval_dz) {
    CsrWeights w;
    w.n_eval = (std::int64_t)eval.size();
    w.n_full = (std::int64_t)full.size();
    w.indptr.assign(eval.size() + 1, 0);
    if (wall.length <= kEps || full.empty() || eval.empty()) return w;
    const double ux = (wall.end.x - wall.start.x) / wall.length;
    const double uy = (wall.end.y - wall.start.y) / wall.length;
    const long long ns = (long long)fm.nx, nz = (long long)fm.ny;
    if (ns <= 0 || nz <= 0 || fm.dx <= kEps || fm.dy <= kEps) return w;
    std::map<LatticeKey, std::int64_t> lattice;
    for (std::size_t n = 0; n < full.size(); ++n) {
        const double s =
            (full[n].center.x - wall.start.x) * ux + (full[n].center.y - wall.start.y) * uy;
        const long long ix = (long long)std::nearbyint(s / fm.dx - 0.5);
        const long long iy = (long long)std::nearbyint(full[n].center.z / fm.dy - 0.5);
        lattice[{ix, iy}] = (std::int64_t)n;
    }
    std::vector<std::pair<std::int64_t, double>> taps;
    for (std::size_t e = 0; e < eval.size(); ++e) {
        taps.clear();
        const double s =
            (eval[e].center.x - wall.start.x) * ux + (eval[e].center.y - wall.start.y) * uy;
        const double z = eval[e].center.z;
        bool ok = false;
        if (eval_ds > kEps && eval_dz > kEps) {
            const long long ilo =
                std::max(0LL, (long long)std::ceil((s - eval_ds / 2) / fm.dx - 0.5 - kEps));
            const long long ihi = std::min(
                ns - 1, (long long)std::floor((s + eval_ds / 2) / fm.dx - 0.5 + kEps));
            const long long klo =
                std::max(0LL, (long long)std::ceil((z - eval_dz / 2) / fm.dy - 0.5 - kEps));
            const long long khi = std::min(
                nz - 1, (long long)std::floor((z + eval_dz / 2) / fm.dy - 0.5 + kEps));
            if (ihi >= ilo && khi >= klo) {
                for (long long k = klo; k <= khi; ++k)
                    for (long long i = ilo; i <= ihi; ++i) {
                        auto it = lattice.find({i, k});
                        if (it != lattice.end()) taps.emplace_back(it->second, 1.0);
                    }
                if (!taps.empty()) {
                    const double wt = 1.0 / taps.size();
                    for (auto& t : taps) t.second = wt;
                    ok = true;
                }
            }
        }
        if (!ok) {
            taps.clear();
            const double fs = s / fm.dx - 0.5, fz = z / fm.dy - 0.5;
            const long long i0 = (long long)std::floor(fs), k0 = (long long)std::floor(fz);
            const double ts = fs - i0, tz = fz - k0;
            const long long ci[4] = {i0, i0 + 1, i0, i0 + 1};
            const long long ck[4] = {k0, k0, k0 + 1, k0 + 1};
            const double cw[4] = {(1 - ts) * (1 - tz), ts * (1 - tz), (1 - ts) * tz, ts * tz};
            double ssum = 0.0;
            for (int k = 0; k < 4; ++k) {
                if (cw[k] <= 0.0) continue;
                auto it = lattice.find({ci[k], ck[k]});
                if (it != lattice.end()) {
                    taps.emplace_back(it->second, cw[k]);
                    ssum += cw[k];
                }
            }
            if (taps.empty()) {
                taps.emplace_back(
                    nearest_patch(full, eval[e].center.x, eval[e].center.y, eval[e].center.z), 1.0);
            } else {
                for (auto& t : taps) t.second /= ssum;
            }
        }
        for (auto& t : taps) {
            w.indices.push_back(t.first);
            w.data.push_back(t.second);
        }
        w.indptr[e + 1] = (std::int64_t)w.indices.size();
    }
    return w;
}

std::vector<double> GeometryEngine::apply_weights(const std::vector<double>& values,
                                                  const CsrWeights& w) {
    std::vector<double> out((std::size_t)w.n_eval, 0.0);
    if (w.n_eval == 0) return out;
    for (std::int64_t r = 0; r < w.n_eval; ++r) {
        double acc = 0.0;
        for (std::int64_t t = w.indptr[(std::size_t)r]; t < w.indptr[(std::size_t)r + 1]; ++t)
            acc += w.data[(std::size_t)t] * values[(std::size_t)w.indices[(std::size_t)t]];
        out[(std::size_t)r] = acc;
    }
    return out;
}

std::vector<std::int64_t> GeometryEngine::sample_plan_to_eval(const std::vector<Patch>& full,
                                                              const GridMeta& fm,
                                                              const std::vector<Patch>& eval) {
    std::vector<std::int64_t> out;
    out.reserve(eval.size());
    if (full.empty() || fm.nx <= 0 || fm.ny <= 0 || fm.dx <= kEps || fm.dy <= kEps) return out;
    auto lattice = lattice_map_plan(full, fm.xmin, fm.ymin, fm.dx, fm.dy);
    const long long nx = (long long)fm.nx, ny = (long long)fm.ny;
    for (const auto& e : eval) {
        long long i = (long long)std::floor((e.center.x - fm.xmin) / fm.dx);
        long long j = (long long)std::floor((e.center.y - fm.ymin) / fm.dy);
        i = std::max(0LL, std::min(nx - 1, i));
        j = std::max(0LL, std::min(ny - 1, j));
        auto it = lattice.find({i, j});
        out.push_back(it != lattice.end()
                          ? it->second
                          : nearest_patch(full, e.center.x, e.center.y, e.center.z));
    }
    return out;
}

std::vector<std::int64_t> GeometryEngine::sample_wall_to_eval(const WallDef& wall,
                                                              const std::vector<Patch>& full,
                                                              const GridMeta& fm,
                                                              const std::vector<Patch>& eval) {
    std::vector<std::int64_t> out;
    out.reserve(eval.size());
    if (full.empty() || fm.nx <= 0 || fm.ny <= 0 || fm.dx <= kEps || fm.dy <= kEps) return out;
    const double ux = (wall.end.x - wall.start.x) / wall.length;
    const double uy = (wall.end.y - wall.start.y) / wall.length;
    std::map<LatticeKey, std::int64_t> lattice;
    for (std::size_t n = 0; n < full.size(); ++n) {
        const double s =
            (full[n].center.x - wall.start.x) * ux + (full[n].center.y - wall.start.y) * uy;
        lattice[{(long long)std::nearbyint(s / fm.dx - 0.5),
                 (long long)std::nearbyint(full[n].center.z / fm.dy - 0.5)}] = (std::int64_t)n;
    }
    const long long ns = (long long)fm.nx, nz = (long long)fm.ny;
    for (const auto& e : eval) {
        const double s = (e.center.x - wall.start.x) * ux + (e.center.y - wall.start.y) * uy;
        long long i = (long long)std::floor(s / fm.dx);
        long long k = (long long)std::floor(e.center.z / fm.dy);
        i = std::max(0LL, std::min(ns - 1, i));
        k = std::max(0LL, std::min(nz - 1, k));
        auto it = lattice.find({i, k});
        out.push_back(it != lattice.end()
                          ? it->second
                          : nearest_patch(full, e.center.x, e.center.y, e.center.z));
    }
    return out;
}

}  // namespace luxcore
