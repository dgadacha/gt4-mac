#pragma once

// Vulkan extension selection for the native GS backend (TASK-081, release blocker for 1.0.0).
//
// The game needs only VK_KHR_surface and the platform surface extension (instance) and VK_KHR_swapchain (device) on a
// Vulkan 1.2 GPU. Swapchain maintenance 1 (present fences) is used when the driver has it, in its KHR form (2025+
// drivers) or its older EXT form (2023+ drivers), with its instance prerequisites (get_surface_capabilities2 and
// surface_maintenance1 of the same family). Without it the backend waits on the GS timeline for a slot and uses one
// present semaphore per swapchain image (the plain VK_KHR_swapchain path). These functions are pure: lists in, choices
// out.
//
// macOS: Vulkan runs on MoltenVK, a portability implementation. The instance must enable
// VK_KHR_portability_enumeration (and set VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR) to see it, and a device
// that lists VK_KHR_portability_subset must have it enabled. The surface is VK_EXT_metal_surface.

#include <string>
#include <vector>

namespace gt4::vulkan {

// The instance extension that creates a surface for this platform's game window.
#if defined(__APPLE__)
inline constexpr const char *kPlatformSurfaceExtension = "VK_EXT_metal_surface";
inline constexpr bool kPortabilityPlatform = true;
#else
inline constexpr const char *kPlatformSurfaceExtension = "VK_KHR_win32_surface";
inline constexpr bool kPortabilityPlatform = false;
#endif

// Which swapchain-maintenance family the instance enabled.
enum class MaintenanceFamily { none, ext, khr };

const char *maintenance_family_name(MaintenanceFamily family);

struct InstanceChoice {
  std::vector<std::string> extensions; // in the order they are passed to vkCreateInstance
  MaintenanceFamily family = MaintenanceFamily::none;
  // VK_KHR_portability_enumeration is in `extensions`: create the instance with
  // VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR.
  bool portability_enumeration = false;
};

struct DeviceChoice {
  std::vector<std::string> extensions; // in the order they are passed to vkCreateDevice
  bool present_fences = false;         // swapchain maintenance 1 enabled (VkSwapchainPresentFenceInfo)
  const char *path = "baseline";       // "khr-maintenance1", "ext-maintenance1" or "baseline"
};

// GT4_VULKAN_FORCE_BASELINE: unset, empty or "0" = automatic; "1" = always the baseline path. Anything else throws
// std::invalid_argument.
bool parse_force_baseline(const char *value);

// Throws std::runtime_error naming a missing required instance extension (VK_KHR_surface, `surface_extension`).
// `portability` (macOS) also requires VK_KHR_portability_enumeration, appended last.
InstanceChoice select_instance_extensions(const std::vector<std::string> &available, bool force_baseline,
                                          const char *surface_extension = kPlatformSurfaceExtension,
                                          bool portability = kPortabilityPlatform);

// `swapchain_maintenance_feature` is VkPhysicalDeviceSwapchainMaintenance1Features::swapchainMaintenance1 as queried
// for the device (false when it could not be queried). Throws std::runtime_error when VK_KHR_swapchain is missing.
// VK_KHR_portability_subset is appended last whenever the device lists it (the specification requires it then).
DeviceChoice select_device_extensions(const std::vector<std::string> &available, MaintenanceFamily instance_family,
                                      bool swapchain_maintenance_feature, bool force_baseline);

// The device extension name of a family ("VK_KHR_swapchain_maintenance1", "VK_EXT_swapchain_maintenance1"), or
// nullptr for none.
const char *swapchain_maintenance_extension(MaintenanceFamily family);

} // namespace gt4::vulkan
