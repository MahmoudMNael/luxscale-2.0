#pragma once
/// IES LM-63 Type-C photometry. Immutable value object with an OOP facade:
/// construction validates, sampling is const, parsing is a named factory.

#include <string>
#include <vector>

namespace luxcore {

class IesProfile final {
  public:
    IesProfile(std::vector<double> vertical_angles, std::vector<double> horizontal_angles,
               std::vector<std::vector<double>> candela_table, double multiplier,
               double ballast_factor, double ballast_lamp_factor, double flux_scale,
               double width, double length, double height);

    /// Parse IES text (mirrors Python load_ies, raises std::invalid_argument).
    static IesProfile load(const std::string& ies_text);

    /// Bilinear candela sample in candela (includes multiplier/ballast/flux scale).
    double sample(double theta_vertical_deg, double phi_horizontal_deg) const;

    double zonal_lumens() const;

    // --- accessors (read-only views) ---
    const std::vector<double>& vertical_angles() const { return vertical_; }
    const std::vector<double>& horizontal_angles() const { return horizontal_; }
    const std::vector<std::vector<double>>& candela_table() const { return table_; }
    double multiplier() const { return multiplier_; }
    double ballast_factor() const { return ballast_; }
    double ballast_lamp_factor() const { return ballast_lamp_; }
    double flux_scale() const { return flux_scale_; }
    double width() const { return width_; }
    double length() const { return length_; }
    double height() const { return height_; }
    double scale() const { return multiplier_ * ballast_ * ballast_lamp_ * flux_scale_; }

  private:
    static void bracket(const std::vector<double>& angles, double value, int& i0, int& i1,
                        double& t);
    static void phi_bracket(const std::vector<double>& angles, double phi, int& i0, int& i1,
                            double& t);
    static inline double lerp(double a, double b, double t) { return a * (1.0 - t) + b * t; }

    std::vector<double> vertical_;
    std::vector<double> horizontal_;
    std::vector<std::vector<double>> table_;
    double multiplier_;
    double ballast_;
    double ballast_lamp_;
    double flux_scale_;
    double width_;
    double length_;
    double height_;
};

}  // namespace luxcore
