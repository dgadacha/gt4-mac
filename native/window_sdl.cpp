// The game window on macOS (window.hpp), with SDL3; window.cpp is the Win32 window.
//
// The guest runs on this thread (the main thread, as Cocoa requires for the window) and SDL events are pumped at every
// guest VBlank, as window.cpp pumps the Win32 messages. The native Vulkan adapter (MoltenVK) presents into the window's
// CAMetalLayer, passed as the window handle of surface kind 3 (native_vulkan.hpp). The rules are the Windows ones:
// GT4_FULLSCREEN, GT4_CONTROLS_FILE, GT4_INPUT, GT4_PACING, GT4_CURSOR_AUTOHIDE, GT4_FORCE_480P, GT4_DISPLAY_ASPECT and
// GT4_OUTPUT_SIZE; F7/F8/F9 drive the performance probe; Alt+Enter, F11, Cmd+F and Ctrl+Cmd+F toggle fullscreen.
// GT4_DEINTERLACE=blend (default) or off: the 480i menus blend their two fields instead of bouncing by one field
// line at every VBlank (native_vulkan.hpp, set_interlaced_presentation).
// GT4_MONITOR names a Windows display and is ignored here. Racing wheels, achievements and the GS process
// (GT4_RENDERER=pcsx2) are Windows only.

#include "window.hpp"
#include "race_display.hpp"
#include "race_widescreen.hpp"
#include "display_aspect.hpp"
#include "ps2/memory.hpp"
#include "gpu.hpp"
#include "gs/gs.hpp"
#include "host_io.hpp"
#include "native_vulkan.hpp"
#include "ps2/system.hpp"
#include "perf_probe.hpp"
#include "frame_clock.hpp"
#include "pacing.hpp"
#include "window_mode.hpp"
#include "cursor_autohide.hpp"
#ifdef GT4_GS_STREAM_CLIENT
#include "gs_stream/gs_stream_client.hpp"
#endif
#ifdef GT4_MTVU_MEASURE
#include "mtvu_measure.hpp"
#endif
#ifdef GT4_SHAPE_CAPTURE
#error "The shape capture build exists only on Windows"
#endif

#include <SDL3/SDL.h>

#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr char window_title[] = "Gran Turismo 4";
SDL_Window *game_window = nullptr;
SDL_MetalView metal_view = nullptr;
bool video_initialized = false;
bool surface_attached = false;
bool closing = false;
bool fullscreen = false;
ControllerInput *controller = nullptr;
// Pacing state (see pacing.hpp). The clock and histogram run in both modes;
// the release grid only in paced mode.
gt4::pacing::Mode pacing_mode = gt4::pacing::Mode::paced;
std::unique_ptr<FrameClock> frame_clock;
std::unique_ptr<gt4::pacing::FramePacer> frame_pacer;
gt4::pacing::Diagnostics pacing_diagnostics;
// Session totals at the last F7 start or F8 report; the next report prints the difference.
gt4::pacing::Counters counters_at_last_report;
// GT4_FORCE_480P (slice164): set at window start; counts guest VBlank writes of the race display index.
bool force_480p_enabled = false;
gt4::display::Force480pState force_480p_state;
AudioOutput *audio_output = nullptr;
// Input bindings (controls.hpp). open_window loads them before the window exists.
gt4::controls::ControlMap active_controls;
// TASK-075: gamepad backend (GT4_INPUT=sdl, the only one on macOS). open_window loads it.
gt4::pad::Backend input_backend = gt4::pad::Backend::sdl;
// A keyboard binding with the scancode that types its key in the current layout (the Win32 virtual key names the key
// by its label, so W stays W on an AZERTY keyboard, as on Windows).
struct ScancodeBinding {
  std::uint8_t virtual_key = 0;
  SDL_Scancode scancode = SDL_SCANCODE_UNKNOWN;
  SDL_Scancode alternate = SDL_SCANCODE_UNKNOWN; // the right-hand twin of Shift, Ctrl and Alt
  std::uint16_t button_mask = 0;
};
std::vector<gt4::controls::KeyboardBinding> keyboard_keys;
std::vector<ScancodeBinding> keyboard_scancodes;
// TASK-060: cursor auto-hide over the game picture (GT4_CURSOR_AUTOHIDE, cursor_autohide.hpp).
gt4::cursor::AutoHide cursor_autohide;
// GT4_DEINTERLACE: blend the fields of an interlaced picture (the 480i menus).
bool blend_interlaced_fields = true;
int lock_descriptor = -1;

