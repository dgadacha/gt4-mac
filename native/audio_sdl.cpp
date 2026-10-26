// AudioOutput on macOS and other POSIX hosts (host_io.hpp); host_io.cpp holds the Windows (WinMM) output.
//
// An SDL3 audio stream at 48 kHz stereo 16-bit, with the buffer sizes, latency target and rate control of the WinMM
// path. The frames queued in the stream play the part of the WinMM buffer queue: the blocking path waits while the
// device holds a full set of buffers, and the paced path tops the device up from the ring without ever waiting.
// GT4_MUTE=1 plays the output at zero gain on the real device: silent, with the device's own clock (test runs).
// SDL_AUDIODRIVER=dummy also plays nothing, but its clock runs about 1 percent slow, so the paced ring overflows.

#include "host_io.hpp"
#include "perf_probe.hpp"

#include <SDL3/SDL.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace {
// The same sizes as the WinMM path (host_io.cpp).
// Blocking audio path: four 512-frame buffers, as before the paced mode.
constexpr std::size_t blocking_frames_per_buffer = 512;
constexpr std::size_t blocking_buffer_count = 4;
// Paced path: sixteen 256-frame buffers (5.3 ms each) under a 60 ms target.
constexpr std::size_t paced_frames_per_buffer = 256;
constexpr std::size_t paced_buffer_count = 16;
constexpr std::size_t bytes_per_frame = 4;
} // namespace

AudioOutput::AudioOutput(std::function<bool()> pump_messages, gt4::pacing::Mode mode)
    : mode_(mode), pump_messages_(std::move(pump_messages)) {
  const bool paced = mode_ == gt4::pacing::Mode::paced;
  frames_per_buffer_ = paced ? paced_frames_per_buffer : blocking_frames_per_buffer;
  buffer_count_ = paced ? paced_buffer_count : blocking_buffer_count;
  if (!SDL_InitSubSystem(SDL_INIT_AUDIO))
    throw std::runtime_error(std::string("SDL_InitSubSystem(SDL_INIT_AUDIO) failed: ") + SDL_GetError());
  audio_subsystem_ = true;
  const SDL_AudioSpec spec{SDL_AUDIO_S16, 2, 48000};
  device_ = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, nullptr, nullptr);
  if (!device_) {
    const std::string error = SDL_GetError();
    close(false);
    throw std::runtime_error("SDL_OpenAudioDeviceStream stereo16/48000 failed: " + error);
  }
  const char *mute = std::getenv("GT4_MUTE");
  const bool muted = mute && std::strcmp(mute, "1") == 0;
  if (muted && !SDL_SetAudioStreamGain(device_, 0.0f)) {
    const std::string error = SDL_GetError();
    close(false);
    throw std::runtime_error("SDL_SetAudioStreamGain failed: " + error);
  }
  // A device stream starts paused.
  if (!SDL_ResumeAudioStreamDevice(device_)) {
    const std::string error = SDL_GetError();
    close(false);
    throw std::runtime_error("SDL_ResumeAudioStreamDevice failed: " + error);
  }
  const char *driver = SDL_GetCurrentAudioDriver();
  if (paced)
    std::fprintf(stderr,
                 "[audio] SDL (%s) PCM stereo16 48000 Hz, paced: %zu x %zu frames, 60 ms target, non-blocking, "
                 "rate control +-0.5 percent%s\n",
                 driver ? driver : "unknown", buffer_count_, frames_per_buffer_, muted ? ", muted (GT4_MUTE=1)" : "");
  else
    std::fprintf(stderr, "[audio] SDL (%s) PCM stereo16 48000 Hz, 4 x 512 frames%s\n", driver ? driver : "unknown",
                 muted ? ", muted (GT4_MUTE=1)" : "");
}

AudioOutput::~AudioOutput() {
  try {
    close(false);
  } catch (const std::exception &error) {
    std::fprintf(stderr, "[audio] fatal cleanup failure: %s\n", error.what());
    std::terminate();
  }
}

std::size_t AudioOutput::queued_device_frames() const {
  if (!device_)
    return 0;
  const int bytes = SDL_GetAudioStreamQueued(device_);
  return bytes > 0 ? static_cast<std::size_t>(bytes) / bytes_per_frame : 0;
}

std::size_t AudioOutput::queued_device_buffers() const {
  return (queued_device_frames() + frames_per_buffer_ - 1) / frames_per_buffer_;
}

// Counts the frames the device consumed since the last call (the WinMM "done" buffers).
std::size_t AudioOutput::reap() {
  const std::uint64_t queued = queued_device_frames();
  const std::uint64_t played = submitted_ > queued ? submitted_ - queued : 0;
  if (played > completed_) {
#if defined(GT4_PERF_PROBE) && !defined(GT4_PERF_FRAME_ONLY)
    gt4::perf::Probe::shared().audio(0, played - completed_);
#endif
    completed_ = played;
  }
  return queued_device_buffers();
}

