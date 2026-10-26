#pragma once

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#define VK_NO_PROTOTYPES
#define VK_USE_PLATFORM_WIN32_KHR
#include <vulkan/vulkan.h>
#else
#define VK_NO_PROTOTYPES
#define VK_USE_PLATFORM_METAL_EXT
#include <vulkan/vulkan.h>
// macOS (MoltenVK): the game window handle passed through gs::attach_window (surface kind 3, gpu_tail.inc) is the
// CAMetalLayer of the SDL3 game window (window_sdl.cpp), and the Vulkan loader is a dlopen handle. The Win32 type
// names are kept so that the adapter sources derived from the donor (scripts/prepare_external_vulkan.py) are the same
// bytes on both platforms.
using HWND = void *;
using HMODULE = void *;
#endif

#include "gs_submit_ring.hpp"
#include "pacing.hpp"
#include "vulkan_extensions.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <vector>

namespace gt4::vulkan {

// The host presents 16:9 only (no environment selection). `standard` remains
// because the pinned slice153 adapter exports set_widescreen(false); the host never calls it.
enum class Aspect { widescreen, standard };

struct PresentationRect {
  std::uint32_t left, top, width, height;
};

PresentationRect presentation_rect(std::uint32_t width, std::uint32_t height,
                                   Aspect aspect);

// TASK-080: the largest centred rectangle of `ratio` (width / height) inside the client area. Pure.
PresentationRect presentation_rect_ratio(std::uint32_t width, std::uint32_t height,
                                         double ratio);

// TASK-080 (native/display_aspect.hpp): while the race view is shown at a ratio other than 16:9, the frame fills a
// rectangle of that ratio (the whole client area in "auto") with linear filtering; otherwise the fixed 16:9
// pillarbox with nearest filtering, as before. Any thread; read at the next presentation.
void set_race_view_presentation(bool fill, double ratio);

// The source of the next presentations is an interlaced field (SMODE2 INT and FFMD: the donor reads one field and
// doubles its lines). With `blend_fields` the presentation weaves the last two fields and averages each pair of lines,
// as the donor's copy_frame does, so the picture no longer bounces by one field line at every VBlank. The macOS window
// sets it at every VBlank (window_sdl.cpp, GT4_DEINTERLACE); off by default. Any thread; read at the next presentation.
void set_interlaced_presentation(bool blend_fields);

struct Buffer {
  VkBuffer handle = VK_NULL_HANDLE;
  VkDeviceMemory memory = VK_NULL_HANDLE;
  void *mapped = nullptr;
  VkDeviceSize size = 0;
};

struct Dispatch {
  std::uint32_t pipeline, x, y, parameter;
};

// One GS submission: per-slot uploads, dispatches, and an optional presentation
// of an RGBA source buffer.
struct Submission {
  const std::uint8_t *arena = nullptr;
  std::uint64_t arena_bytes = 0;
  const std::uint8_t *parameters = nullptr;
  std::uint64_t parameter_bytes = 0;
  const Dispatch *commands = nullptr;
  std::size_t command_count = 0;
  // Null presents nothing; otherwise the source is copied and blitted to the
  // swapchain as part of this submission.
  Buffer *present_source = nullptr;
  std::uint32_t present_width = 0, present_height = 0;
  // execute() uses the buffers bound at indices 2 and 3 instead of slot uploads.
  bool use_bound_buffers = false;
};

// Submissions are recorded into a ring of slots and chained on one timeline
// semaphore. The CPU waits only when a slot is still in use, when it must read
// GPU results, and at resize, state transfer and shutdown.
class Context {
public:
  static constexpr std::uint32_t kSlotCount = 3;
  // At most this many presentations may be pending in the presentation engine.
  static constexpr std::uint32_t kMaxPresentsInFlight = 2;

