#include "disc_overlay.hpp"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace gt4::disc_overlay {
namespace {

// The overlay file (scripts/gt4_volume_overlay.py write_overlay): "GT4OVL01", u64 disc size, u64 virtual size,
// u32 extent count, u32 reserved, then per extent u64 offset, u64 length and the bytes. Little-endian.
constexpr char kMagic[8] = {'G', 'T', '4', 'O', 'V', 'L', '0', '1'};

struct Extent {
  std::uint64_t offset = 0;
  std::vector<std::uint8_t> data;
};

struct Overlay {
  bool active = false;
  std::uint64_t disc_size = 0;
  std::uint64_t virtual_size = 0;
  std::vector<Extent> extents;
};

template <class T> T read_value(std::ifstream &file, const std::string &path) {
  T value{};
  if (!file.read(reinterpret_cast<char *>(&value), sizeof value))
    throw std::runtime_error("Disc overlay " + path + " is truncated");
  return value;
}

Overlay load(const char *path) {
  Overlay overlay;
  std::ifstream file(path, std::ios::binary);
  if (!file)
    throw std::runtime_error(std::string("Cannot open the disc overlay ") + path + " (GT4_DISC_OVERLAY)");
  char magic[8]{};
  if (!file.read(magic, sizeof magic) || std::memcmp(magic, kMagic, sizeof magic) != 0)
    throw std::runtime_error(std::string("Not a disc overlay: ") + path);
  overlay.disc_size = read_value<std::uint64_t>(file, path);
  overlay.virtual_size = read_value<std::uint64_t>(file, path);
  const auto count = read_value<std::uint32_t>(file, path);
  read_value<std::uint32_t>(file, path);
  for (std::uint32_t index = 0; index < count; ++index) {
    Extent extent;
    extent.offset = read_value<std::uint64_t>(file, path);
    const auto length = read_value<std::uint64_t>(file, path);
    if (length > (64u << 20) || extent.offset + length > overlay.virtual_size)
      throw std::runtime_error(std::string("Disc overlay extent out of range in ") + path);
    extent.data.resize(static_cast<std::size_t>(length));
    if (!file.read(reinterpret_cast<char *>(extent.data.data()), static_cast<std::streamsize>(length)))
      throw std::runtime_error(std::string("Disc overlay ") + path + " is truncated");
    overlay.extents.push_back(std::move(extent));
  }
  overlay.active = true;
  return overlay;
}

// Loaded once, at the first disc open; the reader returned by wrap() refers to it for the whole session.
const Overlay &overlay_for(std::uint64_t disc_size) {
  static const Overlay overlay = [] {
    const char *path = std::getenv("GT4_DISC_OVERLAY");
    return path && *path ? load(path) : Overlay{};
  }();
  if (overlay.active && overlay.disc_size != disc_size)
    throw std::runtime_error("The disc overlay (GT4_DISC_OVERLAY) was built for another disc image: rebuild it");
  return overlay;
}

} // namespace

std::uint64_t virtual_size(std::uint64_t disc_size) {
  const Overlay &overlay = overlay_for(disc_size);
  return overlay.active ? std::max(disc_size, overlay.virtual_size) : disc_size;
}

ps2::disc::Reader wrap(std::uint64_t disc_size, ps2::disc::Reader disc) {
  const Overlay &overlay = overlay_for(disc_size);
  if (!overlay.active)
    return disc;
  std::size_t bytes = 0;
  for (const Extent &extent : overlay.extents)
    bytes += extent.data.size();
  std::fprintf(stderr, "[disc] overlay: %zu extents, %zu bytes, %llu sectors past the image (GT4_DISC_OVERLAY)\n",
               overlay.extents.size(), bytes,
               static_cast<unsigned long long>((overlay.virtual_size - disc_size) / ps2::disc::kSector));
  return [&overlay, disc = std::move(disc), disc_size](std::uint64_t offset, void *out, std::size_t size) {
    auto *target = static_cast<std::uint8_t *>(out);
    const std::uint64_t end = std::max(disc_size, overlay.virtual_size);
    if (offset >= end)
      return std::size_t{0};
    const std::size_t valid = static_cast<std::size_t>(std::min<std::uint64_t>(size, end - offset));
    std::size_t from_disc = 0;
    if (offset < disc_size)
      from_disc = disc(offset, target, static_cast<std::size_t>(std::min<std::uint64_t>(valid, disc_size - offset)));
    std::fill(target + from_disc, target + valid, std::uint8_t{0});
    for (const Extent &extent : overlay.extents) {
      const std::uint64_t first = std::max(offset, extent.offset);
      const std::uint64_t last = std::min(offset + valid, extent.offset + extent.data.size());
      if (first < last)
        std::memcpy(target + (first - offset), extent.data.data() + (first - extent.offset),
                    static_cast<std::size_t>(last - first));
    }
    return valid;
  };
}

} // namespace gt4::disc_overlay
