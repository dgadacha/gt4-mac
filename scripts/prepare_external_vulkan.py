"""Derive a private direct-Vulkan GPU adapter from the frozen MIT donor."""

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPU_SHA256 = 'bfd1b54921d3f4d6c8496433739ea97be6d675d3d7941e5ccb2f35e99e833465'
SOURCE_PINS = {
    'runtime/src/gs/gpu/gpu.cpp': GPU_SHA256,
    'runtime/src/gs/gpu/gpu.hpp': 'e99ea5d37565f55a3737dfcd76f79c700e789986803b7384eb0c5c666106f944',
    'runtime/src/gs/gs.cpp': '0a9fbfc53b4dffeaa43ae05c6e7f7f5d1fe8b5aa987d1a4ba94405177a708264',
    'host/main.cpp': '561d977743b0da7af528b86da4d5c5eb744e1b8ac9072487485f7ed3b790f007',
    'runtime/src/gs/gpu/gs.wgsl': 'a6ed68e9ca53ea9b6c90307d3ffeb2b74b15c5f0a20dd776f51bc243ef80d4a5',
}

# TASK-035 (slice191) GS stream seam: (anchor, replacement) pairs for the derived gs.cpp, selected at run time by
# GT4_RENDERER=pcsx2 (native/gs_stream/gs_stream_client.hpp). Each anchor must occur exactly once, and removing the
# replacements must restore the input. With GT4_RENDERER unset or "donor" and no GT4_GS_CAPTURE every hook returns
# at once, so the donor renderer output is unchanged. Design salvaged from the task/012 MIT seam
# (native/parallel_gs_frontend.inc on task/012-parallel-gs); no renderer code is involved.
GS_STREAM = '::gt4::gs_stream::'
GS_STREAM_HOOKS = [
    ('#include "gif.hpp"\n', '#include "gif.hpp"\n#include "gs_stream_client.hpp"\n'),
    ('void init() {\n    static bool built = false;\n',
     'void init() {\n    ' + GS_STREAM + 'set_halt_handler(+[](const char *reason) { ps2::halt(reason); });\n'
     '    static bool built = false;\n'),
    ('#ifdef PS2_GPU\n    const char *backend = std::getenv("PS2_GS");',
     '#ifdef PS2_GPU\n    if (' + GS_STREAM + 'stream_renderer()) return; // no donor Vulkan device: the GS process renders\n'
     '    const char *backend = std::getenv("PS2_GS");'),
    ('void render_reset() {\n#ifdef PS2_GPU\n', 'void render_reset() {\n    ' + GS_STREAM + 'on_gs_reset();\n#ifdef PS2_GPU\n'),
    ('void write_privileged(std::uint32_t address, std::uint64_t value) {\n    switch',
     'void write_privileged(std::uint32_t address, std::uint64_t value) {\n    ' + GS_STREAM +
     'on_privileged_write(address, value); // the donor keeps CSR/IMR/SIGLBLID for EE reads\n    switch'),
    ('void read_image(std::uint8_t *data, std::uint32_t qwords) {\n    if (!queue::active()) {',
     'void read_image(std::uint8_t *data, std::uint32_t qwords) {\n    if (' + GS_STREAM + 'read_fifo(data, qwords)) return;\n'
     '    if (!queue::active()) {'),
    ('        g_odd_field = !g_odd_field;\n        raise(8);\n',
     '        g_odd_field = !g_odd_field;\n        raise(8);\n        ' + GS_STREAM + 'on_vsync(g_odd_field);\n'),
    ('bool attach_window(int kind, void *display, std::uint64_t window, void *surface, const char *selector, '
     'std::uint32_t width, std::uint32_t height) {\n',
     'bool attach_window(int kind, void *display, std::uint64_t window, void *surface, const char *selector, '
     'std::uint32_t width, std::uint32_t height) {\n'
     '    if (' + GS_STREAM + 'stream_renderer()) return kind == 3 && ' + GS_STREAM +
     'attach_window(window, width, height); // 3 = Win32\n'),
    ('void resize_window(std::uint32_t width, std::uint32_t height) {\n',
     'void resize_window(std::uint32_t width, std::uint32_t height) {\n    if (' + GS_STREAM + 'stream_renderer()) {\n'
     '        ' + GS_STREAM + 'resize_window(width, height);\n        return;\n    }\n'),
    ('double gpu_busy_ms() {\n', 'double gpu_busy_ms() {\n    if (' + GS_STREAM + 'stream_renderer()) return 0.0;\n'),
    ('bool present(const DisplayRegs &r) {\n',
     'bool present(const DisplayRegs &r) {\n    if (' + GS_STREAM + 'stream_renderer()) return true; // the GS process presents\n'),
    ('bool display(const DisplayRegs &r, std::vector<std::uint32_t> &rgba, std::uint32_t &width, std::uint32_t &height) {\n',
     'bool display(const DisplayRegs &r, std::vector<std::uint32_t> &rgba, std::uint32_t &width, std::uint32_t &height) {\n'
     '    if (' + GS_STREAM + 'stream_renderer()) return false; // no local VRAM: frames come from the GS process\n'),
    ('bool copy_frame(const DisplayRegs &r, std::vector<std::uint32_t> &rgba, std::uint32_t &width, std::uint32_t &height) {\n',
     'bool copy_frame(const DisplayRegs &r, std::vector<std::uint32_t> &rgba, std::uint32_t &width, std::uint32_t &height) {\n'
     '    if (' + GS_STREAM + 'stream_renderer()) return false;\n'),
    ('void flush_and_wait() {\n', 'void flush_and_wait() {\n    if (' + GS_STREAM + 'stream_renderer()) return;\n'),
    ('void stats() {\n    if (const char *spec = std::getenv("PS2_DUMP_VRAM")) dump_region(spec);\n',
     'void stats() {\n    ' + GS_STREAM + 'finish(stderr);\n    if (' + GS_STREAM + 'stream_renderer()) return;\n'
     '    if (const char *spec = std::getenv("PS2_DUMP_VRAM")) dump_region(spec);\n'),
    ('void state(ps2::state::Stream &s) {\n    s.tag("gs");',
     'void state(ps2::state::Stream &s) {\n    if (' + GS_STREAM + 'stream_renderer())\n'
     '        throw std::runtime_error("save states are not supported with GT4_RENDERER=pcsx2");\n'
     '    s.tag("gs");'),
]


