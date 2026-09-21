#include "luxcore/matrix_ops.h"

#include <stdexcept>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace luxcore {

std::vector<double> MatrixOps::sum(const std::vector<std::vector<double>>& matrices) {
    if (matrices.empty()) return {};
    const std::size_t n = matrices[0].size();
    std::vector<double> out(n, 0.0);
    for (const auto& m : matrices) {
        if (m.size() != n) throw std::invalid_argument("patch layout mismatch");
        for (std::size_t i = 0; i < n; ++i) out[i] += m[i];
    }
    return out;
}

std::vector<double> MatrixOps::scale(const std::vector<double>& values, double factor) {
    std::vector<double> out(values.size());
#ifdef _OPENMP
#pragma omp parallel for schedule(static)
#endif
    for (long long i = 0; i < (long long)values.size(); ++i) out[(std::size_t)i] = values[(std::size_t)i] * factor;
    return out;
}

int ThreadConfig::resolve(int requested) {
    if (requested > 0) return requested;
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

int ThreadConfig::apply(int requested) {
    const int n = resolve(requested);
#ifdef _OPENMP
    omp_set_num_threads(n);
#endif
    return n;
}

int ThreadConfig::current_max() { return resolve(0); }

}  // namespace luxcore
