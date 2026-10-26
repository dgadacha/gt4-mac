// SPDX-License-Identifier: MIT
// See gs_menu_settings.hpp. Keys, values and defaults: docs/launcher/gs-settings.toml (the allow-list of gt4-gs).
#include "gs_menu_settings.hpp"

#include "gs_config_file.hpp"

#include <cstddef>

namespace gt4::gs_menu_settings {
namespace {

constexpr const char *kGS = "EmuCore/GS";
constexpr const char *kGT4GS = "GT4GS";

bool holds(const Row &row, const std::vector<const char *> &values, const std::string &text) {
  for (std::size_t index = 0; index < row.keys.size(); ++index) {
    const Key &key = row.keys[index];
    if (values[index] && gs_config::value(text, key.section, key.name).value_or(key.default_value) != values[index])
      return false;
  }
  return true;
}

}  // namespace

const Row kMetalFX{"MetalFX upscaling", {{kGT4GS, "MetalFX", "false"}}, {"off", "on"}, {{"false"}, {"true"}}};

const Row kAnisotropicFiltering{"anisotropic filtering",
                                {{kGS, "MaxAnisotropy", "0"}},
                                {"off", "2x", "4x", "8x", "16x"},
                                {{"0"}, {"2"}, {"4"}, {"8"}, {"16"}}};

// FXAA of PCSX2, or SMAA 1x of the macOS gt4-gs: one at a time.
const Row kAntiAliasing{"anti-aliasing",
                        {{kGS, "fxaa", "false"}, {kGT4GS, "SMAA", "false"}},
                        {"off", "FXAA", "SMAA"},
                        {{"false", "false"}, {"true", "false"}, {"false", "true"}}};

// FidelityFX CAS, sharpen only (MetalFX does the enlarging); CASSharpness 0 to 100.
const Row kSharpening{"sharpening",
                      {{kGS, "CASMode", "0"}, {kGS, "CASSharpness", "50"}},
                      {"off", "low", "medium", "high"},
                      {{"0", nullptr}, {"1", "25"}, {"1", "50"}, {"1", "100"}}};

// The glow around the picture's bright parts (macOS gt4-gs), in percent strength.
const Row kBloom{"bloom", {{kGT4GS, "Bloom", "0"}}, {"off", "low", "medium", "high"}, {{"0"}, {"20"}, {"40"}, {"70"}}};

// Shade boost: brightness, contrast, saturation and gamma, 50 being neutral (the shader multiplies by level / 50).
// Contrast stays low: GT4's picture is short of saturation, and more contrast darkens its shadows.
const Row kColorBoost{"color boost",
                      {{kGS, "ShadeBoost", "false"},
                       {kGS, "ShadeBoost_Brightness", "50"},
                       {kGS, "ShadeBoost_Contrast", "50"},
                       {kGS, "ShadeBoost_Saturation", "50"},
                       {kGS, "ShadeBoost_Gamma", "50"}},
                      {"off", "low", "medium", "high"},
                      {{"false", nullptr, nullptr, nullptr, nullptr},
                       {"true", "50", "52", "57", "50"},
                       {"true", "50", "54", "64", "50"},
                       {"true", "50", "56", "72", "50"}}};

// A film-like tone curve, cool shadows and warm highlights, and a light vignette (macOS gt4-gs).
const Row kFilmLook{"film look", {{kGT4GS, "FilmLook", "false"}}, {"off", "on"}, {{"false"}, {"true"}}};

const Row kHDR{"HDR", {{kGT4GS, "HDR", "false"}}, {"off", "on"}, {{"false"}, {"true"}}};

int current_choice(const Row &row, const std::string &text) {
  for (std::size_t choice = 0; choice < row.choices.size(); ++choice)
    if (holds(row, row.choices[choice], text))
      return static_cast<int>(choice);
  for (std::size_t choice = 0; choice < row.choices.size(); ++choice)
    if (holds(row, row.choices[choice], std::string()))
      return static_cast<int>(choice);
  return 0;
}

std::string with_choice(const Row &row, const std::string &text, int choice) {
  std::string result = text;
  const std::vector<const char *> &values = row.choices[static_cast<std::size_t>(choice)];
  for (std::size_t index = 0; index < row.keys.size(); ++index)
    if (values[index])
      result = gs_config::with_value(result, row.keys[index].section, row.keys[index].name, values[index]);
  return result;
}

}  // namespace gt4::gs_menu_settings
