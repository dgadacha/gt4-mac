// CTest native_gs_config_file: reading and changing one key of the GS process's settings file (gs_config_file.cpp).

#include "gs_config_file.hpp"

#include <cstdio>
#include <filesystem>
#include <string>

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "[gs-config-file] FAIL: %s\n", what);
    ++failures;
  }
}

}  // namespace

int main() {
  namespace config = gt4::gs_config;
  const std::string text = "; written by the launcher\n[EmuCore/GS]\nupscale_multiplier = 3\nfxaa=false\n\n"
                           "[GT4GS]\nDataRoot = /data\n";

  expect(config::value(text, "EmuCore/GS", "upscale_multiplier") == "3", "value with spaces around '='");
  expect(config::value(text, "EmuCore/GS", "fxaa") == "false", "value without spaces");
  expect(config::value(text, "GT4GS", "DataRoot") == "/data", "value of the second section");
  expect(!config::value(text, "GT4GS", "upscale_multiplier"), "a key of another section is not found");
  expect(!config::value(text, "Folders", "Cache"), "a missing section");

  const std::string replaced = config::with_value(text, "EmuCore/GS", "upscale_multiplier", "6");
  expect(replaced == "; written by the launcher\n[EmuCore/GS]\nupscale_multiplier = 6\nfxaa=false\n\n"
                     "[GT4GS]\nDataRoot = /data\n",
         "the key's line is replaced and every other line kept");

  const std::string added = config::with_value(text, "EmuCore/GS", "CASMode", "1");
  expect(added == "; written by the launcher\n[EmuCore/GS]\nupscale_multiplier = 3\nfxaa=false\nCASMode = 1\n\n"
                  "[GT4GS]\nDataRoot = /data\n",
         "a new key goes after the section's last setting");

  const std::string last = config::with_value(text, "GT4GS", "DumpEvery", "60");
  expect(last == text + "DumpEvery = 60\n", "a new key in the last section");

  const std::string section = config::with_value("[GT4GS]\nDataRoot = /data\n", "EmuCore/GS", "upscale_multiplier", "4");
  expect(section == "[GT4GS]\nDataRoot = /data\n\n[EmuCore/GS]\nupscale_multiplier = 4\n", "a missing section is added");
  expect(config::with_value("", "EmuCore/GS", "upscale_multiplier", "2") == "[EmuCore/GS]\nupscale_multiplier = 2\n",
         "an empty file");

  const std::string windows = "[EmuCore/GS]\r\nupscale_multiplier = 3\r\n";
  expect(config::value(windows, "EmuCore/GS", "upscale_multiplier") == "3", "CRLF line endings are read");

  const std::filesystem::path path = std::filesystem::temp_directory_path() / "gt4-gs-config-fixture.ini";
  std::string read;
  expect(config::write_file(path.string(), replaced), "write_file");
  expect(config::read_file(path.string(), read) && read == replaced, "read_file returns what was written");
  expect(!std::filesystem::exists(path.string() + ".tmp"), "no temporary file is left");
  std::filesystem::remove(path);

  if (failures == 0) std::printf("[gs-config-file] all checks passed\n");
  return failures == 0 ? 0 : 1;
}
