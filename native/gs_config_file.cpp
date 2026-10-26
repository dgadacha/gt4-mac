// SPDX-License-Identifier: MIT
// See gs_config_file.hpp.
#include "gs_config_file.hpp"

#include <cstdio>
#include <fstream>
#include <iterator>
#include <sstream>
#include <vector>

namespace gt4::gs_config {
namespace {

std::string trimmed(const std::string &text) {
  const auto first = text.find_first_not_of(" \t\r");
  if (first == std::string::npos) return {};
  const auto last = text.find_last_not_of(" \t\r");
  return text.substr(first, last - first + 1);
}

// The lines of `text` without their '\n'; a text ending with '\n' gives a last empty line.
std::vector<std::string> lines_of(const std::string &text) {
  std::vector<std::string> lines;
  std::string::size_type start = 0;
  while (true) {
    const auto end = text.find('\n', start);
    if (end == std::string::npos) {
      lines.push_back(text.substr(start));
      return lines;
    }
    lines.push_back(text.substr(start, end - start));
    start = end + 1;
  }
}

std::string joined(const std::vector<std::string> &lines) {
  std::string text;
  for (std::size_t index = 0; index < lines.size(); ++index) {
    if (index) text += '\n';
    text += lines[index];
  }
  return text;
}

bool section_header(const std::string &line, std::string &name) {
  const std::string text = trimmed(line);
  if (text.size() < 2 || text.front() != '[' || text.back() != ']') return false;
  name = trimmed(text.substr(1, text.size() - 2));
  return true;
}

bool setting(const std::string &line, std::string &key, std::string &value) {
  const std::string text = trimmed(line);
  if (text.empty() || text.front() == ';' || text.front() == '#') return false;
  const auto equals = text.find('=');
  if (equals == std::string::npos) return false;
  key = trimmed(text.substr(0, equals));
  value = trimmed(text.substr(equals + 1));
  return true;
}

}  // namespace

std::optional<std::string> value(const std::string &text, const std::string &section, const std::string &key) {
  std::string current, name, line_key, line_value;
  for (const std::string &line : lines_of(text)) {
    if (section_header(line, name))
      current = name;
    else if (current == section && setting(line, line_key, line_value) && line_key == key)
      return line_value;
  }
  return std::nullopt;
}

std::string with_value(const std::string &text, const std::string &section, const std::string &key,
                       const std::string &value) {
  std::vector<std::string> lines = lines_of(text);
  const std::string line = key + " = " + value;
  bool inside = false, found_section = false;
  std::size_t insert_at = 0;
  std::string name, line_key, line_value;
  for (std::size_t index = 0; index < lines.size(); ++index) {
    if (section_header(lines[index], name)) {
      if (inside) break;  // the next section: insert after the last setting of ours
      inside = name == section;
      if (inside) {
        found_section = true;
        insert_at = index + 1;
      }
      continue;
    }
    if (!inside) continue;
    if (setting(lines[index], line_key, line_value) && line_key == key) {
      lines[index] = line;
      return joined(lines);
    }
    if (!trimmed(lines[index]).empty()) insert_at = index + 1;
  }
  if (found_section) {
    lines.insert(lines.begin() + static_cast<std::ptrdiff_t>(insert_at), line);
    return joined(lines);
  }
  std::string result = text;
  if (!result.empty() && result.back() != '\n') result += '\n';
  if (!result.empty()) result += '\n';
  return result + "[" + section + "]\n" + line + "\n";
}

bool read_file(const std::string &path, std::string &text) {
  std::ifstream file(path, std::ios::binary);
  if (!file) return false;
  text.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
  return !file.bad();
}

bool write_file(const std::string &path, const std::string &text) {
  const std::string temporary = path + ".tmp";
  {
    std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
    if (!file) return false;
    file.write(text.data(), static_cast<std::streamsize>(text.size()));
    if (!file.flush()) return false;
  }
  return std::rename(temporary.c_str(), path.c_str()) == 0;
}

}  // namespace gt4::gs_config