// Win32 virtual-key codes, as controls.cpp writes them (it needs no Windows headers either).
constexpr std::uint8_t vk_back = 0x08, vk_tab = 0x09, vk_return = 0x0D, vk_shift = 0x10, vk_control = 0x11,
                       vk_menu = 0x12, vk_escape = 0x1B, vk_space = 0x20, vk_prior = 0x21, vk_next = 0x22,
                       vk_end = 0x23, vk_home = 0x24, vk_left = 0x25, vk_up = 0x26, vk_right = 0x27, vk_down = 0x28,
                       vk_insert = 0x2D, vk_delete = 0x2E, vk_numpad0 = 0x60, vk_f1 = 0x70, vk_f24 = 0x87;

ScancodeBinding scancode_binding(const gt4::controls::KeyboardBinding &binding) {
  ScancodeBinding result;
  result.virtual_key = binding.virtual_key;
  result.button_mask = binding.button_mask;
  const std::uint8_t key = binding.virtual_key;
  if (key >= 'A' && key <= 'Z') {
    result.scancode = SDL_GetScancodeFromKey(static_cast<SDL_Keycode>(key - 'A' + 'a'), nullptr);
    // A layout without that letter (Cyrillic, Greek...): the key at the letter's QWERTY position.
    if (result.scancode == SDL_SCANCODE_UNKNOWN)
      result.scancode = static_cast<SDL_Scancode>(SDL_SCANCODE_A + (key - 'A'));
  } else if (key >= '0' && key <= '9')
    result.scancode = key == '0' ? SDL_SCANCODE_0 : static_cast<SDL_Scancode>(SDL_SCANCODE_1 + (key - '1'));
  else if (key >= vk_numpad0 && key <= vk_numpad0 + 9)
    result.scancode = key == vk_numpad0 ? SDL_SCANCODE_KP_0
                                        : static_cast<SDL_Scancode>(SDL_SCANCODE_KP_1 + (key - vk_numpad0 - 1));
  else if (key >= vk_f1 && key < vk_f1 + 12)
    result.scancode = static_cast<SDL_Scancode>(SDL_SCANCODE_F1 + (key - vk_f1));
  else if (key >= vk_f1 + 12 && key <= vk_f24)
    result.scancode = static_cast<SDL_Scancode>(SDL_SCANCODE_F13 + (key - vk_f1 - 12));
  else {
    switch (key) {
    case vk_back: result.scancode = SDL_SCANCODE_BACKSPACE; break;
    case vk_tab: result.scancode = SDL_SCANCODE_TAB; break;
    case vk_return: result.scancode = SDL_SCANCODE_RETURN; result.alternate = SDL_SCANCODE_KP_ENTER; break;
    case vk_shift: result.scancode = SDL_SCANCODE_LSHIFT; result.alternate = SDL_SCANCODE_RSHIFT; break;
    case vk_control: result.scancode = SDL_SCANCODE_LCTRL; result.alternate = SDL_SCANCODE_RCTRL; break;
    case vk_menu: result.scancode = SDL_SCANCODE_LALT; result.alternate = SDL_SCANCODE_RALT; break;
    case vk_escape: result.scancode = SDL_SCANCODE_ESCAPE; break;
    case vk_space: result.scancode = SDL_SCANCODE_SPACE; break;
    case vk_prior: result.scancode = SDL_SCANCODE_PAGEUP; break;
    case vk_next: result.scancode = SDL_SCANCODE_PAGEDOWN; break;
    case vk_end: result.scancode = SDL_SCANCODE_END; break;
    case vk_home: result.scancode = SDL_SCANCODE_HOME; break;
    case vk_left: result.scancode = SDL_SCANCODE_LEFT; break;
    case vk_up: result.scancode = SDL_SCANCODE_UP; break;
    case vk_right: result.scancode = SDL_SCANCODE_RIGHT; break;
    case vk_down: result.scancode = SDL_SCANCODE_DOWN; break;
    case vk_insert: result.scancode = SDL_SCANCODE_INSERT; break;
    case vk_delete: result.scancode = SDL_SCANCODE_DELETE; break;
    default: break;
    }
  }
  if (result.scancode == SDL_SCANCODE_UNKNOWN)
    std::fprintf(stderr, "[controls] virtual key 0x%02X has no key on this keyboard; binding ignored\n", key);
  return result;
}

