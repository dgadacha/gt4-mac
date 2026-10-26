// The menu bridge (menu_bridge.hpp) on the game's memory and calls; the menu runtime capsule's dispatch.cpp calls it.

#include "menu_bridge.hpp"

#include "ps2/generated.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace gt4::menu_bridge {

void run_callback(ps2::Cpu &c, std::uint32_t depth) {
  static const Guest guest{
      [](std::uint32_t address) { return ps2::ld32(address); },
      [](std::uint32_t address, std::uint32_t value) { ps2::st32(address, value); },
      [](ps2::Cpu &cpu, std::uint32_t target, std::uint32_t call_depth) { ps2::call(cpu, target, call_depth); },
  };
  run_callback(c, depth, guest);
}

bool tracing() {
  static const bool enabled = [] {
    const char *value = std::getenv("GT4_MENU_BRIDGE_TRACE");
    return value && std::strcmp(value, "1") == 0;
  }();
  return enabled;
}

void trace_native_call(const ps2::Cpu &c) {
  const std::uint32_t builtin = c.r[4].w[0];
  const std::uint32_t callback = builtin && builtin < ps2::kRamSize - 16u ? ps2::ld32(builtin + kBuiltinCallbackOffset) : 0u;
  std::fprintf(stderr, "[menu-bridge] native 0x%08X via 0x%08X a1 %08X a2 %08X a3 %08X t0 %08X\n", callback, c.pc,
               c.r[5].w[0], c.r[6].w[0], c.r[7].w[0], c.r[8].w[0]);
}

} // namespace gt4::menu_bridge
