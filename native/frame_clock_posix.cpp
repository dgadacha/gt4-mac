// FrameClock on macOS and other POSIX hosts (frame_clock.hpp); frame_clock.cpp is the Windows clock.

#include "frame_clock.hpp"

#include <cerrno>
#include <chrono>
#include <ctime>

namespace {
// The final stretch is spun rather than slept: a sleep can wake late.
constexpr double spin_seconds = 0.0005;
constexpr std::int64_t nanoseconds_per_second = 1000000000;
}

FrameClock::FrameClock() { frequency_ = static_cast<std::uint64_t>(nanoseconds_per_second); }

FrameClock::~FrameClock() = default;

std::int64_t FrameClock::now() const {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

void FrameClock::sleep_ticks(std::int64_t ticks) {
  if (ticks <= 0)
    return;
  timespec delay{static_cast<std::time_t>(ticks / nanoseconds_per_second),
                 static_cast<long>(ticks % nanoseconds_per_second)};
  while (nanosleep(&delay, &delay) != 0 && errno == EINTR) {
  }
}

void FrameClock::wait_until(std::int64_t target) {
  const auto spin = static_cast<std::int64_t>(spin_seconds * static_cast<double>(frequency_));
  for (;;) {
    const std::int64_t remaining = target - now();
    if (remaining <= 0)
      return;
    if (remaining > spin)
      sleep_ticks(remaining - spin);
    // Within the spin window: busy-wait for the exact tick.
  }
}