bool AudioOutput::wait_until_queued_at_most(std::size_t frames) {
  const std::uint64_t deadline = SDL_GetTicks() + 5000;
  for (;;) {
    reap();
    if (queued_device_frames() <= frames)
      return true;
    if (pump_messages_ && !pump_messages_())
      return false;
    if (SDL_GetTicks() >= deadline)
      throw std::runtime_error("Audio device stalled for five seconds");
    ++waits_;
    GT4_PERF_SCOPE(gt4::perf::Category::audio_wait);
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
}

bool AudioOutput::submit() {
  if (!pending_frames_)
    return true;
  // A free "buffer": the device holds at most buffer_count_ - 1 of them.
  if (!wait_until_queued_at_most((buffer_count_ - 1) * frames_per_buffer_))
    return false;
  const auto queued = reap();
  if (!queued && submitted_) {
    ++empty_queue_;
#if defined(GT4_PERF_PROBE) && !defined(GT4_PERF_FRAME_ONLY)
    gt4::perf::Probe::shared().audio(0, 0, 1);
#endif
  }
  if (!SDL_PutAudioStreamData(device_, pending_.data(), static_cast<int>(pending_frames_ * bytes_per_frame)))
    throw std::runtime_error(std::string("SDL_PutAudioStreamData failed: ") + SDL_GetError());
  submitted_ += pending_frames_;
  peak_ = std::max(peak_, queued + 1);
  pending_frames_ = 0;
  return true;
}

void AudioOutput::submit_paced_block() {
  // Callers check that at least one full block is in the ring.
  ring_.read(block_.data(), frames_per_buffer_);
  if (!SDL_PutAudioStreamData(device_, block_.data(), static_cast<int>(frames_per_buffer_ * bytes_per_frame)))
    throw std::runtime_error(std::string("SDL_PutAudioStreamData failed: ") + SDL_GetError());
  submitted_ += frames_per_buffer_;
  peak_ = std::max(peak_, queued_device_buffers());
}

bool AudioOutput::push_paced(const std::int16_t *samples, std::size_t frames) {
  converted_.clear();
  const std::size_t produced = resampler_.process(samples, frames, converted_);
  const std::size_t accepted = ring_.write(converted_.data(), produced);
  overflow_frames_ += produced - accepted;
  return true;
}

bool AudioOutput::push(const std::int16_t *samples, std::size_t frames) {
  GT4_PERF_SCOPE(gt4::perf::Category::audio_push);
  if (!device_ || (frames && !samples))
    throw std::runtime_error("Invalid audio sink input/lifetime");
  received_ += frames;
#if defined(GT4_PERF_PROBE) && !defined(GT4_PERF_FRAME_ONLY)
  gt4::perf::Probe::shared().audio(frames, 0);
#endif
  if (mode_ == gt4::pacing::Mode::paced)
    return push_paced(samples, frames);
  while (frames) {
    const auto count = std::min(frames, frames_per_buffer_ - pending_frames_);
    std::copy_n(samples, count * 2, pending_.data() + pending_frames_ * 2);
    samples += count * 2;
    frames -= count;
    pending_frames_ += count;
    if (pending_frames_ == frames_per_buffer_ && !submit())
      return false;
  }
  return true;
}

void AudioOutput::pump() {
  if (mode_ != gt4::pacing::Mode::paced || !device_)
    return;
  reap();
  if (!started_ && ring_.size() >= gt4::pacing::target_latency_frames)
    started_ = true;
  if (!started_)
    return;
  // Nothing queued on the device after audio was submitted: the device starved.
  if (!queued_device_frames() && submitted_)
    ++underruns_;
  // The controller sees the whole queue: device plus ring.
  resampler_.set_ratio(controller_.update(static_cast<double>(queued_frames())));
  // Submit only while the device stays within the target: the excess waits in
  // the ring, where the controller can see it.
  while (ring_.size() >= frames_per_buffer_ &&
         queued_device_frames() + frames_per_buffer_ <= gt4::pacing::target_latency_frames)
    submit_paced_block();
}

std::uint64_t AudioOutput::queued_frames() {
  reap();
  const std::uint64_t device = queued_device_frames();
  return device + (mode_ == gt4::pacing::Mode::paced ? ring_.size() : pending_frames_);
}

void AudioOutput::close(bool drain) {
  if (device_) {
    if (drain && submit()) {
      SDL_FlushAudioStream(device_);
      wait_until_queued_at_most(0);
    }
    reap();
    canceled_ += queued_device_frames();
    SDL_ClearAudioStream(device_);
    // Destroying a device stream also closes its device.
    SDL_DestroyAudioStream(device_);
    device_ = nullptr;
    std::fprintf(
        stderr,
        "[audio] received=%llu submitted=%llu completed=%llu canceled=%llu "
        "pending=%zu peak=%zu waits=%llu empty_queue=%llu\n",
        static_cast<unsigned long long>(received_),
        static_cast<unsigned long long>(submitted_),
        static_cast<unsigned long long>(completed_),
        static_cast<unsigned long long>(canceled_), pending_frames_, peak_,
        static_cast<unsigned long long>(waits_),
        static_cast<unsigned long long>(empty_queue_));
    if (mode_ == gt4::pacing::Mode::paced)
      std::fprintf(stderr,
                   "[audio] paced: underruns=%llu ring_overflow_frames=%llu "
                   "ring_left=%zu ratio=%.6f\n",
                   static_cast<unsigned long long>(underruns_),
                   static_cast<unsigned long long>(overflow_frames_),
                   ring_.size(), resampler_.ratio());
  }
  if (audio_subsystem_) {
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
    audio_subsystem_ = false;
  }
}
