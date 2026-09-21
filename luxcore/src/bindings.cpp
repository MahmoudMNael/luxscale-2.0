// nanobind gateway for the LuxScale C++ physics core.
// Thin translation layer only: converts NumPy <-> C++ value objects,
// releases the GIL, then delegates to the OOP engines.

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include "luxcore/common.h"
#include "luxcore/direct_engine.h"
#include "luxcore/fixture.h"
#include "luxcore/geometry_engine.h"
#include "luxcore/ies_profile.h"
#include "luxcore/matrix_ops.h"
#include "luxcore/patch_set.h"
#include "luxcore/radiosity_solver.h"
#include "luxcore/vector_math.h"
#include "luxcore/visibility_policy.h"

namespace nb = nanobind;
using namespace nanobind::literals;
using namespace luxcore;

namespace {

using ArrayD = nb::ndarray<nb::numpy, double>;
using ArrayI32 = nb::ndarray<nb::numpy, std::int32_t>;
using ArrayI64 = nb::ndarray<nb::numpy, std::int64_t>;
using ArrayU8 = nb::ndarray<nb::numpy, uint8_t>;

std::vector<double> vec_from_1d(const ArrayD& a) {
    if (a.ndim() != 1) throw std::invalid_argument("expected 1-D array");
    const std::size_t n = a.shape(0);
    const double* p = static_cast<const double*>(a.data());
    return std::vector<double>(p, p + n);
}

std::vector<Vec2> vec2_from_2d(const ArrayD& a) {
    if (a.ndim() != 2 || a.shape(1) != 2) throw std::invalid_argument("expected (N,2) array");
    const std::size_t n = a.shape(0);
    const double* p = static_cast<const double*>(a.data());
    // nanobind/DLPack strides are in ELEMENTS (not bytes).
    const std::size_t stride = (std::size_t)a.stride(0);
    const std::size_t s1 = (std::size_t)a.stride(1);
    // Handle both C-contiguous and strided.
    std::vector<Vec2> out(n);
    if (s1 == 1 && stride == 2) {
        for (std::size_t i = 0; i < n; ++i) out[i] = Vec2{p[2 * i], p[2 * i + 1]};
    } else {
        for (std::size_t i = 0; i < n; ++i)
            out[i] = Vec2{*(p + i * stride), *(p + i * stride + s1)};
    }
    return out;
}

std::vector<Vec3> vec3_from_2d(const ArrayD& a) {
    if (a.ndim() != 2 || a.shape(1) != 3) throw std::invalid_argument("expected (N,3) array");
    const std::size_t n = a.shape(0);
    const double* p = static_cast<const double*>(a.data());
    std::vector<Vec3> out(n);
    const std::size_t s0 = (std::size_t)a.stride(0);
    const std::size_t s1 = (std::size_t)a.stride(1);
    for (std::size_t i = 0; i < n; ++i)
        out[i] = Vec3{*(p + i * s0), *(p + i * s0 + s1), *(p + i * s0 + 2 * s1)};
    return out;
}

PatchSet patchset_from_arrays(const ArrayD& centers, const ArrayD& normals, const ArrayD& areas,
                              const ArrayD& sizes, const ArrayI32& surface) {
    if (centers.ndim() != 2 || centers.shape(1) != 3) throw std::invalid_argument("centers (N,3)");
    const std::size_t n = centers.shape(0);
    PatchSet ps;
    ps.resize(n);
    const double* c = static_cast<const double*>(centers.data());
    const double* nn = static_cast<const double*>(normals.data());
    const double* ar = static_cast<const double*>(areas.data());
    const double* sz = static_cast<const double*>(sizes.data());
    const std::int32_t* sf = static_cast<const std::int32_t*>(surface.data());
    // DLPack strides are in elements; areas/sizes/surface are 1-D contiguous
    // by contract (bridge passes ascontiguousarray), so plain indexing is used.
    const std::size_t cs0 = (std::size_t)centers.stride(0);
    const std::size_t ns0 = (std::size_t)normals.stride(0);
    for (std::size_t i = 0; i < n; ++i) {
        ps.cx_[i] = *(c + i * cs0);
        ps.cy_[i] = *(c + i * cs0 + 1);
        ps.cz_[i] = *(c + i * cs0 + 2);
        ps.nx_[i] = *(nn + i * ns0);
        ps.ny_[i] = *(nn + i * ns0 + 1);
        ps.nz_[i] = *(nn + i * ns0 + 2);
        ps.area_[i] = ar[i];
        ps.size_[i] = sz[i];
        ps.surface_[i] = sf[i];
    }
    return ps;
}

nb::ndarray<nb::numpy, double> ndarray_2d(std::vector<double>&& flat, std::size_t n,
                                          std::size_t d) {
    double* data = new double[flat.size()];
    std::copy(flat.begin(), flat.end(), data);
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<double*>(p); });
    std::size_t shape[2] = {n, d};
    return nb::ndarray<nb::numpy, double>(data, 2, shape, owner);
}