  ~Context();
  void initialize(const std::filesystem::path &shaders);
  Buffer *create_buffer(std::uint64_t bytes);
  void destroy_buffer(Buffer *buffer);
  void write(Buffer *buffer, std::uint64_t offset, const void *source,
             std::uint64_t bytes);
  void read(Buffer *buffer, std::uint64_t offset, void *destination,
            std::uint64_t bytes);
  // Binds the shared resources (indices 0, 1, 4-7). Indices 2 (parameters) and
  // 3 (arena data) are used only by execute(); submit() uploads into ring slots.
  void bind_buffers(const std::array<Buffer *, 8> &buffers);
  // Submits dispatches without uploads or presentation.
  void execute(const Dispatch *commands, std::size_t count);
  // Records and submits one submission and returns its timeline id, or zero
  // when there was nothing to submit. `presented` reports whether a swapchain
  // image was presented.
  std::uint64_t submit(const Submission &submission, bool *presented = nullptr);
  // Id that the next submission will receive.
  std::uint64_t next_submission() const { return ring_->next_id(); }
  // Last submission known to have completed (non-blocking query).
  std::uint64_t completed_submission();
  // Blocks until every submitted GPU operation has completed.
  void wait_submissions();
  void wait_idle();
  void attach_window(HWND window, std::uint32_t width, std::uint32_t height);
  void resize(std::uint32_t width, std::uint32_t height);
  void set_aspect(Aspect aspect) { aspect_ = aspect; }
  bool has_window() const { return window_ != nullptr; }
  bool synchronous() const { return synchronous_; }
  // Device maximum workgroup count for axis 0 (x) or 1 (y).
  std::uint32_t max_workgroup_count(int axis) const {
    return limits_.maxComputeWorkGroupCount[axis];
  }
  std::uint64_t presentations() const { return presentations_; }

private:
  struct Slot {
    VkCommandBuffer command = VK_NULL_HANDLE;
    VkDescriptorSet descriptors = VK_NULL_HANDLE;
    Buffer *data = nullptr;
    Buffer *parameters = nullptr;
    VkSemaphore acquired = VK_NULL_HANDLE;
    VkSemaphore rendered = VK_NULL_HANDLE;
    VkFence present_fence = VK_NULL_HANDLE;
    bool presented = false;
    // Timeline id of the submission that presented from this slot (baseline path: the slot is free once the GPU
    // finished it; the present semaphore is per swapchain image, see image_rendered_).
    std::uint64_t presented_id = 0;
  };

  void ensure_slot_capacity(Slot &slot, std::uint64_t arena_bytes,
                            std::uint64_t parameter_bytes);
  void update_descriptors(const Slot &slot, bool bound_buffers);
  void validate_dispatches(const Dispatch *commands, std::size_t count,
                           std::uint64_t parameter_capacity) const;
  void record_dispatches(VkCommandBuffer command, VkDescriptorSet descriptors,
                         const Dispatch *commands, std::size_t count);
  void wait_timeline(std::uint64_t value);
  void wait_presentation(Slot &slot);
  void wait_all_presentations();
  bool acquire_image(Slot &slot, const Submission &submission,
                     VkImage &target, std::uint32_t &image);
  void record_presentation(VkCommandBuffer command, const Submission &submission,
                           VkImage target);
  void ensure_display_image(std::uint32_t width, std::uint32_t height);
  void create_transfer_image(std::uint32_t width, std::uint32_t height, VkImage &image, VkDeviceMemory &memory,
                             const char *name);
  void destroy_transfer_image(VkImage &image, VkDeviceMemory &memory);
  void ensure_field_images(std::uint32_t width, std::uint32_t height);
  VkImage record_field_blend(VkCommandBuffer command, std::uint32_t width, std::uint32_t height);
  void record_present_dump(VkCommandBuffer command, VkImage source, std::uint32_t width, std::uint32_t height);
  void write_present_dump();
  void memory_barrier(VkCommandBuffer command, VkPipelineStageFlags source,
                      VkPipelineStageFlags destination, VkAccessFlags writes,
                      VkAccessFlags reads);
  void rebuild_swapchain();
  void destroy_image();
  void image_barrier(VkCommandBuffer command, VkImage image,
                     VkImageLayout old_layout, VkImageLayout new_layout,
                     VkPipelineStageFlags source,
                     VkPipelineStageFlags destination, VkAccessFlags writes,
                     VkAccessFlags reads);