def apply_gs_stream_hooks(source):
    """Splices the TASK-035 GS stream seam into the derived gs.cpp; checks that removing it restores the input."""
    result = source
    for anchor, replacement in GS_STREAM_HOOKS:
        if result.count(anchor) != 1:
            raise ValueError(f'GS stream anchor changed in donor gs.cpp: {anchor[:60]!r}')
        result = result.replace(anchor, replacement)
    inverse = result
    for anchor, replacement in reversed(GS_STREAM_HOOKS):
        if inverse.count(replacement) != 1:
            raise ValueError('Unexpected GS stream hook reversal')
        inverse = inverse.replace(replacement, anchor)
    if inverse != source:
        raise ValueError('GS stream hooks do not reverse to the input')
    return result


def replace_section(source, start, end, replacement):
    first = source.index(start)
    last = source.index(end, first)
    return source[:first] + replacement + '\n\n' + source[last:]


def prepare(output, assets_root=None, gs_stream=False):
    output = output.resolve()
    assets_root = Path(assets_root or ROOT).resolve()
    # A worktree has no private/ of its own: the derived port may live in the assets checkout's private/.
    allowed_roots = [ROOT / 'private', assets_root / 'private']
    if not any(output.is_relative_to(root) and output != root for root in allowed_roots):
        raise ValueError('Derived donor code must stay inside private/')
    donor = assets_root / 'private/references/ps2-web-recomp/runtime/src/gs/gpu'
    donor_root = donor.parents[3]
    if output.is_relative_to(donor_root) or donor_root.is_relative_to(output):
        raise ValueError('Derived output cannot replace the frozen donor checkout')
    for relative, expected in SOURCE_PINS.items():
        if hashlib.sha256((donor_root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Donor source differs from qualified version: {relative}')
    gpu_bytes = (donor / 'gpu.cpp').read_bytes()
    if hashlib.sha256(gpu_bytes).hexdigest() != GPU_SHA256:
        raise ValueError('Donor GPU source differs from the qualified version')
    source = gpu_bytes.decode('utf-8').replace('\r\n', '\n')
    source = replace_section(source, '#include <webgpu/', '#include <algorithm>',
                             '#include "native_vulkan.hpp"\n#include <stdexcept>')
    source = source.replace('extern const char kGsShader[];\nextern const char kBlitShader[];\n', '')
    globals_text = '''gt4::vulkan::Context g_vulkan;
gt4::vulkan::Buffer *g_vram = nullptr, *g_tables = nullptr;
gt4::vulkan::Buffer *g_clut = nullptr, *g_scratch = nullptr, *g_decoded = nullptr;
std::uint32_t g_scale = 1, g_copy_words = 2048u * 2048u, g_field_words = 1u << 19;
bool g_rendered[512] = {};
bool g_decode = true;
std::uint32_t g_decoded_used = 0;'''
    source = replace_section(source, 'WGPUInstance g_instance', 'struct Command {', globals_text)
    source = replace_section(source, 'struct CommandInfo {', 'std::vector<Command> g_commands;', '')
    source = source.replace('WGPUStringView view(const char *s) { return WGPUStringView{s, WGPU_STRLEN}; }\n', '')
    source = source.replace('WGPUBuffer g_cache = nullptr;', 'gt4::vulkan::Buffer* g_cache = nullptr;')
    source = source.replace('wgpuQueueWriteBuffer(g_queue, g_cache,', 'g_vulkan.write(g_cache,')
    # Asynchronous submission: an entry may be overwritten only after the submission that last used it completed.
    guard_old = 'if (front.used == g_serial) return false;'
    guard_new = 'if (front.used > g_vulkan.completed_submission()) return false;'
    if source.count(guard_old) != 1:
        raise ValueError('Cache eviction guard anchor changed in the donor source')
    source = source.replace(guard_old, guard_new)
    source = replace_section(source, 'void note_raster(', 'void flush_batch()', '')
    source = source.replace('    note_raster(prims, tiles, total, snapshot);\n', '')
    source = source.replace('const std::uint32_t snapshot = snapshot_batch(prims, snapshot_lo, snapshot_hi);',
                            'snapshot_batch(prims, snapshot_lo, snapshot_hi);')
    replacements = ROOT / 'native'
    source = replace_section(source, 'void on_error(', 'std::uint32_t make_setup(',
                             (replacements / 'gpu_helpers.inc').read_text())
    source = replace_section(source, 'bool init(Mode m)', 'void draw(',
                             (replacements / 'gpu_init.inc').read_text())
    source = source[:source.index('void flush() {')] + (replacements / 'gpu_tail.inc').read_text() + '\n}\n'
    if 'wgpu' in source.lower() or 'WGPU' in source:
        raise ValueError('Unexpected WebGPU reference remains after the native port')
    source = '// MIT donor batching, derived from pinned ps2-web-recomp gpu.cpp; see THIRD_PARTY.md.\n' + source
    header = (donor / 'gpu.hpp').read_text().replace('../gs.hpp', 'gs.hpp')
    header = header.replace('enum Kind { X11, Wayland, Canvas }', 'enum Kind { X11, Wayland, Canvas, Win32 }')
    header = header.replace('bool has_surface();', 'bool has_surface();\nvoid set_widescreen(bool enabled);')
    output.mkdir(parents=True, exist_ok=True)
    # The pinned port files were written in Windows text mode: CRLF line endings, written explicitly so that every
    # platform derives the same bytes.
    (output / 'gpu.cpp').write_text(source, encoding='utf-8', newline='\r\n')
    (output / 'gpu.hpp').write_text(header, encoding='utf-8', newline='\r\n')
    graphics = donor.parent / 'gs.cpp'
    graphics_source = graphics.read_text(encoding='utf-8')
    graphics_source = graphics_source.replace('"../hw.hpp"', '"hw.hpp"')
    graphics_source = graphics_source.replace('"gpu/gpu.hpp"', '"gpu.hpp"')
    if gs_stream:
        graphics_source = apply_gs_stream_hooks(graphics_source)
    (output / 'gs.cpp').write_text(graphics_source, encoding='utf-8', newline='\r\n')
    host = donor.parents[3] / 'host/main.cpp'
    host_source = host.read_text(encoding='utf-8')
    # Preserve the donor's CLI while refusing a silent CPU raster fallback.
    host_source = host_source.replace('    register_generated_code();',
        '    _putenv_s("PS2_GS", "gpu");\n    register_generated_code();')
    (output / 'main.cpp').write_text(host_source, encoding='utf-8', newline='\r\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--assets-root', type=Path)
    parser.add_argument('--gs-stream-hooks', action='store_true',
                        help='Splice the TASK-035 GS stream seam into gs.cpp (GT4_RENDERER=pcsx2; slice191)')
    options = parser.parse_args()
    prepare(options.output, options.assets_root, options.gs_stream_hooks)