void apply_pad(const PadState &pad) {
  ps2::set_pad_buttons(pad.buttons);
  for (int axis = 0; axis < 4; ++axis)
    ps2::set_pad_axis(axis, pad.axes[axis]);
  for (int button = 0; button < 16; ++button)
    ps2::set_pad_pressure(button, pad.pressures[button]);
}

gt4::pacing::Counters pacing_counters() {
  gt4::pacing::Counters counters;
  if (frame_pacer)
    counters.late_frames = frame_pacer->late_frames();
  if (audio_output) {
    counters.audio_underruns = audio_output->underruns();
    counters.ring_overflow_frames = audio_output->overflow_frames();
  }
  return counters;
}

bool window_focused() {
  return game_window && (SDL_GetWindowFlags(game_window) & SDL_WINDOW_INPUT_FOCUS) != 0;
}

// One cursor sample per VBlank and per mouse movement: hidden after the delay without movement over the picture.
void update_cursor() {
  if (!game_window || !cursor_autohide.policy().auto_hide)
    return;
  float x = 0.0f, y = 0.0f;
  SDL_GetMouseState(&x, &y);
  const bool over_picture = SDL_GetMouseFocus() == game_window;
  const bool was_hidden = cursor_autohide.hidden();
  const bool hide =
      cursor_autohide.update(static_cast<std::int32_t>(x), static_cast<std::int32_t>(y), SDL_GetTicks(), over_picture);
  if (hide && !was_hidden)
    SDL_HideCursor();
  else if (!hide && was_hidden)
    SDL_ShowCursor();
}

// Borderless fullscreen on the window's display (the desktop mode, no mode change); the next toggle restores the
// window. The swapchain follows the new pixel size through SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED.
void set_fullscreen(bool enabled) {
  if (!game_window || enabled == fullscreen)
    return;
  SDL_SetWindowFullscreenMode(game_window, nullptr);
  if (SDL_SetWindowFullscreen(game_window, enabled))
    fullscreen = enabled;
  else
    std::fprintf(stderr, "[window] fullscreen %s failed: %s\n", enabled ? "on" : "off", SDL_GetError());
}

// TASK-080 presentation sink (native/display_aspect.hpp, EE thread): CoreGS 1.1 fills a rectangle of the race
// projection ratio.
void present_race_view(bool fill, double ratio) {
#ifdef GT4_GS_STREAM_CLIENT
  if (gt4::gs_stream::stream_renderer()) {
    gt4::gs_stream::set_display_aspect_mode(fill ? gt4::gs_stream::DisplayAspectMode::fill
                                                 : gt4::gs_stream::DisplayAspectMode::game_aspect,
                                            fill ? gt4::gs_stream::aspect_millionths(ratio) : 0);
    return;
  }
#endif
  gt4::vulkan::set_race_view_presentation(fill, ratio);
}

void on_key_down(const SDL_KeyboardEvent &key) {
#ifdef GT4_PERF_PROBE
  if (key.scancode == SDL_SCANCODE_F7 || key.scancode == SDL_SCANCODE_F8 || key.scancode == SDL_SCANCODE_F9) {
    if (key.scancode == SDL_SCANCODE_F7) {
      // The F7/F8 interval starts here: histogram and counter deltas restart.
      counters_at_last_report = pacing_counters();
      pacing_diagnostics.reset();
#ifdef GT4_MTVU_MEASURE
      if (!key.repeat)
        gt4::mtvu::request_interval_reset();
#endif
    }
    const auto request = key.scancode == SDL_SCANCODE_F7   ? gt4::perf::Request::start
                         : key.scancode == SDL_SCANCODE_F8 ? gt4::perf::Request::report
                                                           : gt4::perf::Request::toggle;
    gt4::perf::Probe::shared().request(request, key.repeat);
    return;
  }
#endif
  if (key.repeat)
    return;
  const bool alt_enter = key.scancode == SDL_SCANCODE_RETURN && (key.mod & SDL_KMOD_ALT);
  const bool command_f = key.scancode == SDL_SCANCODE_F && (key.mod & SDL_KMOD_GUI);
  if (alt_enter || command_f || key.scancode == SDL_SCANCODE_F11)
    set_fullscreen(!fullscreen);
}

