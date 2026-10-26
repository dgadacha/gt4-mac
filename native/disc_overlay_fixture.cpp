// CTest native_disc_overlay: the disc overlay reader (disc_overlay.cpp) over a synthetic disc image.

#include "disc_overlay.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[disc-overlay] FAIL: %s\n", what);
    ++failures;
  }
}

template <class T> void put(std::ofstream &file, T value) { file.write(reinterpret_cast<const char *>(&value), sizeof value); }

void put_extent(std::ofstream &file, std::uint64_t offset, const std::vector<std::uint8_t> &data) {
  put(file, offset);
  put(file, static_cast<std::uint64_t>(data.size()));
  file.write(reinterpret_cast<const char *>(data.data()), static_cast<std::streamsize>(data.size()));
}

} // namespace

int main() {
  constexpr std::uint64_t disc_size = 8 * 2048;
  constexpr std::uint64_t virtual_size = 10 * 2048;
  const std::filesystem::path path = std::filesystem::temp_directory_path() / "gt4-disc-overlay-fixture.gt4ovl";
  {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file.write("GT4OVL01", 8);
    put(file, disc_size);
    put(file, virtual_size);
    put(file, std::uint32_t{2});
    put(file, std::uint32_t{0});
    put_extent(file, 3 * 2048 + 100, std::vector<std::uint8_t>(50, 0xAB));          // inside the image
    put_extent(file, 8 * 2048 + 10, std::vector<std::uint8_t>(2048, 0xCD));       // past its end
  }
#if defined(_WIN32)
  _putenv_s("GT4_DISC_OVERLAY", path.string().c_str());
#else
  setenv("GT4_DISC_OVERLAY", path.string().c_str(), 1);
#endif
  // The image: every byte holds its offset modulo 251.
  const ps2::disc::Reader image = [](std::uint64_t offset, void *out, std::size_t size) {
    const std::size_t valid = offset >= disc_size ? 0 : static_cast<std::size_t>(std::min<std::uint64_t>(size, disc_size - offset));
    auto *bytes = static_cast<std::uint8_t *>(out);
    for (std::size_t index = 0; index < valid; ++index)
      bytes[index] = static_cast<std::uint8_t>((offset + index) % 251);
    return valid;
  };
  expect(gt4::disc_overlay::virtual_size(disc_size) == virtual_size, "virtual size covers the extent past the image");
  const ps2::disc::Reader reader = gt4::disc_overlay::wrap(disc_size, image);
  std::vector<std::uint8_t> sector(2048);
  expect(reader(2 * 2048, sector.data(), 2048) == 2048 && sector[5] == (2 * 2048 + 5) % 251, "untouched sector");
  expect(reader(3 * 2048, sector.data(), 2048) == 2048 && sector[99] == (3 * 2048 + 99) % 251 && sector[100] == 0xAB &&
             sector[149] == 0xAB && sector[150] == (3 * 2048 + 150) % 251,
         "extent inside the image replaces exactly its bytes");
  expect(reader(8 * 2048, sector.data(), 2048) == 2048 && sector[9] == 0 && sector[10] == 0xCD && sector[2047] == 0xCD,
         "extent past the image, zeros before it");
  expect(reader(9 * 2048, sector.data(), 2048) == 2048 && sector[9] == 0xCD && sector[10] == 0, "end of that extent");
  expect(reader(10 * 2048, sector.data(), 2048) == 0, "nothing past the virtual size");
  std::vector<std::uint8_t> span(3 * 2048);
  expect(reader(7 * 2048, span.data(), span.size()) == span.size() && span[0] == (7 * 2048) % 251 && span[2048] == 0 &&
             span[2048 + 10] == 0xCD,
         "one read across the end of the image");
  bool refused = false;
  try {
    gt4::disc_overlay::virtual_size(disc_size + 2048);
  } catch (const std::runtime_error &) {
    refused = true;
  }
  expect(refused, "an overlay built for another image is refused");
  std::filesystem::remove(path);
  if (failures) {
    std::fprintf(stderr, "[disc-overlay] %d failure(s)\n", failures);
    return 1;
  }
  std::fprintf(stderr, "[disc-overlay] PASS\n");
  return 0;
}
