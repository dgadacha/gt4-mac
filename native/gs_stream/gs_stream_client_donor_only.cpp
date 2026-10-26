// SPDX-License-Identifier: MIT
// Game-side GS stream backend for platforms without the GS process (macOS); gs_stream_client.cpp is the Windows one.
//
// gt4-gs.exe, the PCSX2 GS in its own process, and the shared-memory transport exist only on Windows. Here the
// renderer is always the donor GS front end with the native Vulkan renderer (CoreGS 1.1), which is what the Windows
// client does when GT4_RENDERER is unset and no capture is asked for: every hook returns at once. GT4_RENDERER=pcsx2
// and GT4_GS_CAPTURE stop the process before the game starts.
#include "gs_stream_client.hpp"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <string>

namespace gt4::gs_stream {
namespace {

// TASK-084 step 3: when the MTVU journal owns the VBlank, the field is held here instead of posted.
bool g_defer_vsync = false;
bool g_pending_vsync = false;
bool g_has_pending_vsync = false;

[[noreturn]] void refuse(const std::string &message) {
  std::fprintf(stderr, "[gs-ipc] %s; refusing to start\n", message.c_str());
  std::fflush(stderr);
  std::exit(EXIT_FAILURE);
}

Renderer parse_renderer() {
  const char *value = std::getenv("GT4_RENDERER");
  if (const char *capture = std::getenv("GT4_GS_CAPTURE"); capture && *capture)
    refuse("GT4_GS_CAPTURE needs the GS stream client, which exists only on Windows");
  if (!value || std::strcmp(value, "donor") == 0) return Renderer::donor;
  if (std::strcmp(value, "pcsx2") == 0)
    refuse("GT4_RENDERER=pcsx2 needs the GS process (gt4-gs.exe), which exists only on Windows; "
           "unset it for the built-in renderer");
  refuse(std::string("GT4_RENDERER=\"") + value + "\" is not donor or pcsx2");
}

}  // namespace

Renderer renderer() {
  static const Renderer mode = parse_renderer();
  return mode;
}

bool stream_renderer() { return renderer() == Renderer::pcsx2; }

bool on_gif_render(int, const std::uint8_t *, std::uint32_t) { return stream_renderer(); }

void on_privileged_write(std::uint32_t, std::uint64_t) {}

void set_privileged_ordering(const PrivilegedOrdering &) {}

void post_privileged_now(std::uint32_t, std::uint64_t) {}

bool read_fifo(std::uint8_t *, std::uint32_t) { return false; }

void on_vsync(bool odd_field) {
  if (g_defer_vsync) {
    g_pending_vsync = odd_field;
    g_has_pending_vsync = true;
  }
}

void set_vsync_deferral(bool defer) { g_defer_vsync = defer; }

bool post_pending_vsync() {
  if (!g_has_pending_vsync) return false;
  g_has_pending_vsync = false;
  return true;
}

void on_gs_reset() {}

void on_gif_reset() {}

void on_set_gs_crt(std::uint32_t, std::uint32_t, std::uint32_t) {}

bool attach_window(std::uint64_t, std::uint32_t, std::uint32_t) { return false; }

void resize_window(std::uint32_t, std::uint32_t) {}

void set_cursor_policy(bool, std::uint32_t) {}

void set_display_aspect_mode(DisplayAspectMode, std::uint32_t) {}

std::uint32_t aspect_millionths(double ratio) {
  if (!(ratio >= kMinFillAspect && ratio <= kMaxFillAspect)) return 0;
  return static_cast<std::uint32_t>(std::floor(ratio * 1e6 + 0.5));
}

void set_worker_busy_source(std::uint64_t (*)()) {}

void set_halt_handler(void (*)(const char *)) {}

void finish(std::FILE *) {}

}  // namespace gt4::gs_stream
