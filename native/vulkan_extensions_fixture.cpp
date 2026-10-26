// CTest native_vulkan_extensions (TASK-081): the pure extension selection of vulkan_extensions.cpp.

#include "vulkan_extensions.hpp"

#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using gt4::vulkan::DeviceChoice;
using gt4::vulkan::InstanceChoice;
using gt4::vulkan::MaintenanceFamily;
using gt4::vulkan::parse_force_baseline;
using gt4::vulkan::select_device_extensions;
using gt4::vulkan::select_instance_extensions;
using List = std::vector<std::string>;

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[vulkan-extensions] FAIL: %s\n", what);
    ++failures;
  }
}

template <class F> bool throws(F &&body) {
  try {
    body();
  } catch (const std::exception &) {
    return true;
  }
  return false;
}

const List kBase = {"VK_KHR_surface", "VK_KHR_win32_surface"};

List with(List list, std::initializer_list<const char *> more) {
  for (const char *name : more)
    list.emplace_back(name);
  return list;
}

// The Windows selection (Win32 surface, no portability), whatever platform builds the fixture.
InstanceChoice select_win32(const List &available, bool force_baseline) {
  return select_instance_extensions(available, force_baseline, "VK_KHR_win32_surface", false);
}

// The macOS selection (MoltenVK: Metal surface, portability enumeration).
InstanceChoice select_metal(const List &available, bool force_baseline) {
  return select_instance_extensions(available, force_baseline, "VK_EXT_metal_surface", true);
}

} // namespace