  HMODULE loader_ = nullptr;
  VkInstance instance_ = VK_NULL_HANDLE;
  VkPhysicalDevice physical_ = VK_NULL_HANDLE;
  VkDevice device_ = VK_NULL_HANDLE;
  VkQueue queue_ = VK_NULL_HANDLE;
  std::uint32_t queue_family_ = 0;
  VkPhysicalDeviceMemoryProperties memory_properties_{};
  VkPhysicalDeviceLimits limits_{};
  std::vector<Buffer *> buffers_;
  std::array<Buffer *, 8> shared_{};
  VkCommandPool command_pool_ = VK_NULL_HANDLE;
  VkDescriptorSetLayout descriptor_layout_ = VK_NULL_HANDLE;
  VkPipelineLayout pipeline_layout_ = VK_NULL_HANDLE;
  VkDescriptorPool descriptor_pool_ = VK_NULL_HANDLE;
  std::array<VkPipeline, 9> pipelines_{};
  VkSemaphore timeline_ = VK_NULL_HANDLE;
  std::array<Slot, kSlotCount> slots_{};
  std::unique_ptr<SubmitRing> ring_;
  bool synchronous_ = false;
  // GT4_PRESENT_MODE; fifo unless overridden for experiments.
  gt4::pacing::PresentMode present_mode_ = gt4::pacing::PresentMode::fifo;
  HWND window_ = nullptr;
  VkSurfaceKHR surface_ = VK_NULL_HANDLE;
  VkSwapchainKHR swapchain_ = VK_NULL_HANDLE;
  VkImage display_image_ = VK_NULL_HANDLE;
  VkDeviceMemory display_memory_ = VK_NULL_HANDLE;
  // Interlaced field blend (set_interlaced_presentation): the woven last two fields (the rows of the newest field's
  // parity are replaced at each presentation), its 2:1 row average, and that average at the display height.
  VkImage woven_image_ = VK_NULL_HANDLE, field_average_image_ = VK_NULL_HANDLE, blended_image_ = VK_NULL_HANDLE;
  VkDeviceMemory woven_memory_ = VK_NULL_HANDLE, field_average_memory_ = VK_NULL_HANDLE,
                 blended_memory_ = VK_NULL_HANDLE;
  std::uint32_t field_width_ = 0, field_height_ = 0;
  bool blend_presentation_ = false; // this presentation blends fields (set by acquire_image)
  bool woven_valid_ = false;        // the woven image holds two fields of the current size
  std::uint32_t woven_parity_ = 0;  // rows replaced by the next field
  // GT4_PRESENT_DUMP=<folder> (tests): the picture of presentations GT4_PRESENT_DUMP_FRAMES=first:last (counted from
  // 0) before its scaling to the window, written as P6 files once the GPU has finished it.
  std::filesystem::path dump_directory_;
  std::uint64_t dump_first_ = 0, dump_last_ = 0;
  Buffer *dump_buffer_ = nullptr;
  std::uint32_t dump_width_ = 0, dump_height_ = 0;
  bool dump_pending_ = false;
  std::uint32_t image_width_ = 0, image_height_ = 0;
  std::uint32_t window_width_ = 0, window_height_ = 0;
  VkExtent2D extent_{};
  Aspect aspect_ = Aspect::widescreen;
  bool resized_ = false;
  // TASK-081: swapchain maintenance 1 present fences when the driver has them (present_fences_), else the baseline
  // path with one present semaphore per swapchain image. GT4_VULKAN_FORCE_BASELINE=1 forces the baseline.
  bool force_baseline_ = false;
  bool present_fences_ = false;
  MaintenanceFamily maintenance_family_ = MaintenanceFamily::none;
  std::vector<VkSemaphore> image_rendered_;
  std::uint64_t presentations_ = 0;
  std::uint64_t zero_dispatches_ = 0;
};

} // namespace gt4::vulkan