bool pump_messages() {
  SDL_Event event;
  while (SDL_PollEvent(&event)) {
    switch (event.type) {
    case SDL_EVENT_QUIT:
    case SDL_EVENT_WINDOW_CLOSE_REQUESTED:
      ps2::halt("window closed");
      closing = true;
      return false;
    case SDL_EVENT_KEY_DOWN:
      on_key_down(event.key);
      break;
    case SDL_EVENT_WINDOW_FOCUS_LOST:
      if (controller) {
        controller->stop();
        if (ps2::g_options.presses.empty())
          apply_pad({});
      }
      break;
    case SDL_EVENT_WINDOW_ENTER_FULLSCREEN:
      fullscreen = true;
      break;
    case SDL_EVENT_WINDOW_LEAVE_FULLSCREEN:
      fullscreen = false;
      break;
    case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED: {
      const auto width = static_cast<std::uint32_t>(event.window.data1);
      const auto height = static_cast<std::uint32_t>(event.window.data2);
      // TASK-080: GT4_DISPLAY_ASPECT=auto follows the picture size (windowed, fullscreen, resize).
      gt4::display_aspect::set_window_client_size(width, height);
      if (surface_attached)
        ps2::gs::resize_window(width, height);
      break;
    }
    case SDL_EVENT_MOUSE_MOTION:
      update_cursor();
      break;
    default:
      break;
    }
  }
  return !closing;
}

// Releases the guest frame. Paced mode waits on the wall-clock grid first, so
// each VBlank comes at the donor's 60 Hz rate and audio never sets the pace.
// The interval histogram is recorded in both modes.
void release_frame() {
  if (pacing_mode == gt4::pacing::Mode::paced) {
    if (!frame_pacer->anchored())
      frame_pacer->anchor(frame_clock->now());
    // TASK-084 step 0: the sleep is its own category, so F8 ee_dispatch and unattributed mean work, not sleep.
    GT4_PERF_SCOPE(gt4::perf::Category::pacing_wait);
    frame_clock->wait_until(frame_pacer->deadline());
  }
  const std::int64_t released = frame_clock->now();
  if (pacing_mode == gt4::pacing::Mode::paced)
    frame_pacer->release(released);
  pacing_diagnostics.record_release(released, frame_clock->frequency());
}

void on_vblank() {
#ifdef GT4_PERF_PROBE
  gt4::perf::Probe::shared().frame_boundary(
      {ps2::now(), ps2::primitives_drawn(), ps2::vu1_interpreted_calls()});
#endif
  release_frame();
  GT4_PERF_SCOPE(gt4::perf::Category::host_vblank);
  if (!pump_messages())
    return;
  update_cursor();
  if (force_480p_enabled)
    gt4::display::force_race_480p_at_vblank(ps2::g_ram, ps2::kRamSize, force_480p_state);
  std::uint16_t buttons = 0;
  const bool focused = window_focused();
  if (focused) {
    // Keyboard bindings come from the controls table (defaults match the old fixed map).
    // Alt+Enter toggles fullscreen: while Alt is held, Enter is not Start.
    const bool *keys = SDL_GetKeyboardState(nullptr);
    const bool alt_held = (SDL_GetModState() & SDL_KMOD_ALT) != 0;
    for (const auto &binding : keyboard_scancodes) {
      if (binding.virtual_key == vk_return && alt_held)
        continue;
      if ((binding.scancode != SDL_SCANCODE_UNKNOWN && keys[binding.scancode]) ||
          (binding.alternate != SDL_SCANCODE_UNKNOWN && keys[binding.alternate]))
        buttons |= binding.button_mask;
    }
  }
  if (ps2::g_options.presses.empty()) {
    apply_pad(controller->poll(focused, buttons));
    if (focused)
      controller->rumble(ps2::pad_rumble());
  }
  if (audio_output) {
    // Paced mode: move ring data to the device without waiting.
    audio_output->pump();
    pacing_diagnostics.record_queue_frames(audio_output->queued_frames());
    if (audio_output->mode() == gt4::pacing::Mode::paced)
      pacing_diagnostics.record_ratio(audio_output->resampler_ratio());
  }
  // SMODE2 INT and FFMD: the picture is one field of an interlaced frame (480i menus).
  gt4::vulkan::set_interlaced_presentation(blend_interlaced_fields &&
                                           (ps2::gs::display_regs().smode2 & 3u) == 3u);
  ps2::gs::present();
}

