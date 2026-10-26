// CTest native_menu_bridge: the option scripts' host bridge (menu_bridge.cpp) on a simulated guest.

#include "menu_bridge.hpp"

#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <map>

namespace {

namespace bridge = gt4::menu_bridge;

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[menu-bridge] FAIL: %s\n", what);
    ++failures;
  }
}

// Guest memory words and the four retail functions a result int needs: an int object is {refcount, vtable, 0, 0,
// value}; a holder is one word holding an object pointer.
struct FakeGuest {
  std::map<std::uint32_t, std::uint32_t> words;
  std::uint32_t next_object = 0x00200000u;
  int calls = 0;

  std::uint32_t load(std::uint32_t address) const {
    const auto found = words.find(address);
    return found == words.end() ? 0u : found->second;
  }

  std::uint32_t make_int(std::int32_t value, std::uint32_t references) {
    const std::uint32_t object = next_object;
    next_object += 0x20u;
    words[object] = references;
    words[object + 4u] = bridge::kAdhocIntVtable;
    words[object + bridge::kAdhocIntValueOffset] = static_cast<std::uint32_t>(value);
    return object;
  }

  void call(ps2::Cpu &c, std::uint32_t target) {
    ++calls;
    const std::uint32_t a0 = c.r[4].w[0];
    if (target == bridge::kBoxInt)
      words[a0] = make_int(static_cast<std::int32_t>(c.r[5].w[0]), 1);
    else if (target == bridge::kAddReference)
      ++words[a0];
    else if (target == bridge::kDropReference)
      --words[a0];
    else if (target == bridge::kDestroyHolder)
      --words[load(a0)];
    else
      std::fprintf(stderr, "[menu-bridge] unexpected guest call 0x%08X\n", target), ++failures;
    c.pc = c.r[31].w[0];
  }

  bridge::Guest guest() {
    return {[this](std::uint32_t address) { return load(address); },
            [this](std::uint32_t address, std::uint32_t value) { words[address] = value; },
            [this](ps2::Cpu &c, std::uint32_t target, std::uint32_t) { call(c, target); }};
  }
};

void set(ps2::Cpu &c, int index, std::uint32_t value) { c.r[index].sd[0] = static_cast<std::int32_t>(value); }

// A native call: result holder, arguments (int objects), return address.
void prepare(ps2::Cpu &c, FakeGuest &fake, std::uint32_t callback, std::uint32_t result,
             std::initializer_list<std::uint32_t> objects) {
  const std::uint32_t arguments = 0x00100000u;
  std::uint32_t index = 0;
  for (std::uint32_t object : objects)
    fake.words[arguments + 4u * index++] = object;
  set(c, 4, result);
  set(c, 5, index);
  set(c, 6, arguments);
  set(c, 7, 0x01FA746Cu);
  set(c, 29, 0x01F00000u);
  set(c, 31, 0x00123450u);
  c.pc = callback;
}

} // namespace

int main() {
  int display_mode = 0;
  bridge::register_setting(bridge::kDisplayMode, {[&] { return display_mode; }, [&](int value) { display_mode = value; }, 0, 1});

  // SetDrawPerfMeter(1, 1) sets the display mode and returns to the caller.
  {
    FakeGuest fake;
    ps2::Cpu c{};
    prepare(c, fake, bridge::kSetSettingCallback, 0x00110000u, {fake.make_int(1, 1), fake.make_int(1, 1)});
    bridge::run_callback(c, 0, fake.guest());
    expect(display_mode == 1, "SetDrawPerfMeter(1, 1) sets the display mode");
    expect(c.pc == 0x00123450u && c.r[31].w[0] == 0x00123450u, "the set callback returns to ra");
    expect(fake.calls == 0, "a set calls no guest function");
  }
  // Out of range, unknown id, missing or non-int arguments change nothing.
  {
    FakeGuest fake;
    ps2::Cpu c{};
    prepare(c, fake, bridge::kSetSettingCallback, 0x00110000u, {fake.make_int(1, 1), fake.make_int(5, 1)});
    bridge::run_callback(c, 0, fake.guest());
    prepare(c, fake, bridge::kSetSettingCallback, 0x00110000u, {fake.make_int(99, 1), fake.make_int(0, 1)});
    bridge::run_callback(c, 0, fake.guest());
    prepare(c, fake, bridge::kSetSettingCallback, 0x00110000u, {fake.make_int(1, 1)});
    bridge::run_callback(c, 0, fake.guest());
    const std::uint32_t not_int = fake.make_int(0, 1);
    fake.words[not_int + 4u] = 0x00670000u;
    prepare(c, fake, bridge::kSetSettingCallback, 0x00110000u, {fake.make_int(1, 1), not_int});
    bridge::run_callback(c, 0, fake.guest());
    expect(display_mode == 1, "invalid set calls change nothing");
    expect(c.pc == 0x00123450u, "an invalid set still returns to ra");
  }
  // IsDrawPerfMeter(1) puts a new int 1 in the result holder and drops the holder's old object.
  {
    FakeGuest fake;
    ps2::Cpu c{};
    const std::uint32_t result = 0x00110000u;
    const std::uint32_t old = fake.make_int(7, 2);
    fake.words[result] = old;
    prepare(c, fake, bridge::kGetSettingCallback, result, {fake.make_int(1, 1)});
    bridge::run_callback(c, 0, fake.guest());
    const std::uint32_t object = fake.load(result);
    expect(object != old && fake.load(object + 4u) == bridge::kAdhocIntVtable &&
               fake.load(object + bridge::kAdhocIntValueOffset) == 1u,
           "the result holder holds a new int 1");
    expect(fake.load(object) == 1u, "the new int is referenced once, by the result holder");
    expect(fake.load(old) == 1u, "the old result object lost one reference");
    expect(c.pc == 0x00123450u && c.r[29].w[0] == 0x01F00000u, "the get callback returns to ra with sp restored");
    expect(fake.calls == 4, "box, add reference, drop reference, destroy holder");
  }
  // An unknown id leaves the result holder alone (the script sees nil, as without the bridge).
  {
    FakeGuest fake;
    ps2::Cpu c{};
    prepare(c, fake, bridge::kGetSettingCallback, 0x00110000u, {fake.make_int(42, 1)});
    bridge::run_callback(c, 0, fake.guest());
    expect(fake.load(0x00110000u) == 0u && fake.calls == 0, "an unknown id returns nil");
    expect(c.pc == 0x00123450u, "the unknown id returns to ra");
  }
  expect(bridge::is_bridge_callback(0x001AC238u) && bridge::is_bridge_callback(0x001AC240u) &&
             !bridge::is_bridge_callback(0x001AC248u),
         "only the two retail stubs are bridge callbacks");
  if (failures) {
    std::fprintf(stderr, "[menu-bridge] %d failure(s)\n", failures);
    return 1;
  }
  std::fprintf(stderr, "[menu-bridge] PASS\n");
  return 0;
}
