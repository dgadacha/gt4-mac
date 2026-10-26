#pragma once

// Disc overlay (in-game Graphics menu): GT4_DISC_OVERLAY=<file> names an overlay built by
// scripts/gt4_volume_overlay.py from the user's own disc: extents of disc bytes (a rewritten GT4.VOL catalogue and
// replacement files placed past the end of the image) that the game reads instead of the image. The derived donor
// disc.cpp (scripts/prepare_menu_runtime.py) passes its reader through wrap(). Without the variable both functions
// return their input unchanged.

#include "ps2/disc.hpp"

#include <cstdint>

namespace gt4::disc_overlay {

// The size the game sees: the image size, or the end of the last overlay extent past it.
std::uint64_t virtual_size(std::uint64_t disc_size);

// A reader that serves the overlay extents over `disc`, the reader of an image of `disc_size` bytes. Throws
// std::runtime_error when the overlay file cannot be read or was built for an image of another size.
ps2::disc::Reader wrap(std::uint64_t disc_size, ps2::disc::Reader disc);

} // namespace gt4::disc_overlay
