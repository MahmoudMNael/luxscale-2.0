#pragma once
/// Shared POD types for the LuxScale C++ physics core.
/// Plain structs only — behaviour lives in engine classes.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace luxcore {

inline constexpr double kEps = 1e-9;
inline constexpr double kPi = 3.14159265358979323846;
inline constexpr double kDegToRad = kPi / 180.0;
inline constexpr double kRadToDeg = 180.0 / kPi;

/// 2D point (plan view).
struct Vec2 {
    double x{0.0};
    double y{0.0};
};

/// 3D point / vector.
struct Vec3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

/// Surface classification mirroring Python Patch.surface_type.
enum class SurfaceType : std::int32_t { Wall = 0, Floor = 1, Ceiling = 2 };

inline SurfaceType surface_type_from_int(int v) {
    if (v == 1) return SurfaceType::Floor;
    if (v == 2) return SurfaceType::Ceiling;
    return SurfaceType::Wall;
}

/// Grid metadata shared by solver / evaluation meshes.
struct GridMeta {
    double spacing{0.0};
    double spacing_x{0.0};
    double spacing_y{0.0};
    double nx{0.0};
    double ny{0.0};
    double dx{0.0};
    double dy{0.0};
    double xmin{0.0};
    double xmax{0.0};
    double ymin{0.0};
    double ymax{0.0};
    double border{0.0};
};

/// CSR interpolation weights (solver mesh -> eval mesh).
struct CsrWeights {
    std::vector<std::int64_t> indptr;   // size n_eval + 1
    std::vector<std::int64_t> indices;  // size nnz
    std::vector<double> data;           // size nnz
    std::int64_t n_eval{0};
    std::int64_t n_full{0};
};

/// Wall definition (mirrors Python Wall, without string id).
struct WallDef {
    std::string id;
    Vec2 start{0.0, 0.0};
    Vec2 end{0.0, 0.0};
    double length{0.0};
    Vec2 normal{0.0, 0.0};
    double height{0.0};
};

}  // namespace luxcore
