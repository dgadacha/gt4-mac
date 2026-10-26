// SPDX-License-Identifier: MIT
// The resolutions the in-game Graphics menu offers with the PCSX2 GS renderer (macOS, GT4_RENDERER=pcsx2), and the
// internal resolution multiplier of each (gt4-gs.ini upscale_multiplier).
//
// The list depends on the screen: the common 16:9 resolutions that fit in it, then the screen's own resolution when it
// is not one of them and draws at a higher multiplier than the largest of them. The multiplier is the Windows
// launcher's rule (docs/GS-SETTINGS.md, TASK-080 addendum): the smallest whole multiple of the PS2 picture (640x448)
// that covers the resolution, k = ceil(max(W / 640, H / 448)), clamped to 1..12. 1920x1080 gives 3, 2560x1440 4,
// 3840x2160 6.
#pragma once

#include <cstdint>
#include <vector>

namespace gt4::gs_resolution {

struct Resolution {
  std::uint32_t width = 0, height = 0;
};

inline constexpr Resolution kCommon[] = {{1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}};
// The menu's choices: 0 is the PS2 picture itself (multiplier 1), then at most kMaxListed resolutions.
inline constexpr int kMaxListed = 5;

// The resolutions offered on a screen of `width` x `height` pixels, smallest first.
std::vector<Resolution> offered(std::uint32_t width, std::uint32_t height);
// upscale_multiplier for a resolution.
int multiplier(Resolution resolution);

}  // namespace gt4::gs_resolution