int main() {
  // The switch.
  expect(!parse_force_baseline(nullptr) && !parse_force_baseline("") && !parse_force_baseline("0"), "unset/0 = auto");
  expect(parse_force_baseline("1"), "1 forces the baseline");
  expect(throws([] { parse_force_baseline("yes"); }), "other values are refused");

  // Instance: required pair only on an old driver.
  {
    const InstanceChoice old = select_win32(with(kBase, {"VK_EXT_debug_utils"}), false);
    expect(old.extensions == kBase && old.family == MaintenanceFamily::none, "old driver: surface + win32 only");
  }
  // Instance: KHR family (this machine, 2025+ drivers).
  const List khr_instance = with(kBase, {"VK_KHR_get_surface_capabilities2", "VK_KHR_surface_maintenance1",
                                         "VK_EXT_surface_maintenance1"});
  {
    const InstanceChoice khr = select_win32(khr_instance, false);
    expect(khr.family == MaintenanceFamily::khr, "KHR family preferred");
    expect(khr.extensions == with(kBase, {"VK_KHR_get_surface_capabilities2", "VK_KHR_surface_maintenance1"}),
           "KHR instance list");
    const InstanceChoice forced = select_win32(khr_instance, true);
    expect(forced.extensions == kBase && forced.family == MaintenanceFamily::none, "forced baseline drops both");
  }
  // Instance: EXT family (2023-2024 drivers).
  {
    const InstanceChoice ext = select_win32(
        with(kBase, {"VK_KHR_get_surface_capabilities2", "VK_EXT_surface_maintenance1"}), false);
    expect(ext.family == MaintenanceFamily::ext, "EXT family");
    expect(ext.extensions == with(kBase, {"VK_KHR_get_surface_capabilities2", "VK_EXT_surface_maintenance1"}),
           "EXT instance list");
  }
  // Instance: surface_maintenance1 without its prerequisite is not used.
  {
    const InstanceChoice lone = select_win32(with(kBase, {"VK_KHR_surface_maintenance1"}), false);
    expect(lone.family == MaintenanceFamily::none && lone.extensions == kBase, "no capabilities2: baseline");
  }
  // Instance: missing required extensions refuse.
  expect(throws([] { select_win32({"VK_KHR_surface"}, false); }), "no win32 surface refuses");
  expect(throws([] { select_win32({"VK_KHR_win32_surface"}, true); }), "no surface refuses");

  // Instance on macOS (MoltenVK 1.4 on an M3 lists both maintenance families): the Metal surface, the KHR family and
  // the portability enumeration last.
  {
    const List moltenvk = {"VK_KHR_surface", "VK_EXT_metal_surface", "VK_KHR_get_surface_capabilities2",
                           "VK_KHR_surface_maintenance1", "VK_EXT_surface_maintenance1",
                           "VK_KHR_portability_enumeration"};
    const InstanceChoice metal = select_metal(moltenvk, false);
    expect(metal.portability_enumeration && metal.family == MaintenanceFamily::khr &&
               metal.extensions == List({"VK_KHR_surface", "VK_EXT_metal_surface", "VK_KHR_get_surface_capabilities2",
                                         "VK_KHR_surface_maintenance1", "VK_KHR_portability_enumeration"}),
           "macOS instance list");
    const InstanceChoice forced = select_metal(moltenvk, true);
    expect(forced.portability_enumeration &&
               forced.extensions == List({"VK_KHR_surface", "VK_EXT_metal_surface", "VK_KHR_portability_enumeration"}),
           "macOS forced baseline keeps the portability enumeration");
    expect(!select_win32(with(kBase, {"VK_KHR_portability_enumeration"}), false).portability_enumeration,
           "Windows never enumerates portability drivers");
    expect(throws([] { select_metal({"VK_KHR_surface", "VK_EXT_metal_surface"}, false); }),
           "macOS without portability enumeration refuses");
    expect(throws([] { select_metal(kBase, false); }), "macOS without a Metal surface refuses");
  }

  // Device.
  const List swapchain = {"VK_KHR_swapchain"};
  const List both_device = {"VK_KHR_swapchain", "VK_KHR_swapchain_maintenance1", "VK_EXT_swapchain_maintenance1"};
  {
    const DeviceChoice fast = select_device_extensions(both_device, MaintenanceFamily::khr, true, false);
    expect(fast.present_fences && fast.extensions == List({"VK_KHR_swapchain", "VK_KHR_swapchain_maintenance1"}) &&
               std::string(fast.path) == "khr-maintenance1",
           "KHR device path");
    const DeviceChoice ext = select_device_extensions(both_device, MaintenanceFamily::ext, true, false);
    expect(ext.present_fences && ext.extensions == List({"VK_KHR_swapchain", "VK_EXT_swapchain_maintenance1"}) &&
               std::string(ext.path) == "ext-maintenance1",
           "EXT device path matches the instance family");
    const DeviceChoice no_feature = select_device_extensions(both_device, MaintenanceFamily::khr, false, false);
    expect(!no_feature.present_fences && no_feature.extensions == swapchain, "feature off: baseline");
    const DeviceChoice no_instance = select_device_extensions(both_device, MaintenanceFamily::none, true, false);
    expect(!no_instance.present_fences && no_instance.extensions == swapchain, "instance baseline: device baseline");
    const DeviceChoice old = select_device_extensions(swapchain, MaintenanceFamily::khr, false, false);
    expect(!old.present_fences && std::string(old.path) == "baseline", "old device: baseline");
    const DeviceChoice mismatch =
        select_device_extensions({"VK_KHR_swapchain", "VK_EXT_swapchain_maintenance1"}, MaintenanceFamily::khr, true,
                                 false);
    expect(!mismatch.present_fences, "KHR instance with an EXT-only device: baseline");
    const DeviceChoice forced = select_device_extensions(both_device, MaintenanceFamily::khr, true, true);
    expect(!forced.present_fences && forced.extensions == swapchain, "forced baseline on the device");
  }
  expect(throws([] { select_device_extensions({}, MaintenanceFamily::none, false, false); }),
         "no VK_KHR_swapchain refuses");
  // Device on MoltenVK: the portability subset is enabled whenever it is listed.
  {
    const DeviceChoice moltenvk = select_device_extensions(
        {"VK_KHR_swapchain", "VK_KHR_swapchain_maintenance1", "VK_KHR_portability_subset"}, MaintenanceFamily::khr,
        true, false);
    expect(moltenvk.present_fences &&
               moltenvk.extensions ==
                   List({"VK_KHR_swapchain", "VK_KHR_swapchain_maintenance1", "VK_KHR_portability_subset"}),
           "MoltenVK device list");
    const DeviceChoice forced = select_device_extensions({"VK_KHR_swapchain", "VK_KHR_portability_subset"},
                                                         MaintenanceFamily::none, false, true);
    expect(!forced.present_fences && forced.extensions == List({"VK_KHR_swapchain", "VK_KHR_portability_subset"}),
           "portability subset on the baseline path");
  }

  if (failures) {
    std::fprintf(stderr, "[vulkan-extensions] %d failure(s)\n", failures);
    return 1;
  }
  std::fprintf(stderr, "[vulkan-extensions] PASS\n");
  return 0;
}
