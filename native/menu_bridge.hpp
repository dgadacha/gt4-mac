#pragma once

// In-game Graphics menu: the bridge between GT4's option scripts and the host settings (docs/BUILD-MACOS.md).
//
// Two MSystem natives are empty functions in the retail executable (jr ra), so a script may call them on any runtime:
//   main::menu::MSystem::SetDrawPerfMeter(id, value)   callback 0x001AC238
//   main::menu::MSystem::IsDrawPerfMeter(id)           callback 0x001AC240
// The menu runtime capsule (scripts/prepare_menu_runtime.py) sends those two callbacks here from ps2::dispatch: the
// first sets the host setting `id` to `value`, the second returns its current value as an Adhoc int. Without the
// capsule both stay empty and the second returns nil, which the script reads as "no host settings".
//
// The callback contract of a native function, as the VM calls it (invokers 0x0032CF80 and 0x0032CFA8, below): a0 is the
// result holder (the address of an object pointer), a1 the argument count and a2 the array of argument object pointers
// (attribute callbacks such as MOption.race_display_mode at 0x001805D0 get the object first, so their count and
// arguments are in a2 and a3). An Adhoc int object has its vtable at +4 (0x00674188) and its value at +16. A result int is made the way
// the retail natives make one (0x001AC290): func_002FE278 boxes it into a holder on the stack, the result holder takes
// a reference to it (0x003285A8) and drops its old object (0x003285F8), then the stack holder is destroyed (0x002FC870).

#include "ps2/cpu.hpp"

#include <cstdint>
#include <functional>
#include <optional>

namespace gt4::menu_bridge {

inline constexpr std::uint32_t kSetSettingCallback = 0x001AC238u; // MSystem.SetDrawPerfMeter, empty in retail
inline constexpr std::uint32_t kGetSettingCallback = 0x001AC240u; // MSystem.IsDrawPerfMeter, empty in retail
inline constexpr std::uint32_t kAdhocIntVtable = 0x00674188u;
inline constexpr std::uint32_t kAdhocIntValueOffset = 16u;
inline constexpr std::uint32_t kBoxInt = 0x002FE278u;        // (holder, value): holder = new int object
inline constexpr std::uint32_t kAddReference = 0x003285A8u;  // (object)
inline constexpr std::uint32_t kDropReference = 0x003285F8u; // (object): frees it at zero
inline constexpr std::uint32_t kDestroyHolder = 0x002FC870u; // (holder, 2)
// The VM's calls of natives (hBuiltin virtuals): a0 is the builtin object, whose callback is at +12. 0x0032DA40 (methods)
// and 0x0032CFA8 pass the callback a temporary result holder; 0x0032CF80 passes it its own a1 as the result holder.
inline constexpr std::uint32_t kMethodInvoker = 0x0032DA40u;
inline constexpr std::uint32_t kFunctionInvoker = 0x0032CF80u;
inline constexpr std::uint32_t kFunctionInvokerWithHolder = 0x0032CFA8u;
inline constexpr std::uint32_t kBuiltinCallbackOffset = 12u;

constexpr bool is_native_invoker(std::uint32_t pc) {
  return pc == kMethodInvoker || pc == kFunctionInvoker || pc == kFunctionInvokerWithHolder;
}

// Setting ids, the numbers the option scripts pass.
enum SettingId : int {
  kDisplayMode = 1,   // 0 window, 1 full screen
  kDeinterlacing = 2, // 0 off, 1 blend the two fields of the 480i menus
  // Resolution of the PCSX2 GS renderer (GT4_RENDERER=pcsx2 only): 0 the PS2 picture, n the n-th resolution offered for
  // the screen (gs_resolution.hpp), whose size the menu reads from the two read-only ids below.
  kInternalResolution = 3,
  kResolutionWidthBase = 10,  // + n: width of the n-th resolution, 0 when fewer are offered (n = 1..5)
  kResolutionHeightBase = 20, // + n: its height
  kHDR = 4,                   // PCSX2 GS renderer: 0 SDR, 1 HDR output on EDR displays
  kMetalFX = 5,               // PCSX2 GS renderer: 0 off, 1 MetalFX upscaling to the screen
  // PCSX2 GS renderer, the choices of gs_menu_settings.hpp:
  kAnisotropicFiltering = 30, // 0 off, 1 2x, 2 4x, 3 8x, 4 16x
  kAntiAliasing = 31,         // 0 off, 1 FXAA, 2 SMAA (macOS gt4-gs)
  kSharpening = 32,           // 0 off, 1 low, 2 medium, 3 high (FidelityFX CAS)
  kColorBoost = 33,           // 0 off, 1 low, 2 medium, 3 high (shade boost)
  kBloom = 34,                // 0 off, 1 low, 2 medium, 3 high (macOS gt4-gs)
  kFilmLook = 35,             // 0 off, 1 on (macOS gt4-gs)
};

struct Setting {
  std::function<int()> get;
  std::function<void(int)> set;
  int minimum = 0;
  int maximum = 1;
};

// The window and the renderer register their live settings at start; a later registration of an id replaces it.
void register_setting(int id, Setting setting);
std::optional<int> setting_value(int id);
// Sets a registered setting; false (and nothing changes) for an unknown id or a value out of its range.
bool change_setting(int id, int value);

constexpr bool is_bridge_callback(std::uint32_t pc) {
  return pc == kSetSettingCallback || pc == kGetSettingCallback;
}

// What a callback needs from the guest: memory words and calls into guest functions (ps2::call in the game).
struct Guest {
  std::function<std::uint32_t(std::uint32_t)> load32;
  std::function<void(std::uint32_t, std::uint32_t)> store32;
  std::function<void(ps2::Cpu &, std::uint32_t target, std::uint32_t depth)> call;
};

// The value of the Adhoc int argument `index`, or nothing when it is missing or not an int.
std::optional<std::int32_t> int_argument(const Guest &guest, std::uint32_t count, std::uint32_t arguments,
                                         std::uint32_t index);

// Runs the bridge callback at c.pc with the native contract above, then returns to the caller (c.pc = ra).
void run_callback(ps2::Cpu &c, std::uint32_t depth, const Guest &guest);

// The same with the game's memory and ps2::call (menu_bridge_runtime.cpp, linked with the runtime).
void run_callback(ps2::Cpu &c, std::uint32_t depth);

// GT4_MENU_BRIDGE_TRACE=1: one stderr line per native the VM calls (invoker, callback and the invoker's arguments), for
// script debugging. tracing() reads the variable once.
bool tracing();
void trace_native_call(const ps2::Cpu &c);

} // namespace gt4::menu_bridge