// The game window's picture size in pixels (the Metal drawable size on a Retina display).
void pixel_size(std::uint32_t &width, std::uint32_t &height) {
  int pixel_width = 0, pixel_height = 0;
  if (!SDL_GetWindowSizeInPixels(game_window, &pixel_width, &pixel_height))
    throw std::runtime_error(std::string("Cannot read the game window size: ") + SDL_GetError());
  width = static_cast<std::uint32_t>(pixel_width);
  height = static_cast<std::uint32_t>(pixel_height);
}

// Exclusive lock of <memory card>.lock for the whole session, as the Windows window keeps its lock handle open.
void lock_memory_card() {
  const auto lock_path = ps2::g_options.memcard_path + ".lock";
  lock_descriptor = ::open(lock_path.c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0644);
  if (lock_descriptor < 0 || flock(lock_descriptor, LOCK_EX | LOCK_NB) != 0) {
    const int error = errno;
    if (lock_descriptor >= 0)
      ::close(lock_descriptor);
    lock_descriptor = -1;
    throw std::runtime_error("Cannot exclusively lock game memory card: " + std::string(std::strerror(error)));
  }
}

void unlock_memory_card() {
  if (lock_descriptor >= 0) {
    flock(lock_descriptor, LOCK_UN);
    ::close(lock_descriptor);
    lock_descriptor = -1;
  }
}
} // namespace

bool open_window(bool start_in_fullscreen) {
  // The launcher passes GT4_FULLSCREEN (its Display setting, on by default). An invalid value stops the start.
  bool start_fullscreen = start_in_fullscreen;
  try {
    start_fullscreen = start_fullscreen || gt4::window_mode::parse_start_fullscreen(std::getenv("GT4_FULLSCREEN"));
  } catch (const std::invalid_argument &error) {
    std::fprintf(stderr, "[window] %s, game not started\n", error.what());
    return false;
  }
  // An invalid GT4_CONTROLS_FILE stops the start here, before any window or guest work.
  try {
    active_controls = gt4::controls::load_controls_from_environment();
  } catch (const gt4::controls::ConfigError &error) {
    std::fprintf(stderr, "[controls] invalid controls file, game not started: %s\n",
                 error.what());
    return false;
  }
  keyboard_keys = gt4::controls::keyboard_bindings(active_controls);
  // TASK-080: an invalid GT4_DISPLAY_ASPECT, GT4_OUTPUT_SIZE or GT4_ASPECT_FOV_EXTRA stops the start here (prints and
  // exits).
  gt4::display_aspect::configured_setting();
  const gt4::display_aspect::OutputSize output = gt4::display_aspect::configured_output_size();
  try {
    if (!gt4::window_mode::parse_monitor(std::getenv("GT4_MONITOR")).empty())
      std::fprintf(stderr, "[window] GT4_MONITOR names a Windows display; ignored on this platform\n");
  } catch (const std::invalid_argument &error) {
    std::fprintf(stderr, "[window] %s, game not started\n", error.what());
    return false;
  }
  try {
    input_backend = gt4::pad::parse_backend(std::getenv("GT4_INPUT"));
  } catch (const std::invalid_argument &error) {
    std::fprintf(stderr, "[input] %s, game not started\n", error.what());
    return false;
  }
  if (input_backend != gt4::pad::Backend::sdl) {
    std::fprintf(stderr, "[input] GT4_INPUT=%s exists only on Windows, game not started\n",
                 gt4::pad::backend_name(input_backend));
    return false;
  }
  std::fprintf(stderr, "[input] backend %s\n", gt4::pad::backend_name(input_backend));
  const char *controls_file = std::getenv("GT4_CONTROLS_FILE");
  std::fprintf(stderr, "[controls] %s\n",
               controls_file && *controls_file ? controls_file : "default bindings");
  if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS))
    throw std::runtime_error(std::string("SDL_Init(SDL_INIT_VIDEO) failed: ") + SDL_GetError());
  video_initialized = true;
  keyboard_scancodes.clear();
  for (const auto &binding : keyboard_keys)
    keyboard_scancodes.push_back(scancode_binding(binding));
  // A 960x540 picture by default, or the output size (GT4_OUTPUT_SIZE) shrunk with its shape to fit the display.
  std::uint32_t width = output.known() ? output.width : 960u, height = output.known() ? output.height : 540u;
  SDL_Rect usable{};
  const SDL_DisplayID display = SDL_GetPrimaryDisplay();
  if (display && SDL_GetDisplayUsableBounds(display, &usable)) {
    const float scale = SDL_GetDisplayContentScale(display) > 0.0f ? SDL_GetDisplayContentScale(display) : 1.0f;
    // The output size is in pixels; SDL window sizes are in points.
    const auto client = gt4::window_mode::fit_client(
        static_cast<std::uint32_t>(width / scale), static_cast<std::uint32_t>(height / scale), usable.w, usable.h);
    width = static_cast<std::uint32_t>(client.width);
    height = static_cast<std::uint32_t>(client.height);
  }
  game_window = SDL_CreateWindow(window_title, static_cast<int>(width), static_cast<int>(height),
                                 SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY | SDL_WINDOW_METAL);
  if (!game_window)
    throw std::runtime_error(std::string("Cannot create native game window: ") + SDL_GetError());
  metal_view = SDL_Metal_CreateView(game_window);
  if (!metal_view)
    throw std::runtime_error(std::string("Cannot create the Metal view of the game window: ") + SDL_GetError());
  // Start in borderless fullscreen on the window's display: the same path as Alt+Enter and F11.
  if (start_fullscreen)
    set_fullscreen(true);
  std::uint32_t pixel_width = 0, pixel_height = 0;
  pixel_size(pixel_width, pixel_height);
  gt4::display_aspect::set_window_client_size(pixel_width, pixel_height);
  std::fprintf(stderr, "[window] %s start (GT4_FULLSCREEN), %ux%u points, %ux%u pixels\n",
               start_fullscreen ? "fullscreen" : "windowed", width, height, pixel_width, pixel_height);
  return true;
}