nb::ndarray<nb::numpy, double> ndarray_1d(std::vector<double>&& v) {
    double* data = new double[v.size()];
    std::copy(v.begin(), v.end(), data);
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<double*>(p); });
    std::size_t shape[1] = {v.size()};
    return nb::ndarray<nb::numpy, double>(data, 1, shape, owner);
}

GridMeta gridmeta_from_dict(const nb::dict& d) {
    GridMeta m;
    auto get = [&](const char* k) -> double {
        if (d.contains(k)) return nb::cast<double>(d[k]);
        return 0.0;
    };
    m.spacing = get("spacing");
    m.spacing_x = get("spacingX");
    m.spacing_y = get("spacingY");
    m.nx = get("nx");
    m.ny = get("ny");
    m.dx = get("dx");
    m.dy = get("dy");
    m.xmin = get("xmin");
    m.xmax = get("xmax");
    m.ymin = get("ymin");
    m.ymax = get("ymax");
    m.border = get("border");
    return m;
}

nb::dict dict_from_gridmeta(const GridMeta& m) {
    nb::dict d;
    d["spacing"] = m.spacing;
    d["spacingX"] = m.spacing_x;
    d["spacingY"] = m.spacing_y;
    d["nx"] = m.nx;
    d["ny"] = m.ny;
    d["dx"] = m.dx;
    d["dy"] = m.dy;
    d["xmin"] = m.xmin;
    d["xmax"] = m.xmax;
    d["ymin"] = m.ymin;
    d["ymax"] = m.ymax;
    d["border"] = m.border;
    return d;
}

WallDef walldef_from_dict(const nb::dict& d) {
    WallDef w;
    w.id = nb::cast<std::string>(d["id"]);
    auto s = nb::cast<std::vector<double>>(d["start"]);
    auto e = nb::cast<std::vector<double>>(d["end"]);
    auto n = nb::cast<std::vector<double>>(d["normal"]);
    w.start = Vec2{s[0], s[1]};
    w.end = Vec2{e[0], e[1]};
    w.length = nb::cast<double>(d["length"]);
    w.normal = Vec2{n[0], n[1]};
    w.height = nb::cast<double>(d["height"]);
    return w;
}

nb::tuple patches_to_arrays(const std::vector<Patch>& patches) {
    std::vector<double> c, nrm, ar, sz;
    c.reserve(patches.size() * 3);
    nrm.reserve(patches.size() * 3);
    ar.reserve(patches.size());
    sz.reserve(patches.size());
    for (const auto& p : patches) {
        c.push_back(p.center.x);
        c.push_back(p.center.y);
        c.push_back(p.center.z);
        nrm.push_back(p.normal.x);
        nrm.push_back(p.normal.y);
        nrm.push_back(p.normal.z);
        ar.push_back(p.area);
        sz.push_back(p.size);
    }
    return nb::make_tuple(ndarray_2d(std::move(c), patches.size(), 3),
                          ndarray_2d(std::move(nrm), patches.size(), 3), ndarray_1d(std::move(ar)),
                          ndarray_1d(std::move(sz)));
}

}  // namespace

