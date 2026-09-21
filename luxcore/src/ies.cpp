#include "luxcore/ies_profile.h"

#include <cmath>
#include <sstream>
#include <stdexcept>

#include "luxcore/common.h"
#include "luxcore/vector_math.h"

namespace luxcore {

IesProfile::IesProfile(std::vector<double> vertical_angles,
                       std::vector<double> horizontal_angles,
                       std::vector<std::vector<double>> candela_table, double multiplier,
                       double ballast_factor, double ballast_lamp_factor, double flux_scale,
                       double width, double length, double height)
    : vertical_(std::move(vertical_angles)),
      horizontal_(std::move(horizontal_angles)),
      table_(std::move(candela_table)),
      multiplier_(multiplier),
      ballast_(ballast_factor),
      ballast_lamp_(ballast_lamp_factor),
      flux_scale_(flux_scale),
      width_(width),
      length_(length),
      height_(height) {
    if (vertical_.empty() || horizontal_.empty() || table_.size() != vertical_.size())
        throw std::invalid_argument("IES candela table is missing or incomplete.");
}

IesProfile IesProfile::load(const std::string& ies_text) {
    // Mirror Python load_ies() exactly (whitespace/commas, TILT=NONE, Type C).
    std::string stripped;
    stripped.reserve(ies_text.size());
    for (char c : ies_text) {
        if (c != '\r') stripped.push_back(c);
    }
    bool blank = true;
    for (char c : stripped) {
        if (c != ' ' && c != '\n' && c != '\t') {
            blank = false;
            break;
        }
    }
    if (blank) throw std::invalid_argument("IES candela table is missing or incomplete.");

    std::vector<std::string> lines;
    {
        std::string cur;
        for (char c : stripped) {
            if (c == '\n') {
                lines.push_back(cur);
                cur.clear();
            } else {
                cur.push_back(c);
            }
        }
        lines.push_back(cur);
    }
    int tilt_at = -1;
    for (std::size_t i = 0; i < lines.size(); ++i) {
        std::string s = lines[i];
        std::size_t p = s.find_first_not_of(" \t");
        std::string t = (p == std::string::npos) ? "" : s.substr(p);
        std::string up;
        up.reserve(t.size());
        for (char c : t) up.push_back((char)std::toupper((unsigned char)c));
        if (up.rfind("TILT", 0) == 0) {
            tilt_at = (int)i;
            break;
        }
    }
    if (tilt_at < 0) throw std::invalid_argument("IES file must declare TILT=NONE.");
    {
        std::string line = lines[(std::size_t)tilt_at];
        auto eq = line.find('=');
        std::string val = (eq == std::string::npos) ? line : line.substr(eq + 1);
        std::size_t a = val.find_first_not_of(" \t");
        std::size_t b = val.find_last_not_of(" \t");
        std::string v = (a == std::string::npos) ? "" : val.substr(a, b - a + 1);
        std::string up;
        for (char c : v) up.push_back((char)std::toupper((unsigned char)c));
        if (up != "NONE") throw std::invalid_argument("IES file must declare TILT=NONE.");
    }
    std::vector<double> nums;
    for (std::size_t i = (std::size_t)tilt_at + 1; i < lines.size(); ++i) {
        std::string line = lines[i];
        for (char& c : line)
            if (c == ',') c = ' ';
        std::istringstream ss(line);
        std::string tok;
        while (ss >> tok) {
            try {
                nums.push_back(std::stod(tok));
            } catch (...) {
                throw std::invalid_argument("IES candela table is missing or incomplete.");
            }
        }
    }
    if (nums.size() < 13)
        throw std::invalid_argument("IES candela table is missing or incomplete.");
    const int n_v = (int)nums[3], n_h = (int)nums[4];
    if (n_v < 1 || n_h < 1)
        throw std::invalid_argument("IES candela table is missing or incomplete.");
    if ((int)nums[5] != 1)
        throw std::invalid_argument("IES photometric type must be Type C (1).");
    const std::size_t needed = (std::size_t)13 + (std::size_t)n_v + (std::size_t)n_h +
                               (std::size_t)n_v * (std::size_t)n_h;
    if (nums.size() < needed)
        throw std::invalid_argument("IES candela table is missing or incomplete.");

    std::size_t k = 13;
    std::vector<double> vertical(nums.begin() + (std::ptrdiff_t)k,
                                nums.begin() + (std::ptrdiff_t)(k + (std::size_t)n_v));
    k += (std::size_t)n_v;
    std::vector<double> horizontal(nums.begin() + (std::ptrdiff_t)k,
                                  nums.begin() + (std::ptrdiff_t)(k + (std::size_t)n_h));
    k += (std::size_t)n_h;
    std::vector<double> raw(nums.begin() + (std::ptrdiff_t)k,
                            nums.begin() + (std::ptrdiff_t)(k + (std::size_t)n_v * (std::size_t)n_h));
    std::vector<std::vector<double>> table((std::size_t)n_v, std::vector<double>((std::size_t)n_h));
    std::size_t q = 0;
    for (int h = 0; h < n_h; ++h)
        for (int v = 0; v < n_v; ++v) table[(std::size_t)v][(std::size_t)h] = raw[q++];

    const double feet = ((int)nums[6] == 1) ? 0.3048 : 1.0;
    const double lamps = nums[0], lumens = nums[1], multiplier = nums[2];
    // zonal lumens (same formula as Python _zonal_lumens)
    double flux = 0.0;
    {
        std::vector<double> dphi;
        if (n_h == 1) {
            dphi.push_back(2.0 * kPi);
        } else {
            for (int j = 0; j < n_h; ++j) {
                double step = std::fmod(horizontal[(j + 1) % n_h] - horizontal[j], 360.0);
                if (step < 0) step += 360.0;
                if (step == 0.0) step = 360.0 / n_h;
                dphi.push_back(step * kDegToRad);
            }
        }
        if (n_v >= 2 && n_h >= 1) {
            for (int i = 0; i < n_v - 1; ++i) {
                const double band = std::cos(vertical[(std::size_t)i] * kDegToRad) -
                                    std::cos(vertical[(std::size_t)i + 1] * kDegToRad);
                for (int j = 0; j < n_h; ++j) {
                    const double dph = (n_h > 1) ? dphi[(std::size_t)j] : dphi[0];
                    flux += 0.5 * (table[(std::size_t)i][(std::size_t)j] +
                                   table[(std::size_t)i + 1][(std::size_t)j]) *
                            dph * band;
                }
            }
        }
    }
    const double flux_total = flux * multiplier;
    double flux_scale = 1.0;
    if (lumens > 0 && flux_total > kEps) flux_scale = (lamps * lumens) / flux_total;
    return IesProfile(vertical, horizontal, table, multiplier, nums[10], nums[11], flux_scale,
                      std::fabs(nums[7]) * feet, std::fabs(nums[8]) * feet,
                      std::fabs(nums[9]) * feet);
}

void IesProfile::bracket(const std::vector<double>& angles, double value, int& i0, int& i1,
                         double& t) {
    if (value <= angles[0]) {
        i0 = 0;
        i1 = 0;
        t = 0.0;
        return;
    }
    if (value >= angles.back()) {
        i0 = i1 = (int)angles.size() - 1;
        t = 0.0;
        return;
    }
    for (std::size_t i = 0; i + 1 < angles.size(); ++i) {
        if (angles[i] <= value && value <= angles[i + 1]) {
            const double span = angles[i + 1] - angles[i];
            t = (std::fabs(span) < kEps) ? 0.0 : (value - angles[i]) / span;
            i0 = (int)i;
            i1 = (int)i + 1;
            return;
        }
    }
    i0 = i1 = (int)angles.size() - 1;
    t = 0.0;
}

void IesProfile::phi_bracket(const std::vector<double>& angles, double phi, int& i0, int& i1,
                             double& t) {
    phi = VectorMath::wrap_deg(phi);
    const std::size_t n = angles.size();
    const double step = (n > 1) ? (angles.back() - angles.front()) / (n - 1) : 0.0;
    const bool circular = ((angles.front() + 360.0) - angles.back()) <= step * 1.5 + kEps;
    if (!circular) {
        bracket(angles, phi, i0, i1, t);
        return;
    }
    std::vector<double> extended = angles;
    extended.push_back(angles.front() + 360.0);
    const double sample = (phi >= angles.front()) ? phi : phi + 360.0;
    bracket(extended, sample, i0, i1, t);
    i0 = i0 % (int)n;
    i1 = i1 % (int)n;
}

double IesProfile::sample(double theta_vertical_deg, double phi_horizontal_deg) const {
    if (theta_vertical_deg > vertical_.back() + kEps) return 0.0;
    int iv0, iv1;
    double tv;
    bracket(vertical_, theta_vertical_deg, iv0, iv1, tv);
    const double sc = scale();
    if (horizontal_.size() == 1) {
        return lerp(table_[(std::size_t)iv0][0], table_[(std::size_t)iv1][0], tv) * sc;
    }
    int ih0, ih1;
    double th;
    phi_bracket(horizontal_, phi_horizontal_deg, ih0, ih1, th);
    const double lo =
        lerp(table_[(std::size_t)iv0][(std::size_t)ih0], table_[(std::size_t)iv0][(std::size_t)ih1], th);
    const double hi =
        lerp(table_[(std::size_t)iv1][(std::size_t)ih0], table_[(std::size_t)iv1][(std::size_t)ih1], th);
    return lerp(lo, hi, tv) * sc;
}

double IesProfile::zonal_lumens() const {
    const int n_v = (int)vertical_.size(), n_h = (int)horizontal_.size();
    if (n_v < 2 || n_h < 1) return 0.0;
    std::vector<double> dphi;
    if (n_h == 1) {
        dphi.push_back(2.0 * kPi);
    } else {
        for (int j = 0; j < n_h; ++j) {
            double step = std::fmod(horizontal_[(j + 1) % n_h] - horizontal_[j], 360.0);
            if (step < 0) step += 360.0;
            if (step == 0.0) step = 360.0 / n_h;
            dphi.push_back(step * kDegToRad);
        }
    }
    double flux = 0.0;
    for (int i = 0; i < n_v - 1; ++i) {
        const double band = std::cos(vertical_[(std::size_t)i] * kDegToRad) -
                            std::cos(vertical_[(std::size_t)i + 1] * kDegToRad);
        for (int j = 0; j < n_h; ++j)
            flux += 0.5 *
                    (table_[(std::size_t)i][(std::size_t)j] +
                     table_[(std::size_t)i + 1][(std::size_t)j]) *
                    dphi[(std::size_t)j] * band;
    }
    return flux;
}

}  // namespace luxcore
