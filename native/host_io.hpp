#pragma once
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
// clang-format off
#include <windows.h>
#include <mmsystem.h>
#include <Xinput.h>
// clang-format on
#endif

#include "controls.hpp"
#include "pacing.hpp"
#include "pad_mapping.hpp"

#include <array>
#include <cstdint>
#include <functional>
#include <vector>

// TASK-075: the PS2 pad state lives in pad_mapping.hpp (shared with the SDL3 path).
using PadState = gt4::pad::PadState;

// SDL3 gamepad handle (SDL_gamepad.h); the header is kept out of this file.
struct SDL_Gamepad;

// One standardized SDL3 gamepad reading, shared by live polling and the virtual-device fixture.
gt4::pad::GamepadReading read_sdl_gamepad(SDL_Gamepad *gamepad);

#if defined(_WIN32)
// Maps one XInput state through the binding table. The default-argument overload
// uses controls::default_controls(), which equals the slice 157 mapping.
PadState map_gamepad(const XINPUT_GAMEPAD &gamepad, const gt4::controls::ControlMap &map);
PadState map_gamepad(const XINPUT_GAMEPAD &gamepad);
XINPUT_VIBRATION map_rumble(std::uint16_t rumble);
#endif
void merge_keyboard(PadState &pad, std::uint16_t buttons);

// Player 1's pad. GT4_INPUT=sdl (default): SDL3 gamepad subsystem only, no SDL window; the first connected pad is
// player 1, and hot-plug is polled. GT4_INPUT=xinput: the previous XInput path (Windows only).
class ControllerInput {
public:
  explicit ControllerInput(gt4::controls::ControlMap map = gt4::controls::default_controls(),
                           gt4::pad::Backend backend = gt4::pad::Backend::sdl);
  ~ControllerInput();
  ControllerInput(const ControllerInput &) = delete;
  ControllerInput &operator=(const ControllerInput &) = delete;
  PadState poll(bool focused, std::uint16_t keyboard_buttons);
  void rumble(std::uint16_t value);
  void stop();
  gt4::pad::Backend backend() const { return backend_; }

private:
  PadState poll_xinput(bool focused);
  PadState poll_sdl(bool focused);
  void rumble_xinput(std::uint16_t value);
  void rumble_sdl(std::uint16_t value);
  void close_sdl_pad();

  gt4::controls::ControlMap map_;
  gt4::pad::Backend backend_;
#if defined(_WIN32)
  DWORD slot_ = XUSER_MAX_COUNT;
  ULONGLONG next_scan_ = 0;
#endif
  SDL_Gamepad *sdl_pad_ = nullptr;
  std::uint64_t sdl_next_scan_ = 0;
  std::uint64_t rumble_sent_at_ = 0;
  bool sdl_initialized_ = false;
  std::uint16_t motors_ = 0;
};

// SDL3 audio stream handle (SDL_audio.h), used by the macOS audio output (audio_sdl.cpp).
struct SDL_AudioStream;

// 48 kHz stereo 16-bit output. Windows: WinMM (host_io.cpp). macOS: an SDL3 audio stream (audio_sdl.cpp), with the
// same buffer sizes, latency target and rate control.
class AudioOutput {
public:
  // `mode` selects the blocking path (audio) or the non-blocking paced
  // ring with rate control (paced); see pacing.hpp.
  explicit AudioOutput(std::function<bool()> pump_messages = {},
                       gt4::pacing::Mode mode = gt4::pacing::Mode::audio);
  ~AudioOutput();
  AudioOutput(const AudioOutput &) = delete;
  AudioOutput &operator=(const AudioOutput &) = delete;
  // Audio mode waits for a free device buffer. Paced mode never waits: the
  // frames are resampled into the ring.
  bool push(const std::int16_t *samples, std::size_t frames);
  // Paced mode: reaps finished buffers, updates the rate ratio and submits full
  // blocks while the device queue is below the latency target. Never waits.
  // Does nothing in audio mode.
  void pump();
  // Frames queued on the device plus the ring (paced) or pending (audio).
  std::uint64_t queued_frames();
  gt4::pacing::Mode mode() const { return mode_; }
  double resampler_ratio() const { return resampler_.ratio(); }
  std::uint64_t underruns() const { return underruns_; }
  std::uint64_t overflow_frames() const { return overflow_frames_; }
  std::uint64_t received_frames() const { return received_; }
  std::uint64_t completed_frames() const { return completed_; }
  std::uint64_t canceled_frames() const { return canceled_; }
  void close(bool drain);

private:
  static constexpr std::size_t max_frames_per_buffer = 512;
  static constexpr std::size_t max_buffers = 16;
#if defined(_WIN32)
  struct Buffer {
    std::array<std::int16_t, max_frames_per_buffer * 2> samples{};
    WAVEHDR header{};
    bool prepared = false;
    bool queued = false;
  };
  std::array<Buffer, max_buffers> buffers_{};
#endif
  std::array<std::int16_t, max_frames_per_buffer * 2> pending_{};
  std::size_t pending_frames_ = 0;
  std::size_t frames_per_buffer_ = 512;
  std::size_t buffer_count_ = 4;
  std::size_t next_buffer_ = 0;
  gt4::pacing::Mode mode_ = gt4::pacing::Mode::audio;
  bool started_ = false;
  gt4::pacing::FrameRing ring_{gt4::pacing::paced_ring_frames};
  gt4::pacing::LinearResampler resampler_;
  gt4::pacing::RateController controller_{
      static_cast<double>(gt4::pacing::target_latency_frames),
      1.0 / static_cast<double>(gt4::pacing::guest_vblank_rate)};
  std::vector<std::int16_t> converted_;
#if defined(_WIN32)
  HWAVEOUT device_ = nullptr;
  HANDLE event_ = nullptr;
#else
  SDL_AudioStream *device_ = nullptr;
  bool audio_subsystem_ = false;
  std::array<std::int16_t, max_frames_per_buffer * 2> block_{};
#endif
  std::function<bool()> pump_messages_;
  std::uint64_t received_ = 0, submitted_ = 0, completed_ = 0, canceled_ = 0;
  std::uint64_t empty_queue_ = 0, waits_ = 0;
  std::uint64_t underruns_ = 0, overflow_frames_ = 0;
  std::size_t peak_ = 0;
  std::size_t reap();
  std::size_t queued_device_buffers() const;
#if defined(_WIN32)
  bool wait_for(Buffer *buffer);
#else
  // Frames the device has not played yet, and a wait until at most `frames` remain.
  std::size_t queued_device_frames() const;
  bool wait_until_queued_at_most(std::size_t frames);
#endif
  bool submit();
  bool push_paced(const std::int16_t *samples, std::size_t frames);
  void submit_paced_block();
};
