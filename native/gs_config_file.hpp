// SPDX-License-Identifier: MIT
// The GS process's settings file (GT4_GS_CONFIG, docs/GS-SETTINGS.md) as INI text: one key read or changed in place,
// every other line kept as it is. The in-game Graphics menu (macOS, GT4_RENDERER=pcsx2) writes the internal resolution
// here; the GS process applies it after CONTROL reload_config (gs_stream_client.hpp, reload_gs_settings).
#pragma once

#include <optional>
#include <string>

namespace gt4::gs_config {

// The value of `key` in `[section]`, spaces around it removed; nullopt when the key is absent.
std::optional<std::string> value(const std::string &text, const std::string &section, const std::string &key);
// `text` with `key = value` in `[section]`: the key's line replaced, else a line added after the section's last
// setting, else the section added at the end.
std::string with_value(const std::string &text, const std::string &section, const std::string &key,
                       const std::string &value);

// The whole file; false when it cannot be read.
bool read_file(const std::string &path, std::string &text);
// Writes a temporary file next to `path` and renames it over `path`, so a reader never sees half a file.
bool write_file(const std::string &path, const std::string &text);

}  // namespace gt4::gs_config