#ifdef GT4_MEMCARD_FLUSH_OVERLAY
namespace ps2::iop::sio2 {
void flush_cards_now(); // memcard capsule sio2.cpp (scripts/prepare_memcard_flush.py)
}
#endif

int run_window(const std::function<int()> &emulate) {
  ControllerInput input(active_controls, input_backend);
  controller = &input;
  const auto cleanup = [&]() {
#ifdef GT4_PERF_PROBE
    gt4::perf::Probe::shared().set_report_section({});
    gt4::perf::Probe::shared().finish();
#endif
    audio_output = nullptr;
    frame_pacer.reset();
    frame_clock.reset();
    ps2::set_audio_sink({});
    ps2::g_options.on_vblank = {};
    input.stop();
    controller = nullptr;
    surface_attached = false;
    unlock_memory_card();
    if (metal_view)
      SDL_Metal_DestroyView(metal_view);
    metal_view = nullptr;
    if (game_window)
      SDL_DestroyWindow(game_window);
    game_window = nullptr;
    if (video_initialized)
      SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_EVENTS);
    video_initialized = false;
  };
  try {
    force_480p_enabled = gt4::display::parse_force_480p(std::getenv("GT4_FORCE_480P"));
    force_480p_state = {};
    if (force_480p_enabled)
      std::fprintf(stderr, "[display] GT4_FORCE_480P=1: race display index held at 480p (guest VBlank)\n");
    // TASK-079: an invalid GT4_FORCE_WIDESCREEN stops the start here (the hold itself runs at guest VBlank).
    gt4::display::widescreen_hold_enabled();
    pacing_mode = gt4::pacing::parse_mode(std::getenv("GT4_PACING"));
    if (const char *deinterlace = std::getenv("GT4_DEINTERLACE"); deinterlace && *deinterlace) {
      if (std::strcmp(deinterlace, "blend") != 0 && std::strcmp(deinterlace, "off") != 0)
        throw std::invalid_argument("GT4_DEINTERLACE must be blend or off");
      blend_interlaced_fields = std::strcmp(deinterlace, "blend") == 0;
    }
    std::fprintf(stderr, "[window] interlaced fields: %s (GT4_DEINTERLACE)\n",
                 blend_interlaced_fields ? "blend" : "off");
    cursor_autohide = gt4::cursor::AutoHide(gt4::cursor::parse_policy(std::getenv("GT4_CURSOR_AUTOHIDE")));
    std::fprintf(stderr, "[window] cursor auto-hide %s (GT4_CURSOR_AUTOHIDE; %u ms without movement over the picture)\n",
                 cursor_autohide.policy().auto_hide ? "on" : "off", cursor_autohide.policy().hide_delay_ms);
#ifdef GT4_GS_STREAM_CLIENT
    gt4::gs_stream::set_cursor_policy(cursor_autohide.policy().auto_hide, cursor_autohide.policy().hide_delay_ms);
#endif
    frame_clock = std::make_unique<FrameClock>();
    frame_pacer = std::make_unique<gt4::pacing::FramePacer>(
        frame_clock->frequency(), gt4::pacing::guest_vblank_rate);
    pacing_diagnostics.reset();
    counters_at_last_report = {};
    std::fprintf(stderr, "[pacing] mode=%s; guest VBlank %llu Hz; timer=%s\n",
                 gt4::pacing::mode_name(pacing_mode),
                 static_cast<unsigned long long>(gt4::pacing::guest_vblank_rate),
                 frame_clock->high_resolution_timer() ? "high-resolution" : "1 ms");
    lock_memory_card();
    ps2::init_graphics();
    std::uint32_t width = 0, height = 0;
    pixel_size(width, height);
    if (!ps2::gs::attach_window(3, nullptr, reinterpret_cast<std::uint64_t>(SDL_Metal_GetLayer(metal_view)), nullptr,
                                nullptr, width, height))
      throw std::runtime_error("Native Vulkan presentation refused window");
    surface_attached = true;
    // The presentation is 16:9 pillarbox; TASK-080 fills the screen in the race view at other ratios.
    ps2::gs::gpu::set_widescreen(true);
    gt4::display_aspect::set_presentation_sink(present_race_view);
    std::fprintf(stderr,
                 "[window] real guest GPU output through native Vulkan (MoltenVK)\n");
    ps2::g_options.on_vblank = on_vblank;
    AudioOutput audio(pump_messages, pacing_mode);
    audio_output = &audio;
#ifdef GT4_PERF_PROBE
    gt4::perf::Probe::shared().set_report_section([](std::FILE *output) {
      // F8 report: counter differences since the last F7 or report, then totals.
      const gt4::pacing::Counters session = pacing_counters();
      pacing_diagnostics.format(output, pacing_mode,
                                session.since(counters_at_last_report), session);
      if (force_480p_enabled)
        std::fprintf(output, "[display] GT4_FORCE_480P: race display index writes %llu\n",
                     static_cast<unsigned long long>(force_480p_state.writes));
      counters_at_last_report = session;
      pacing_diagnostics.reset();
#ifdef GT4_MTVU_MEASURE
      // TASK-011 step 0: interval counters since the last F7 or report, then a new interval.
      gt4::mtvu::report(output, "interval");
      gt4::mtvu::reset_interval();
#endif
    });
#endif
    ps2::set_audio_sink(
        [&audio](const std::int16_t *samples, std::size_t frames) {
          if (!audio.push(samples, frames))
            ps2::halt("window closed");
        });
    int result = 1;
    try {
      result = emulate();
    } catch (...) {
      ps2::set_audio_sink({});
      throw;
    }
    // Exit path (TASK-025 Part A / TASK-058): a save made less than 50 VBlanks before the window closed is written
    // now. emulate() returns normally after halt(), so this runs on every exit.
#ifdef GT4_MEMCARD_FLUSH_OVERLAY
    ps2::iop::sio2::flush_cards_now();
#endif
    ps2::set_audio_sink({});
    audio.close(!closing && result == 0);
    audio_output = nullptr;
    cleanup();
    return result;
  } catch (const std::exception &error) {
    cleanup();
    std::fprintf(stderr, "[host] audio/input/window failure: %s\n",
                 error.what());
    return 1;
  }
}
