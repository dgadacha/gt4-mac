// CTest native_gs_resolution: the menu's resolution list per screen and the multiplier of each (gs_resolution.cpp).

#include "gs_resolution.hpp"

#include <cstdio>
#include <initializer_list>
#include <vector>

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[gs-resolution] FAIL: %s\n", what);
    ++failures;
  }
}

bool same(const std::vector<gt4::gs_resolution::Resolution> &list,
          std::initializer_list<gt4::gs_resolution::Resolution> expected) {
  if (list.size() != expected.size()) return false;
  auto entry = expected.begin();
  for (const auto &resolution : list) {
    if (resolution.width != entry->width || resolution.height != entry->height) return false;
    ++entry;
  }
  return true;
}

}  // namespace

int main() {
  namespace res = gt4::gs_resolution;
  // The docs/GS-SETTINGS.md table of the Windows launcher.
  expect(res::multiplier({1920, 1080}) == 3, "1920x1080 is 3x");
  expect(res::multiplier({2560, 1440}) == 4, "2560x1440 is 4x");
  expect(res::multiplier({3840, 2160}) == 6, "3840x2160 is 6x");
  expect(res::multiplier({3440, 1440}) == 6, "3440x1440 is 6x");
  expect(res::multiplier({1280, 720}) == 2, "1280x720 is 2x");
  expect(res::multiplier({640, 448}) == 1, "the PS2 picture is 1x");
  expect(res::multiplier({3024, 1964}) == 5, "a 14-inch MacBook Pro screen is 5x");
  expect(res::multiplier({20000, 20000}) == 12, "the multiplier stops at 12");

  expect(same(res::offered(3024, 1964), {{1280, 720}, {1920, 1080}, {2560, 1440}, {3024, 1964}}),
         "14-inch MacBook Pro: the common sizes that fit, then the screen's own");
  expect(same(res::offered(3840, 2160), {{1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}}),
         "a 4K screen is listed once");
  expect(same(res::offered(1920, 1080), {{1280, 720}, {1920, 1080}}), "a 1080p screen");
  expect(same(res::offered(5120, 2880), {{1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}, {5120, 2880}}),
         "a 5K screen");
  expect(same(res::offered(1440, 900), {{1280, 720}, {1440, 900}}), "a small 16:10 screen");
  expect(same(res::offered(2560, 1600), {{1280, 720}, {1920, 1080}, {2560, 1440}}),
         "a screen drawn at the multiplier of a listed size is not added");
  expect(res::offered(0, 0).empty(), "no screen size, no resolution");

  if (failures == 0) std::printf("[gs-resolution] all checks passed\n");
  return failures == 0 ? 0 : 1;
}
