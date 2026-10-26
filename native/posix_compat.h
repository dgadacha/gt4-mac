// MSVC runtime names used by the Windows sources, mapped to POSIX on macOS so that those files stay the same on both
// platforms: _putenv_s in the port main.cpp derived from the donor (scripts/prepare_external_vulkan.py, pinned bytes)
// and tmpfile_s (C11 Annex K) in two fixtures. Force-included by native/CMakeLists.txt on macOS.
#pragma once

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

#define _putenv_s(name, value) setenv((name), (value), 1)

static inline int tmpfile_s(FILE **stream) {
  *stream = tmpfile();
  return *stream ? 0 : errno;
}
