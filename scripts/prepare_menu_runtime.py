"""Derive the runtime hooks of the in-game Graphics menu (macOS): a capsule with disc.cpp and dispatch.cpp.

disc.cpp is the pinned MIT donor disc reader (runtime/src/disc.cpp) whose open(path) passes its reader through
native/disc_overlay.cpp: with GT4_DISC_OVERLAY set, the extents of an overlay built by scripts/gt4_volume_overlay.py (a
rewritten GT4.VOL catalogue and replacement files past the end of the image) are served instead of the image; without
it the reader is unchanged.

dispatch.cpp is the slice262 license guard capsule's dispatch.cpp (scripts/prepare_license_guard.py, pinned in
docs/inputs/slice262-license-guard-runtime.json) in which the two empty retail natives that the option scripts use as
the host bridge, MSystem.SetDrawPerfMeter (0x001AC238) and MSystem.IsDrawPerfMeter (0x001AC240), run
native/menu_bridge.cpp instead of their empty bodies.

Overlay sections are anchored on unique text, and removing them must restore the normalized input, as
scripts/prepare_memcard_flush.py checks for its overlay.
"""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DONOR_DISC = 'runtime/src/disc.cpp'
DONOR_DISC_SHA256 = 'fc2944cfd3ebd5650cca87ddd588c73d8491319d1192bf07df24bb6d32bba129'
GUARD_CAPSULE = 'private/slice262-license-guard-runtime'
GUARD_PIN = 'docs/inputs/slice262-license-guard-runtime.json'

INCLUDE_ANCHOR = '#include "ps2/disc.hpp"\n'
INCLUDE_SECTION = '\n#include "disc_overlay.hpp"\n'
OPEN_ANCHOR = '    return open(path, size, [file](std::uint64_t offset, void *out, std::size_t bytes) {\n'
OPEN_SECTION = ('    // GT4_DISC_OVERLAY: the overlay extents replace or extend the image (native/disc_overlay.cpp).\n'
                '    return open(path, gt4::disc_overlay::virtual_size(size),\n'
                '                gt4::disc_overlay::wrap(size, [file](std::uint64_t offset, void *out, std::size_t bytes) {\n')
CLOSE_ANCHOR = '        return std::fread(out, 1, bytes, file);\n    });\n}\n'
CLOSE_SECTION = '        return std::fread(out, 1, bytes, file);\n    }));\n}\n'

BRIDGE_INCLUDE_ANCHOR = '#include "display_aspect.hpp"\n'
BRIDGE_INCLUDE_SECTION = '#include "menu_bridge.hpp"\n'
BRIDGE_CALL_ANCHOR = '    if (pc == kHandlerReturn || pc == kIdle) return;\n'
BRIDGE_CALL_SECTION = (
    '    // In-game Graphics menu (scripts/prepare_menu_runtime.py): the two empty retail natives that the option scripts\n'
    '    // use as the host bridge run native/menu_bridge.cpp; GT4_MENU_BRIDGE_TRACE=1 logs every native the VM calls.\n'
    '    if (gt4::menu_bridge::is_bridge_callback(pc)) [[unlikely]] {\n'
    '        gt4::menu_bridge::run_callback(c, depth);\n'
    '        return;\n'
    '    }\n'
    '    if (gt4::menu_bridge::is_native_invoker(pc) && gt4::menu_bridge::tracing()) [[unlikely]]\n'
    '        gt4::menu_bridge::trace_native_call(c);\n')


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def replace_once(source, anchor, replacement, label):
    if source.count(anchor) != 1:
        raise ValueError(f'{label} anchor must appear exactly once')
    return source.replace(anchor, replacement, 1)


def apply_disc_overlay(source):
    """Returns the derived disc.cpp text (LF line endings)."""
    source = replace_once(source, INCLUDE_ANCHOR, INCLUDE_ANCHOR + INCLUDE_SECTION, 'include')
    source = replace_once(source, OPEN_ANCHOR, OPEN_SECTION, 'open')
    return replace_once(source, CLOSE_ANCHOR, CLOSE_SECTION, 'open closing')


