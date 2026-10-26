// CTest native_gs_menu_settings: the Graphics page rows that write the GS process's settings file (gs_menu_settings.cpp).

#include "gs_config_file.hpp"
#include "gs_menu_settings.hpp"

#include <cstdio>
#include <string>

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[gs-menu-settings] FAIL: %s\n", what);
    ++failures;
  }
}

}  // namespace

int main() {
  namespace rows = gt4::gs_menu_settings;
  namespace config = gt4::gs_config;
  const rows::Row *all[] = {&rows::kMetalFX,    &rows::kAnisotropicFiltering, &rows::kAntiAliasing,
                            &rows::kSharpening, &rows::kBloom,                &rows::kColorBoost,
                            &rows::kFilmLook,   &rows::kHDR};
  const std::string file = "[EmuCore/GS]\nupscale_multiplier = 5\n\n[GT4GS]\nDataRoot = /data\n";

  for (const rows::Row *row : all) {
    expect(row->choice_names.size() == row->choices.size(), "one name per choice");
    for (const auto &values : row->choices)
      expect(values.size() == row->keys.size(), "one value per key in every choice");
    // Every choice written reads back as itself, and the other lines stay.
    for (int choice = 0; choice < static_cast<int>(row->choices.size()); ++choice) {
      const std::string written = rows::with_choice(*row, file, choice);
      expect(rows::current_choice(*row, written) == choice, "a written choice reads back");
      expect(config::value(written, "EmuCore/GS", "upscale_multiplier") == "5", "other keys are kept");
      expect(config::value(written, "GT4GS", "DataRoot") == "/data", "other sections are kept");
    }
  }

  // Without the keys the page shows what the GS process does: everything off.
  expect(rows::current_choice(rows::kMetalFX, file) == 0, "MetalFX is off by default");
  expect(rows::current_choice(rows::kAnisotropicFiltering, file) == 0, "anisotropic filtering is off by default");
  expect(rows::current_choice(rows::kAntiAliasing, file) == 0, "FXAA is off by default");
  expect(rows::current_choice(rows::kSharpening, file) == 0, "CAS is off by default");
  expect(rows::current_choice(rows::kColorBoost, file) == 0, "shade boost is off by default");
  expect(rows::current_choice(rows::kBloom, file) == 0, "bloom is off by default");
  expect(rows::current_choice(rows::kFilmLook, file) == 0, "the film look is off by default");
  expect(rows::current_choice(rows::kHDR, file) == 0, "HDR is off by default");

  // The values the GS process reads.
  const std::string sixteen = rows::with_choice(rows::kAnisotropicFiltering, file, 4);
  expect(config::value(sixteen, "EmuCore/GS", "MaxAnisotropy") == "16", "16x writes MaxAnisotropy = 16");
  const std::string smaa = rows::with_choice(rows::kAntiAliasing, rows::with_choice(rows::kAntiAliasing, file, 1), 2);
  expect(config::value(smaa, "EmuCore/GS", "fxaa") == "false" && config::value(smaa, "GT4GS", "SMAA") == "true",
         "SMAA turns FXAA off");
  const std::string glow = rows::with_choice(rows::kBloom, file, 2);
  expect(config::value(glow, "GT4GS", "Bloom") == "40", "medium bloom writes [GT4GS] Bloom = 40");
  const std::string hdr = rows::with_choice(rows::kHDR, file, 1);
  expect(config::value(hdr, "GT4GS", "HDR") == "true", "HDR on writes [GT4GS] HDR = true");
  const std::string sharp = rows::with_choice(rows::kSharpening, file, 3);
  expect(config::value(sharp, "EmuCore/GS", "CASMode") == "1" &&
             config::value(sharp, "EmuCore/GS", "CASSharpness") == "100",
         "high sharpening writes sharpen-only CAS at 100");
  const std::string vivid = rows::with_choice(rows::kColorBoost, file, 2);
  expect(config::value(vivid, "EmuCore/GS", "ShadeBoost") == "true" &&
             config::value(vivid, "EmuCore/GS", "ShadeBoost_Saturation") == "64",
         "medium color boost turns shade boost on with its levels");

  // Off writes only the switch: the levels stay for the next time, and still read as Off.
  const std::string sharp_off = rows::with_choice(rows::kSharpening, sharp, 0);
  expect(config::value(sharp_off, "EmuCore/GS", "CASMode") == "0", "sharpening off writes CASMode = 0");
  expect(config::value(sharp_off, "EmuCore/GS", "CASSharpness") == "100", "sharpening off keeps the amount");
  expect(rows::current_choice(rows::kSharpening, sharp_off) == 0, "sharpening off reads back");
  const std::string boost_off = rows::with_choice(rows::kColorBoost, vivid, 0);
  expect(rows::current_choice(rows::kColorBoost, boost_off) == 0, "color boost off reads back");
  expect(config::value(boost_off, "EmuCore/GS", "ShadeBoost_Saturation") == "64", "color boost off keeps the levels");

  // A value no choice writes falls back to the default choice.
  const std::string odd = config::with_value(file, "EmuCore/GS", "MaxAnisotropy", "3");
  expect(rows::current_choice(rows::kAnisotropicFiltering, odd) == 0, "an odd anisotropy reads as Off");

  if (failures == 0) std::printf("[gs-menu-settings] all checks passed\n");
  return failures == 0 ? 0 : 1;
}
