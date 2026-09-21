#include "luxcore/radiosity_solver.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <unordered_map>
#ifdef _OPENMP
#include <omp.h>
#endif

#include "luxcore/common.h"
#include "luxcore/vector_math.h"
#include "luxcore/visibility_policy.h"

namespace luxcore {
namespace {

// Quantize like Python round(x, 9).
inline std::int64_t q9(double v) { return (std::int64_t)std::llround(v * 1e9); }
struct XYKey {
    std::int64_t x, y;
    bool operator==(const XYKey& o) const { return x == o.x && y == o.y; }
};
struct XYHash {
    std::size_t operator()(const XYKey& k) const noexcept {
        return (std::size_t)(k.x * 1000003LL ^ k.y * 917719);
    }
};

struct TangentFrames {
    std::vector<double> t1x, t1y, t1z, t2x, t2y, t2z;
};

TangentFrames tangent_frames(const std::vector<double>& nx, const std::vector<double>& ny,
                             const std::vector<double>& nz) {
    const std::size_t n = nx.size();
    TangentFrames f;
    f.t1x.resize(n);
    f.t1y.resize(n);
    f.t1z.resize(n);
    f.t2x.resize(n);
    f.t2y.resize(n);
    f.t2z.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        double nnx = nx[i], nny = ny[i], nnz = nz[i];
        const double l = std::sqrt(nnx * nnx + nny * nny + nnz * nnz);
        const double il = (l < kEps) ? 0.0 : 1.0 / std::max(l, kEps);
        nnx *= il;
        nny *= il;
        nnz *= il;
        double upx = 0.0, upy = 0.0, upz = 1.0;
        if (std::fabs(nnz) > 0.9) {
            upx = 1.0;
            upy = 0.0;
            upz = 0.0;
        }
        // t1 = up x n
        double t1x = upy * nnz - upz * nny;
        double t1y = upz * nnx - upx * nnz;
        double t1z = upx * nny - upy * nnx;
        const double l1 = std::sqrt(t1x * t1x + t1y * t1y + t1z * t1z);
        const double il1 = 1.0 / std::max(l1, kEps);
        t1x *= il1;
        t1y *= il1;
        t1z *= il1;
        // t2 = n x t1
        const double t2x = nny * t1z - nnz * t1y;
        const double t2y = nnz * t1x - nnx * t1z;
        const double t2z = nnx * t1y - nny * t1x;
        f.t1x[i] = t1x;
        f.t1y[i] = t1y;
        f.t1z[i] = t1z;
        f.t2x[i] = t2x;
        f.t2y[i] = t2y;
        f.t2z[i] = t2z;
    }
    return f;
}

// In-place 2x2 refinement mirroring Python _refine_close_transfers.
void refine_close(std::vector<double>& g, const PatchSet& src, const TangentFrames& sf,
                  const Vec3& tp, const Vec3& tn, double tarea, const Vec3& tt1,
                  const Vec3& tt2, const std::vector<char>& close) {
    bool any = false;
    for (char c : close) {
        if (c) {
            any = true;
            break;
        }
    }
    if (!any) return;
    const double ds_t = std::sqrt(std::max(tarea, kEps));
    const double off[2] = {-0.25 * ds_t, 0.25 * ds_t};
    double tq[4][3];
    int q = 0;
    for (int a = 0; a < 2; ++a)
        for (int b = 0; b < 2; ++b) {
            tq[q][0] = tp.x + off[a] * tt1.x + off[b] * tt2.x;
            tq[q][1] = tp.y + off[a] * tt1.y + off[b] * tt2.y;
            tq[q][2] = tp.z + off[a] * tt1.z + off[b] * tt2.z;
            ++q;
        }
    const std::size_t n = src.size();
    for (std::size_t i = 0; i < n; ++i) {
        if (!close[i]) continue;
        const double ds = std::sqrt(std::max(src.area_[i], kEps));
        const double o[2] = {-0.25 * ds, 0.25 * ds};
        double sp[4][3];
        int qq = 0;
        for (int a = 0; a < 2; ++a)
            for (int b = 0; b < 2; ++b) {
                sp[qq][0] = src.cx_[i] + o[a] * sf.t1x[i] + o[b] * sf.t2x[i];
                sp[qq][1] = src.cy_[i] + o[a] * sf.t1y[i] + o[b] * sf.t2y[i];
                sp[qq][2] = src.cz_[i] + o[a] * sf.t1z[i] + o[b] * sf.t2z[i];
                ++qq;
            }
        double acc = 0.0;
        for (int qi = 0; qi < 4; ++qi) {
            for (int pi = 0; pi < 4; ++pi) {
                const double dx = tq[qi][0] - sp[pi][0];
                const double dy = tq[qi][1] - sp[pi][1];
                const double dz = tq[qi][2] - sp[pi][2];
                const double d2 = dx * dx + dy * dy + dz * dz;
                if (d2 < kEps * kEps) continue;
                const double d = std::sqrt(d2);
                const double c1 = (dx * src.nx_[i] + dy * src.ny_[i] + dz * src.nz_[i]) / d;
                const double c2 = -(dx * tn.x + dy * tn.y + dz * tn.z) / d;
                if (c1 <= 0.0 || c2 <= 0.0) continue;
                acc += (src.area_[i] / 4.0) * c1 * c2 / (kPi * d2);
            }
        }
        g[i] = acc / 4.0;
    }
}

}  // namespace

