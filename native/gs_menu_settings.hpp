// SPDX-License-Identifier: MIT
// The rows of the in-game Graphics page that change keys of the PCSX2 GS renderer's settings file (macOS,
// GT4_RENDERER=pcsx2; GT4_GS_CONFIG, docs/GS-SETTINGS.md): the values each choice of a row writes, and the choice a
// file holds. The GS process applies a change after CONTROL reload_config (gs_stream_client.hpp, reload_gs_settings).
// The Resolution row is separate (gs_resolution.hpp): its choices depend on the screen.
#pragma once

#include <string>
#include <vector>

namespace gt4::gs_menu_settings {

// A key a row writes, and the value the GS process uses when the file lacks it.
struct Key {
  const char *section;
  const char *name;
  const char *default_value;
};

// Choice n of a row writes choices[n][k] to keys[k]; a null value is not written and matches any value in the file.
struct Row {
  const char *name;                               // for the log
  std::vector<Key> keys;
  std::vector<const char *> choice_names;         // for the log
  std::vector<std::vector<const char *>> choices;
};

// The rows, in the order of the Graphics page (Resolution comes first and is not one of them).
extern const Row kMetalFX;              // [GT4GS] MetalFX: Off, On
extern const Row kAnisotropicFiltering; // MaxAnisotropy: Off, 2x, 4x, 8x, 16x
extern const Row kAntiAliasing;         // fxaa and [GT4GS] SMAA: Off, FXAA, SMAA
extern const Row kSharpening;           // CASMode and CASSharpness: Off, Low, Medium, High
extern const Row kBloom;                // [GT4GS] Bloom (percent strength): Off, Low, Medium, High
extern const Row kColorBoost;           // ShadeBoost and its four levels: Off, Low, Medium, High
extern const Row kFilmLook;             // [GT4GS] FilmLook: Off, On
extern const Row kHDR;                  // [GT4GS] HDR: Off, On

// The choice the settings file `text` holds: the first whose values all match the file (a key the file lacks reads as
// its default). When none matches (a value written by hand), the choice that matches the defaults, which is what the
// GS process does without the keys.
int current_choice(const Row &row, const std::string &text);
// `text` with the values of choice `choice` written (gs_config_file.hpp with_value), every other line kept.
std::string with_choice(const Row &row, const std::string &text, int choice);

}  // namespace gt4::gs_menu_settings
