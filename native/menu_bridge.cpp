#include "menu_bridge.hpp"

#include <cstdio>
#include <map>
#include <set>
#include <utility>

namespace gt4::menu_bridge {
namespace {

constexpr std::uint32_t kGuestRamBytes = 32u << 20;  // EE main RAM, as ps2::kRamSize
constexpr std::uint32_t kMaximumArguments = 16u;
constexpr std::uint32_t kResultFrameBytes = 32u;     // the stack holder of a result int, 16-byte aligned frame

std::map<int, Setting> &settings() {
  static std::map<int, Setting> table;
  return table;
}

bool guest_span(std::uint32_t address, std::uint32_t size) {
  return address != 0 && address < kGuestRamBytes && size <= kGuestRamBytes - address;
}

void set_register(ps2::Cpu &c, int index, std::uint32_t value) {
  c.r[index].sd[0] = static_cast<std::int32_t>(value);
}

// Calls a guest function as a jal from the callback would; false when it did not come back (halt or unwind), with
// c.pc left as the callee set it.
bool call_guest(ps2::Cpu &c, std::uint32_t depth, const Guest &guest, std::uint32_t target, std::uint32_t sentinel) {
  set_register(c, 31, sentinel);
  guest.call(c, target, depth + 1u);
  return c.pc == sentinel;
}

// Stores a new Adhoc int into the result holder, the way the retail natives do (menu_bridge.hpp).
bool return_int(ps2::Cpu &c, std::uint32_t depth, const Guest &guest, std::uint32_t result, std::int32_t value) {
  // The delay slot of the callback's jr ra: never a return address of the guest code.
  const std::uint32_t sentinel = c.pc + 4u;
  const std::uint32_t stack = c.r[29].w[0];
  const std::uint32_t holder = stack - kResultFrameBytes;
  set_register(c, 29, holder);
  guest.store32(holder, 0);
  set_register(c, 4, holder);
  set_register(c, 5, static_cast<std::uint32_t>(value));
  if (!call_guest(c, depth, guest, kBoxInt, sentinel))
    return false;
  const std::uint32_t object = guest.load32(holder);
  if (object) {
    set_register(c, 4, object);
    if (!call_guest(c, depth, guest, kAddReference, sentinel))
      return false;
  }
  if (const std::uint32_t old = guest.load32(result)) {
    set_register(c, 4, old);
    if (!call_guest(c, depth, guest, kDropReference, sentinel))
      return false;
  }
  guest.store32(result, object);
  set_register(c, 4, holder);
  set_register(c, 5, 2u);
  if (!call_guest(c, depth, guest, kDestroyHolder, sentinel))
    return false;
  set_register(c, 29, stack);
  return true;
}

} // namespace

void register_setting(int id, Setting setting) { settings()[id] = std::move(setting); }

std::optional<int> setting_value(int id) {
  const auto found = settings().find(id);
  if (found == settings().end() || !found->second.get)
    return std::nullopt;
  return found->second.get();
}

bool change_setting(int id, int value) {
  const auto found = settings().find(id);
  if (found == settings().end() || !found->second.set || value < found->second.minimum ||
      value > found->second.maximum)
    return false;
  found->second.set(value);
  return true;
}

std::optional<std::int32_t> int_argument(const Guest &guest, std::uint32_t count, std::uint32_t arguments,
                                         std::uint32_t index) {
  if (index >= count || count > kMaximumArguments || !guest_span(arguments, count * 4u))
    return std::nullopt;
  const std::uint32_t object = guest.load32(arguments + index * 4u);
  if (!guest_span(object, kAdhocIntValueOffset + 4u) || guest.load32(object + 4u) != kAdhocIntVtable)
    return std::nullopt;
  return static_cast<std::int32_t>(guest.load32(object + kAdhocIntValueOffset));
}

void run_callback(ps2::Cpu &c, std::uint32_t depth, const Guest &guest) {
  const std::uint32_t return_address = c.r[31].w[0];
  const std::uint32_t result = c.r[4].w[0];
  const std::uint32_t count = c.r[5].w[0];
  const std::uint32_t arguments = c.r[6].w[0];
  const std::optional<std::int32_t> id = int_argument(guest, count, arguments, 0);
  if (c.pc == kSetSettingCallback) {
    const std::optional<std::int32_t> value = int_argument(guest, count, arguments, 1);
    if (!id || !value)
      std::fprintf(stderr, "[menu-bridge] SetDrawPerfMeter: %u argument(s), expected two ints -> ignored\n", count);
    else
      std::fprintf(stderr, "[menu-bridge] setting %d = %d%s\n", *id, *value,
                   change_setting(*id, *value) ? "" : " refused (unknown id or out of range)");
  } else if (c.pc == kGetSettingCallback) {
    const std::optional<int> value = id ? setting_value(*id) : std::nullopt;
    static std::set<int> reported;
    // One line per id (and one for calls without an int id), the first time the menu reads it.
    if (!id) {
      if (reported.insert(-1).second)
        std::fprintf(stderr, "[menu-bridge] IsDrawPerfMeter: %u argument(s), expected one int -> nil\n", count);
    } else if (reported.insert(*id).second) {
      if (value)
        std::fprintf(stderr, "[menu-bridge] setting %d read by the menu: %d\n", *id, *value);
      else
        std::fprintf(stderr, "[menu-bridge] setting %d read by the menu: unknown -> nil\n", *id);
    }
    if (value && guest_span(result, 4u) && !return_int(c, depth, guest, result, *value))
      return; // a guest call halted or unwound: leave c.pc as it set it
  }
  set_register(c, 31, return_address);
  c.pc = return_address;
}

} // namespace gt4::menu_bridge