double RadiositySolver::form_factor(const Vec3& sc, const Vec3& sn, double sa, const Vec3& tc,
                                    const Vec3& tn) {
    const double lx = tc.x - sc.x, ly = tc.y - sc.y, lz = tc.z - sc.z;
    const double d2 = lx * lx + ly * ly + lz * lz;
    if (d2 < kEps * kEps) return 0.0;
    const double d = std::sqrt(d2);
    const double c1 = (lx * sn.x + ly * sn.y + lz * sn.z) / d;
    const double c2 = -(lx * tn.x + ly * tn.y + lz * tn.z) / d;
    if (c1 <= 0.0 || c2 <= 0.0) return 0.0;
    return sa * c1 * c2 / (kPi * d2);
}

std::vector<double> RadiositySolver::bounce_values(const PatchSet& sources,
                                                   const std::vector<double>& src_vals,
                                                   const PatchSet& targets, double reflectance,
                                                   const IVisibilityPolicy& visibility) const {
    const std::size_t ns = sources.size(), nt = targets.size();
    std::vector<double> out(nt, 0.0);
    if (ns == 0 || nt == 0 || src_vals.size() != ns) return out;
    const bool check = visibility.blocks_anything();
    const int nth = config_.num_threads;
#ifdef _OPENMP
    if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
    for (long long j = 0; j < (long long)nt; ++j) {
        const std::size_t jj = (std::size_t)j;
        const double tx = targets.cx_[jj], ty = targets.cy_[jj], tz = targets.cz_[jj];
        const double tnx = targets.nx_[jj], tny = targets.ny_[jj], tnz = targets.nz_[jj];
        double acc = 0.0;
        for (std::size_t i = 0; i < ns; ++i) {
            const double e = src_vals[i];
            if (e == 0.0) continue;
            const double lx = tx - sources.cx_[i];
            const double ly = ty - sources.cy_[i];
            const double lz = tz - sources.cz_[i];
            const double d2 = lx * lx + ly * ly + lz * lz;
            if (d2 < kEps * kEps) continue;
            const double d = std::sqrt(d2);
            const double c1 = (lx * sources.nx_[i] + ly * sources.ny_[i] + lz * sources.nz_[i]) / d;
            const double c2 = -(lx * tnx + ly * tny + lz * tnz) / d;
            if (c1 <= 0.0 || c2 <= 0.0) continue;
            if (check) {
                if (!visibility.is_visible(Vec2{sources.cx_[i], sources.cy_[i]}, Vec2{tx, ty}))
                    continue;
            }
            acc += e * reflectance * sources.area_[i] * c1 * c2 / (kPi * d2);
        }
        out[jj] = acc;
    }
    return out;
}

