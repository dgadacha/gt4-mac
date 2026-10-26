// SPDX-License-Identifier: MIT
// See gs_resolution.hpp.
#include "gs_resolution.hpp"

#include <algorithm>

namespace gt4::gs_resolution {

std::vector<Resolution> offered(std::uint32_t width, std::uint32_t height) {
  std::vector<Resolution> list;
  bool screen_listed = false;
  for (const Resolution common : kCommon) {
    if (common.width > width || common.height > height) continue;
    list.push_back(common);
    screen_listed = screen_listed || (common.width == width && common.height == height);
  }
  // The screen's own resolution, unless a listed one already draws at its multiplier (2560x1600 next to 2560x1440).
  if (!screen_listed && width && height && (list.empty() || multiplier({width, height}) > multiplier(list.back())))
    list.push_back({width, height});
  // The largest ones stay when a screen would list more than the menu holds.
  if (list.size() > static_cast<std::size_t>(kMaxListed)) list.erase(list.begin(), list.end() - kMaxListed);
  return list;
}

int multiplier(Resolution resolution) {
  const std::uint32_t across = (resolution.width + 639) / 640, down = (resolution.height + 447) / 448;
  return std::clamp(static_cast<int>(std::max(across, down)), 1, 12);
}

}  // namespace gt4::gs_resolution