def remove_disc_overlay(source):
    """Reverses apply_disc_overlay so the input can be checked byte for byte."""
    source = replace_once(source, INCLUDE_ANCHOR + INCLUDE_SECTION, INCLUDE_ANCHOR, 'derived include')
    source = replace_once(source, OPEN_SECTION, OPEN_ANCHOR, 'derived open')
    return replace_once(source, CLOSE_SECTION, CLOSE_ANCHOR, 'derived open closing')


def apply_bridge(source):
    """Returns the derived dispatch.cpp text (LF line endings)."""
    source = replace_once(source, BRIDGE_INCLUDE_ANCHOR, BRIDGE_INCLUDE_ANCHOR + BRIDGE_INCLUDE_SECTION, 'bridge include')
    return replace_once(source, BRIDGE_CALL_ANCHOR, BRIDGE_CALL_ANCHOR + BRIDGE_CALL_SECTION, 'bridge call')


def remove_bridge(source):
    """Reverses apply_bridge so the input can be checked byte for byte."""
    source = replace_once(source, BRIDGE_INCLUDE_ANCHOR + BRIDGE_INCLUDE_SECTION, BRIDGE_INCLUDE_ANCHOR,
                          'derived bridge include')
    return replace_once(source, BRIDGE_CALL_ANCHOR + BRIDGE_CALL_SECTION, BRIDGE_CALL_ANCHOR, 'derived bridge call')


def read_donor(assets_root):
    raw = (assets_root / 'private/references/ps2-web-recomp' / DONOR_DISC).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DONOR_DISC_SHA256:
        raise ValueError(f'Donor source differs from the pinned version: {DONOR_DISC}')
    return raw.decode('utf-8').replace('\r\n', '\n')


def read_guard_dispatch(assets_root):
    """The slice262 license guard dispatch.cpp, checked against its reviewed pin."""
    pinned = json.loads((ROOT / GUARD_PIN).read_text(encoding='utf-8'))['source_sha256']['dispatch.cpp']
    raw = (assets_root / GUARD_CAPSULE / 'dispatch.cpp').read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != pinned:
        raise ValueError(f'{GUARD_CAPSULE}/dispatch.cpp differs from {GUARD_PIN}: run the runtime stage first')
    return raw.decode('utf-8').replace('\r\n', '\n'), actual


def prepare(output, assets_root=None):
    assets_root = Path(assets_root or ROOT).resolve()
    output = output.resolve()
    private = assets_root / 'private'
    if not output.is_relative_to(private) or output == private:
        raise ValueError('Derived donor code must stay inside the assets checkout private/')
    disc_source = read_donor(assets_root)
    disc = apply_disc_overlay(disc_source)
    if remove_disc_overlay(disc) != disc_source:
        raise ValueError('Disc overlay hook does not reverse to the donor input')
    guard_source, guard_sha256 = read_guard_dispatch(assets_root)
    dispatch = apply_bridge(guard_source)
    if remove_bridge(dispatch) != guard_source:
        raise ValueError('Menu bridge hook does not reverse to the license guard input')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'disc.cpp').write_text(disc, encoding='utf-8', newline='\n')
    (output / 'dispatch.cpp').write_text(dispatch, encoding='utf-8', newline='\n')
    manifest = {
        'schema_version': 1,
        'donor_source': DONOR_DISC,
        'donor_sha256': DONOR_DISC_SHA256,
        'guard_dispatch_source': f'{GUARD_CAPSULE}/dispatch.cpp',
        'guard_dispatch_sha256': guard_sha256,
        'disc_sha256': sha256_text(disc),
        'dispatch_sha256': sha256_text(dispatch),
        'hooks': 'GT4_DISC_OVERLAY reader (native/disc_overlay.cpp) and the option scripts host bridge '
                 '(native/menu_bridge.cpp) of the in-game Graphics menu',
    }
    (output / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output', type=Path)
    parser.add_argument('--assets-root', type=Path)
    options = parser.parse_args()
    prepare(options.output, options.assets_root)
