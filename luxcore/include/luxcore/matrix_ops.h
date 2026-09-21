#pragma once
/// Trivially parallel element-wise matrix helpers.

#include <vector>

namespace luxcore {

class MatrixOps final {
  public:
    MatrixOps() = delete;
    static std::vector<double> sum(const std::vector<std::vector<double>>& matrices);
    static std::vector<double> scale(const std::vector<double>& values, double factor);
};

class ThreadConfig final {
  public:
    ThreadConfig() = delete;
    /// Resolve requested thread count (0/negative = auto = omp_get_max_threads).
    static int resolve(int requested);
    /// Apply to OpenMP runtime; returns effective count.
    static int apply(int requested);
    static int current_max();
};

}  // namespace luxcore