NB_MODULE(luxcore, m) {
    m.attr("__version__") = "2.0.0";
#ifdef _OPENMP
    m.attr("has_openmp") = true;
#else
    m.attr("has_openmp") = false;
#endif

    m.def("set_threads", [](int n) { return ThreadConfig::apply(n); }, "n"_a = 0);
    m.def("get_threads", [] { return ThreadConfig::current_max(); });
    m.def("backend", [] { return std::string("luxcore-cpp-nanobind-openmp"); });

    // ---- IES ----
    nb::class_<IesProfile>(m, "IesProfile")
        .def("__init__",
             [](IesProfile* self, ArrayD v, ArrayD h, ArrayD table_flat, int nv, int nh,
                double mult, double bf, double blf, double fs, double w, double l, double hh) {
                 auto vv = vec_from_1d(v);
                 auto hhv = vec_from_1d(h);
                 auto flat = vec_from_1d(table_flat);
                 std::vector<std::vector<double>> t((std::size_t)nv,
                                                    std::vector<double>((std::size_t)nh));
                 for (int i = 0; i < nv; ++i)
                     for (int j = 0; j < nh; ++j)
                         t[(std::size_t)i][(std::size_t)j] = flat[(std::size_t)i * (std::size_t)nh +
                                                                  (std::size_t)j];
                 new (self) IesProfile(vv, hhv, t, mult, bf, blf, fs, w, l, hh);
             },
             "vertical"_a, "horizontal"_a, "table_flat"_a, "nv"_a, "nh"_a, "multiplier"_a,
             "ballast"_a, "ballast_lamp"_a, "flux_scale"_a, "width"_a, "length"_a, "height"_a)
        .def_static("load", [](const std::string& text) {
            // No GIL release: the returned IesProfile needs the GIL for
            // Python wrapper construction (parsing itself is sub-ms).
            return IesProfile::load(text);
        })
        .def("sample",
             [](const IesProfile& self, double th, double ph) {
                 nb::gil_scoped_release r;
                 return self.sample(th, ph);
             })
        .def("zonal_lumens", &IesProfile::zonal_lumens)
        .def_prop_ro("multiplier", &IesProfile::multiplier)
        .def_prop_ro("flux_scale", &IesProfile::flux_scale)
        .def_prop_ro("width", &IesProfile::width)
        .def_prop_ro("length", &IesProfile::length)
        .def_prop_ro("height", &IesProfile::height);

    m.def("zonal_lumens",
          [](ArrayD v, ArrayD h, ArrayD flat, int nv, int nh) {
              nb::gil_scoped_release r;
              auto vv = vec_from_1d(v);
              auto hhv = vec_from_1d(h);
              auto fl = vec_from_1d(flat);
              std::vector<std::vector<double>> t((std::size_t)nv,
                                                 std::vector<double>((std::size_t)nh));
              for (int i = 0; i < nv; ++i)
                  for (int j = 0; j < nh; ++j)
                      t[(std::size_t)i][(std::size_t)j] =
                          fl[(std::size_t)i * (std::size_t)nh + (std::size_t)j];
              IesProfile p(vv, hhv, t, 1.0, 1.0, 1.0, 1.0, 0, 0, 0);
              return p.zonal_lumens();
          });

    // ---- vector math ----
    m.def("angle_deg",
          [](std::vector<double> a, std::vector<double> b) {
              return VectorMath::angle_deg(Vec3{a[0], a[1], a[2]}, Vec3{b[0], b[1], b[2]});
          });
    m.def("wrap_deg", &VectorMath::wrap_deg);
    m.def("en12464_spacing", &VectorMath::en12464_spacing);
    m.def("perimeter_border", &VectorMath::perimeter_border);

    // ---- fixture ----
    // NOTE: nb::gil_scoped_release must NEVER span nb::capsule/ndarray
    // construction (those allocate Python objects and need the GIL).
    // Pattern everywhere below: compute under release, convert after.
    m.def("luminous_elements",
          [](std::vector<double> pos, double rot, double len, double wid) {
              std::vector<Vec3> els;
              {
                  nb::gil_scoped_release r;
                  FixtureDef f{{pos[0], pos[1], pos[2]}, {0, 0, -1}, rot};
                  els = LuminousOpening::elements(f, len, wid);
              }
              std::vector<double> flat;
              flat.reserve(els.size() * 3);
              for (auto& e : els) {
                  flat.push_back(e.x);
                  flat.push_back(e.y);
                  flat.push_back(e.z);
              }
              return ndarray_2d(std::move(flat), els.size(), 3);
          });
    m.def("luminous_corners",
          [](std::vector<double> pos, double rot, double len, double wid) {
              FixtureDef f{{pos[0], pos[1], pos[2]}, {0, 0, -1}, rot};
              auto cs = LuminousOpening::corners(f, len, wid);
              std::vector<double> flat;
              for (auto& e : cs) {
                  flat.push_back(e.x);
                  flat.push_back(e.y);
                  flat.push_back(e.z);
              }
              return ndarray_2d(std::move(flat), cs.size(), 3);
          });

    // ---- direct ----
    nb::class_<DirectEngine>(m, "DirectEngine")
        .def("__init__",
             [](DirectEngine* self, double c0, int threads, const IesProfile& ies) {
                 new (self) DirectEngine(DirectConfig{c0, threads}, &ies);
             },
             "c0_offset"_a = 0.0, "threads"_a = 0, "ies"_a)
        .def("compute",
             [](const DirectEngine& self, std::vector<double> pos, std::vector<double> aim,
                double rot, ArrayD centers, ArrayD normals, ArrayD origins, ArrayD ring,
                bool convex) {
                 auto vc = vec3_from_2d(centers);
                 auto vn = vec3_from_2d(normals);
                 auto org = vec3_from_2d(origins);
                 std::vector<Vec2> rv;
                 if (!convex && ring.ndim() == 2) rv = vec2_from_2d(ring);
                 PatchSet ps;
                 ps.resize(vc.size());
                 for (std::size_t i = 0; i < vc.size(); ++i) {
                     ps.cx_[i] = vc[i].x;
                     ps.cy_[i] = vc[i].y;
                     ps.cz_[i] = vc[i].z;
                     ps.nx_[i] = vn[i].x;
                     ps.ny_[i] = vn[i].y;
                     ps.nz_[i] = vn[i].z;
                     ps.area_[i] = 1.0;
                 }
                 FixtureDef f{{pos[0], pos[1], pos[2]}, {aim[0], aim[1], aim[2]}, rot};
                 auto pol = VisibilityPolicyFactory::create(convex, std::move(rv));
                 std::vector<double> out;
                 {
                     nb::gil_scoped_release release;
                     out = self.compute(f, ps, org, *pol);
                 }
                 return ndarray_1d(std::move(out));
             });

    m.def(
        "direct_compute",
        [](ArrayD pos, ArrayD aim, double rot, double c0, const IesProfile& ies, ArrayD centers,
           ArrayD normals, ArrayD origins, ArrayD ring, bool convex, int threads) {
            auto vp = vec_from_1d(pos);
            auto va = vec_from_1d(aim);
            auto vc = vec3_from_2d(centers);
            auto vn = vec3_from_2d(normals);
            auto org = vec3_from_2d(origins);
            std::vector<Vec2> rv;
            if (!convex && ring.ndim() == 2 && ring.shape(0) > 0) rv = vec2_from_2d(ring);
            FixtureDef f{{vp[0], vp[1], vp[2]}, {va[0], va[1], va[2]}, rot};
            PatchSet ps;
            ps.resize(vc.size());
            for (std::size_t i = 0; i < vc.size(); ++i) {
                ps.cx_[i] = vc[i].x;
                ps.cy_[i] = vc[i].y;
                ps.cz_[i] = vc[i].z;
                ps.nx_[i] = vn[i].x;
                ps.ny_[i] = vn[i].y;
                ps.nz_[i] = vn[i].z;
                ps.area_[i] = 1.0;
            }
            auto pol = VisibilityPolicyFactory::create(convex, std::move(rv));
            DirectEngine eng(DirectConfig{c0, threads}, &ies);
            std::vector<double> out;
            {
                nb::gil_scoped_release release;
                out = eng.compute(f, ps, org, *pol);
            }
            return ndarray_1d(std::move(out));
        },
        "pos"_a, "aim"_a, "rotation"_a, "c0"_a, "ies"_a, "centers"_a, "normals"_a, "origins"_a,
        "ring"_a, "convex"_a, "threads"_a = 0);

    // ---- visibility batch ----
    m.def(
        "union_visibility",
        [](ArrayD uniq, ArrayD ring, bool convex, bool self_occlusion, int threads) {
            auto u = vec2_from_2d(uniq);
            std::vector<Vec2> rv;
            if (!convex && ring.ndim() == 2 && ring.shape(0) > 0) rv = vec2_from_2d(ring);
            auto pol = VisibilityPolicyFactory::create(convex, std::move(rv));
            std::vector<char> mask;
            {
                nb::gil_scoped_release release;
                mask = UnionVisibilityBuilder::build(u, *pol, self_occlusion, threads);
            }
            uint8_t* data = new uint8_t[mask.size()];
            for (std::size_t i = 0; i < mask.size(); ++i) data[i] = (uint8_t)mask[i];
            nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<uint8_t*>(p); });
            std::size_t shape[2] = {u.size(), u.size()};
            return nb::ndarray<nb::numpy, uint8_t>(data, 2, shape, owner);
        },
        "uniq"_a, "ring"_a, "convex"_a, "self_occlusion"_a = true, "threads"_a = 0);

    // ---- radiosity ----
    nb::class_<RadiositySolver>(m, "RadiositySolver")
        .def("__init__",
             [](RadiositySolver* self, double wr, double fr, double cr, int bounces, int threads) {
                 new (self) RadiositySolver(RadiosityConfig{wr, fr, cr, bounces, threads});
             },
             "wall"_a, "floor"_a, "ceiling"_a, "bounces"_a, "threads"_a = 0)
        .def(
            "solve",
            [](const RadiositySolver& self, ArrayD sc, ArrayD sn, ArrayD sa, ArrayI32 ss,
               nb::list origin_ids, ArrayD seeds, nb::list target_ids, nb::list target_centers,
               nb::list target_normals, nb::list target_areas,                nb::list target_surface, ArrayD ring,
               bool convex) {
                PatchSet src = patchset_from_arrays(sc, sn, sa, sa, ss);
                // areas passed twice (sa) — fix: areas + sizes both sa; sizes unused in solver
                auto oids = nb::cast<std::vector<std::string>>(origin_ids);
                auto tids = nb::cast<std::vector<std::string>>(target_ids);
                const std::size_t no = oids.size();
                const double* sp = static_cast<const double*>(seeds.data());
                const std::size_t s0 = (std::size_t)seeds.stride(0);
                const std::size_t s1 = (std::size_t)seeds.stride(1);
                SeedMap sm;
                for (std::size_t k = 0; k < no; ++k) {
                    std::vector<double> v(src.size());
                    for (std::size_t i = 0; i < src.size(); ++i) v[i] = *(sp + k * s0 + i * s1);
                    sm[oids[k]] = std::move(v);
                }
                TargetMap tm;
                for (std::size_t t = 0; t < tids.size(); ++t) {
                    ArrayD tc = nb::cast<ArrayD>(target_centers[t]);
                    ArrayD tn = nb::cast<ArrayD>(target_normals[t]);
                    ArrayD ta = nb::cast<ArrayD>(target_areas[t]);
                    int surf = nb::cast<int>(target_surface[t]);
                    auto vc = vec3_from_2d(tc);
                    auto vn = vec3_from_2d(tn);
                    auto va = vec_from_1d(ta);
                    PatchSet ps;
                    ps.resize(vc.size());
                    for (std::size_t i = 0; i < vc.size(); ++i) {
                        ps.cx_[i] = vc[i].x;
                        ps.cy_[i] = vc[i].y;
                        ps.cz_[i] = vc[i].z;
                        ps.nx_[i] = vn[i].x;
                        ps.ny_[i] = vn[i].y;
                        ps.nz_[i] = vn[i].z;
                        ps.area_[i] = va[i];
                        ps.size_[i] = 1.0;
                        ps.surface_[i] = surf;
                    }
                    tm[tids[t]] = std::move(ps);
                }
                std::vector<Vec2> rv;
                if (!convex && ring.ndim() == 2 && ring.shape(0) > 0) rv = vec2_from_2d(ring);
                auto pol = VisibilityPolicyFactory::create(convex, std::move(rv));
                IndirectResult res;
                {
                    nb::gil_scoped_release release;
                    res = self.solve(src, sm, tm, *pol);
                }
                nb::dict out;
                for (auto& kv : res) {
                    nb::dict per;
                    for (auto& kv2 : kv.second) per[nb::str(kv2.first.c_str())] =
                        ndarray_1d(std::vector<double>(kv2.second));
                    out[nb::str(kv.first.c_str())] = per;
                }
                return out;
            })
        .def("bounce_values",
             [](const RadiositySolver& self, ArrayD sc, ArrayD sn, ArrayD sa, ArrayD vals, ArrayD tc,
                ArrayD tn, double rho, ArrayD ring, bool convex) {
                 auto vsc = vec3_from_2d(sc);
                 auto vsn = vec3_from_2d(sn);
                 auto vsa = vec_from_1d(sa);
                 auto vtc = vec3_from_2d(tc);
                 auto vtn = vec3_from_2d(tn);
                 auto vv = vec_from_1d(vals);
                 std::vector<Vec2> rv;
                 if (!convex && ring.ndim() == 2 && ring.shape(0) > 0) rv = vec2_from_2d(ring);
                 PatchSet src;
                 src.resize(vsc.size());
                 for (std::size_t i = 0; i < vsc.size(); ++i) {
                     src.cx_[i] = vsc[i].x;
                     src.cy_[i] = vsc[i].y;
                     src.cz_[i] = vsc[i].z;
                     src.nx_[i] = vsn[i].x;
                     src.ny_[i] = vsn[i].y;
                     src.nz_[i] = vsn[i].z;
                     src.area_[i] = vsa[i];
                 }
                 PatchSet tgt;
                 tgt.resize(vtc.size());
                 for (std::size_t i = 0; i < vtc.size(); ++i) {
                     tgt.cx_[i] = vtc[i].x;
                     tgt.cy_[i] = vtc[i].y;
                     tgt.cz_[i] = vtc[i].z;
                     tgt.nx_[i] = vtn[i].x;
                     tgt.ny_[i] = vtn[i].y;
                     tgt.nz_[i] = vtn[i].z;
                     tgt.area_[i] = 1.0;
                 }
                 auto pol = VisibilityPolicyFactory::create(convex, std::move(rv));
                 std::vector<double> out;
                 {
                     nb::gil_scoped_release release;
                     out = self.bounce_values(src, vv, tgt, rho, *pol);
                 }
                 return ndarray_1d(std::move(out));
             });

    // ---- geometry ----
    m.def(
        "solver_plan_grid",
        [](ArrayD bbox, nb::list rings, double z, int surface, double cell, std::vector<double> n) {
            auto bb = vec2_from_2d(bbox);
            std::vector<std::vector<Vec2>> rr;
            for (auto h : rings) rr.push_back(vec2_from_2d(nb::cast<ArrayD>(h)));
            Vec3 nn{n[0], n[1], n[2]};
            auto res = GeometryEngine::solver_plan_grid(bb, rr, z, surface_type_from_int(surface),
                                                        cell, nn);
            return nb::make_tuple(patches_to_arrays(res.patches), dict_from_gridmeta(res.meta));
        });
    m.def("solver_wall_grid", [](nb::dict wall, double cell) {
        WallDef w = walldef_from_dict(wall);
        auto res = GeometryEngine::solver_wall_grid(w, cell);
        return nb::make_tuple(patches_to_arrays(res.patches), dict_from_gridmeta(res.meta));
    });
    m.def("wall_grid", [](nb::dict wall, double border, bool neglect) {
        WallDef w = walldef_from_dict(wall);
        auto res = GeometryEngine::wall_grid(w, border, neglect);
        return nb::make_tuple(patches_to_arrays(res.patches), dict_from_gridmeta(res.meta));
    });
    m.def(
        "build_plan_weights",
        [](ArrayD fc, ArrayD fn, nb::dict fm, ArrayD ec, ArrayD en, double edx, double edy) {
            auto vfc = vec3_from_2d(fc);
            auto vfn = vec3_from_2d(fn);
            auto vec = vec3_from_2d(ec);
            auto ven = vec3_from_2d(en);
            std::vector<Patch> full(vfc.size()), ev(vec.size());
            for (std::size_t i = 0; i < vfc.size(); ++i)
                full[i] = Patch{vfc[i], vfn[i], 1.0, 1.0, SurfaceType::Floor};
            for (std::size_t i = 0; i < vec.size(); ++i)
                ev[i] = Patch{vec[i], ven[i], 1.0, 1.0, SurfaceType::Floor};
            GridMeta gm = gridmeta_from_dict(fm);
            CsrWeights w = GeometryEngine::build_plan_interp_weights(full, gm, ev, edx, edy);
            std::vector<double> dp(w.indptr.begin(), w.indptr.end());
            std::vector<double> di(w.indices.begin(), w.indices.end());
            return nb::make_tuple(ndarray_1d(std::move(dp)), ndarray_1d(std::move(di)),
                                  ndarray_1d(std::vector<double>(w.data)), (std::int64_t)w.n_eval,
                                  (std::int64_t)w.n_full);
        });
    m.def(
        "build_wall_weights",
        [](nb::dict wall, ArrayD fc, ArrayD fn, nb::dict fm, ArrayD ec, ArrayD en, double eds,
           double edz) {
            WallDef wdef = walldef_from_dict(wall);
            auto vfc = vec3_from_2d(fc);
            auto vfn = vec3_from_2d(fn);
            auto vec = vec3_from_2d(ec);
            auto ven = vec3_from_2d(en);
            std::vector<Patch> full(vfc.size()), ev(vec.size());
            for (std::size_t i = 0; i < vfc.size(); ++i)
                full[i] = Patch{vfc[i], vfn[i], 1.0, 1.0, SurfaceType::Wall};
            for (std::size_t i = 0; i < vec.size(); ++i)
                ev[i] = Patch{vec[i], ven[i], 1.0, 1.0, SurfaceType::Wall};
            GridMeta gm = gridmeta_from_dict(fm);
            CsrWeights w =
                GeometryEngine::build_wall_interp_weights(wdef, full, gm, ev, eds, edz);
            std::vector<double> dp(w.indptr.begin(), w.indptr.end());
            std::vector<double> di(w.indices.begin(), w.indices.end());
            return nb::make_tuple(ndarray_1d(std::move(dp)), ndarray_1d(std::move(di)),
                                  ndarray_1d(std::vector<double>(w.data)), (std::int64_t)w.n_eval,
                                  (std::int64_t)w.n_full);
        });
    m.def("apply_weights", [](ArrayD vals, ArrayD indptr, ArrayD indices, ArrayD data,
                              std::int64_t n_eval, std::int64_t n_full) {
        auto v = vec_from_1d(vals);
        auto ip = vec_from_1d(indptr);
        auto ii = vec_from_1d(indices);
        auto dd = vec_from_1d(data);
        CsrWeights w;
        w.n_eval = n_eval;
        w.n_full = n_full;
        w.indptr.reserve(ip.size());
        w.indices.reserve(ii.size());
        for (double x : ip) w.indptr.push_back((std::int64_t)std::llround(x));
        for (double x : ii) w.indices.push_back((std::int64_t)std::llround(x));
        w.data = dd;
        auto out = GeometryEngine::apply_weights(v, w);
        return ndarray_1d(std::move(out));
    });

    // ---- matrix ----
    m.def("sum_matrices", [](nb::list mats) {
        std::vector<std::vector<double>> in;
        for (auto h : mats) in.push_back(vec_from_1d(nb::cast<ArrayD>(h)));
        return ndarray_1d(MatrixOps::sum(in));
    });
    m.def("scale_vector", [](ArrayD v, double f) {
        auto vv = vec_from_1d(v);
        return ndarray_1d(MatrixOps::scale(vv, f));
    });
}