IndirectResult RadiositySolver::solve(const PatchSet& sources, const SeedMap& seeds,
                                      const TargetMap& targets,
                                      const IVisibilityPolicy& visibility) const {
    // Order origins deterministically (Python uses sorted()).
    std::vector<std::string> order;
    order.reserve(seeds.size());
    for (const auto& kv : seeds) order.push_back(kv.first);
    std::sort(order.begin(), order.end());
    const std::size_t n_src = sources.size();
    const std::size_t n_org = order.size();

    IndirectResult out;
    for (const auto& kv : targets) {
        std::map<std::string, std::vector<double>> per;
        for (const auto& o : order) per[o] = std::vector<double>(kv.second.size(), 0.0);
        out[kv.first] = std::move(per);
    }
    if (config_.num_bounces <= 0 || n_src == 0 || n_org == 0) return out;
    for (const auto& o : order) {
        if (seeds.at(o).size() != n_src) throw std::invalid_argument("patch layout mismatch");
    }

    // Reflectances per source.
    std::vector<double> rho(n_src);
    for (std::size_t i = 0; i < n_src; ++i) {
        const int s = sources.surface_[i];
        rho[i] = (s == 0) ? config_.wall_reflectance
                          : (s == 1) ? config_.floor_reflectance : config_.ceiling_reflectance;
    }

    // Unique-XY dedup (mirrors Python round(x,9)).
    std::unordered_map<XYKey, std::int64_t, XYHash> key_of;
    std::vector<Vec2> uniq;
    uniq.reserve(n_src + 64);
    std::vector<std::int64_t> src_idx(n_src);
    auto take = [&](double x, double y) -> std::int64_t {
        XYKey k{q9(x), q9(y)};
        auto it = key_of.find(k);
        if (it != key_of.end()) return it->second;
        const std::int64_t u = (std::int64_t)uniq.size();
        key_of.emplace(k, u);
        uniq.push_back(Vec2{x, y});
        return u;
    };
    for (std::size_t i = 0; i < n_src; ++i) src_idx[i] = take(sources.cx_[i], sources.cy_[i]);
    std::map<std::string, std::vector<std::int64_t>> tgt_idx;
    for (const auto& kv : targets) {
        std::vector<std::int64_t> ti;
        ti.reserve(kv.second.size());
        for (std::size_t i = 0; i < kv.second.size(); ++i)
            ti.push_back(take(kv.second.cx_[i], kv.second.cy_[i]));
        tgt_idx[kv.first] = std::move(ti);
    }
    const std::size_t mu = uniq.size();
    // mu x mu visibility, row-major vis[t*mu+i].
    std::vector<char> uni(mu * mu, 1);
    const bool use_vis = visibility.blocks_anything();
    if (use_vis) {
        const int nth = config_.num_threads;
#ifdef _OPENMP
        if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
        for (long long t = 0; t < (long long)mu; ++t) {
            for (std::size_t i = 0; i < mu; ++i) {
                if (i == (std::size_t)t) {
                    uni[(std::size_t)t * mu + i] = 1;
                    continue;
                }
                uni[(std::size_t)t * mu + i] =
                    visibility.is_visible(uniq[i], uniq[(std::size_t)t]) ? 1 : 0;
            }
        }
    }
    // src_vis slice + zero diagonal.
    std::vector<char> src_vis(use_vis ? n_src * n_src : 0);
    if (use_vis) {
        for (std::size_t t = 0; t < n_src; ++t)
            for (std::size_t i = 0; i < n_src; ++i) {
                char v = uni[(std::size_t)src_idx[t] * mu + (std::size_t)src_idx[i]];
                if (i == t) v = 0;
                src_vis[t * n_src + i] = v;
            }
    }

    const TangentFrames sframes =
        tangent_frames(sources.nx_, sources.ny_, sources.nz_);
    std::vector<double> src_ds(n_src);
    for (std::size_t i = 0; i < n_src; ++i) src_ds[i] = std::sqrt(std::max(sources.area_[i], kEps));

    // F matrix row-major F[i*n_src+t].
    std::vector<double> F(n_src * n_src, 0.0);
    {
        const int nth = config_.num_threads;
#ifdef _OPENMP
        if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
        for (long long t = 0; t < (long long)n_src; ++t) {
            const std::size_t tt = (std::size_t)t;
            const double tcx = sources.cx_[tt], tcy = sources.cy_[tt], tcz = sources.cz_[tt];
            const double tnx = sources.nx_[tt], tny = sources.ny_[tt], tnz = sources.nz_[tt];
            std::vector<double> g(n_src, 0.0);
            std::vector<char> close(n_src, 0);
            for (std::size_t i = 0; i < n_src; ++i) {
                if (i == tt) continue;
                const double lx = tcx - sources.cx_[i];
                const double ly = tcy - sources.cy_[i];
                const double lz = tcz - sources.cz_[i];
                const double d2 = lx * lx + ly * ly + lz * lz;
                if (d2 < kEps * kEps) continue;
                const double d = std::sqrt(d2);
                const double c1 =
                    (lx * sources.nx_[i] + ly * sources.ny_[i] + lz * sources.nz_[i]) / d;
                const double c2 = -(lx * tnx + ly * tny + lz * tnz) / d;
                if (c1 <= 0.0 || c2 <= 0.0) continue;
                if (use_vis && !src_vis[tt * n_src + i]) continue;
                g[i] = sources.area_[i] * c1 * c2 / (kPi * d2);
                const double thr = 2.0 * std::max(src_ds[i], src_ds[tt]);
                if (d < thr) close[i] = 1;
            }
            if (std::any_of(close.begin(), close.end(), [](char c) { return c; })) {
                refine_close(g, sources, sframes, Vec3{tcx, tcy, tcz}, Vec3{tnx, tny, tnz},
                             sources.area_[tt],
                             Vec3{sframes.t1x[tt], sframes.t1y[tt], sframes.t1z[tt]},
                             Vec3{sframes.t2x[tt], sframes.t2y[tt], sframes.t2z[tt]}, close);
                g[tt] = 0.0;
            }
            for (std::size_t i = 0; i < n_src; ++i) F[i * n_src + tt] = g[i];
        }
    }
    // Conservation.
    std::vector<double> conserve(n_src, 1.0);
    for (std::size_t i = 0; i < n_src; ++i) {
        double row = 0.0;
        for (std::size_t t = 0; t < n_src; ++t) row += F[i * n_src + t] * sources.area_[t];
        row /= std::max(sources.area_[i], kEps);
        const double c = 1.0 / std::max(row, kEps);
        conserve[i] = std::min(1.0, c);
    }
    for (std::size_t i = 0; i < n_src; ++i) {
        const double c = conserve[i];
        if (c == 1.0) continue;
        for (std::size_t t = 0; t < n_src; ++t) F[i * n_src + t] *= c;
    }

    // Seeds matrix row-major E[n_org*n_src].
    std::vector<double> E(n_org * n_src, 0.0);
    for (std::size_t k = 0; k < n_org; ++k) {
        const auto& v = seeds.at(order[k]);
        for (std::size_t i = 0; i < n_src; ++i) E[k * n_src + i] = v[i];
    }
    // Neumann iterations.
    std::vector<double> E2(n_org * n_src);
    const int iters = std::max(0, config_.num_bounces - 1);
    for (int it = 0; it < iters; ++it) {
        const int nth = config_.num_threads;
#ifdef _OPENMP
        if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
        for (long long k = 0; k < (long long)n_org; ++k) {
            for (std::size_t t = 0; t < n_src; ++t) {
                double acc = 0.0;
                for (std::size_t i = 0; i < n_src; ++i)
                    acc += E[(std::size_t)k * n_src + i] * rho[i] * F[i * n_src + t];
                E2[(std::size_t)k * n_src + t] = seeds.at(order[(std::size_t)k])[t] + acc;
            }
        }
        E.swap(E2);
    }

    // Targets.
    for (const auto& kv : targets) {
        const std::string& tid = kv.first;
        const PatchSet& tp = kv.second;
        const std::size_t n_tgt = tp.size();
        if (n_tgt == 0) continue;
        const TangentFrames tframes = tangent_frames(tp.nx_, tp.ny_, tp.nz_);
        const std::vector<std::int64_t>& ti = tgt_idx[tid];
        // G row-major n_tgt x n_src.
        std::vector<double> G(n_tgt * n_src, 0.0);
        {
            const int nth = config_.num_threads;
#ifdef _OPENMP
            if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
            for (long long j = 0; j < (long long)n_tgt; ++j) {
                const std::size_t jj = (std::size_t)j;
                const double tcx = tp.cx_[jj], tcy = tp.cy_[jj], tcz = tp.cz_[jj];
                const double tnx = tp.nx_[jj], tny = tp.ny_[jj], tnz = tp.nz_[jj];
                const double tds = std::sqrt(std::max(tp.area_[jj], kEps));
                std::vector<double> g(n_src, 0.0);
                std::vector<char> close(n_src, 0);
                for (std::size_t i = 0; i < n_src; ++i) {
                    const double lx = tcx - sources.cx_[i];
                    const double ly = tcy - sources.cy_[i];
                    const double lz = tcz - sources.cz_[i];
                    const double d2 = lx * lx + ly * ly + lz * lz;
                    if (d2 < kEps * kEps) continue;
                    const double d = std::sqrt(d2);
                    const double c1 =
                        (lx * sources.nx_[i] + ly * sources.ny_[i] + lz * sources.nz_[i]) / d;
                    const double c2 = -(lx * tnx + ly * tny + lz * tnz) / d;
                    if (c1 <= 0.0 || c2 <= 0.0) continue;
                    g[i] = sources.area_[i] * c1 * c2 / (kPi * d2);
                    const double thr = 2.0 * std::max(src_ds[i], tds);
                    if (d < thr) close[i] = 1;
                }
                if (std::any_of(close.begin(), close.end(), [](char c) { return c; })) {
                    refine_close(g, sources, sframes, Vec3{tcx, tcy, tcz}, Vec3{tnx, tny, tnz},
                                 tp.area_[jj],
                                 Vec3{tframes.t1x[jj], tframes.t1y[jj], tframes.t1z[jj]},
                                 Vec3{tframes.t2x[jj], tframes.t2y[jj], tframes.t2z[jj]}, close);
                }
                if (use_vis) {
                    for (std::size_t i = 0; i < n_src; ++i) {
                        const char v =
                            uni[(std::size_t)ti[jj] * mu + (std::size_t)src_idx[i]];
                        G[jj * n_src + i] = v ? g[i] : 0.0;
                    }
                } else {
                    for (std::size_t i = 0; i < n_src; ++i) G[jj * n_src + i] = g[i];
                }
            }
        }
        // E_tgt[k][j] = sum_i G[j,i]*conserve[i]*rho[i]*E[k,i]
        std::map<std::string, std::vector<double>>& per = out[tid];
        {
            const int nth = config_.num_threads;
#ifdef _OPENMP
            if (nth > 0) omp_set_num_threads(nth);
#pragma omp parallel for schedule(static)
#endif
            for (long long k = 0; k < (long long)n_org; ++k) {
                auto& vec = per[order[(std::size_t)k]];
                for (std::size_t j = 0; j < n_tgt; ++j) {
                    double acc = 0.0;
                    for (std::size_t i = 0; i < n_src; ++i)
                        acc += G[j * n_src + i] * conserve[i] * rho[i] *
                               E[(std::size_t)k * n_src + i];
                    vec[j] = acc;
                }
            }
        }
    }
    return out;
}

IndirectResult RadiositySolver::solve(
    const PatchSet& sources, const SeedMap& seeds, const TargetMap& targets,
    const IVisibilityPolicy& visibility, const std::vector<Vec2>&,
    const std::vector<std::int64_t>&, const std::vector<std::vector<std::int64_t>>&) const {
    // Precomputed indices are an optimization hint; the canonical path above
    // rebuilds them deterministically (same round(x,9) rule).
    return solve(sources, seeds, targets, visibility);
}

}  // namespace luxcore
