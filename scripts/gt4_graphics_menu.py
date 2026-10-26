"""In-game Graphics menu: the edits of GT4's option project, applied to the user's own disc files.

The Screen page of the Options menu (projects/option) gets a "Display Mode" row (Window / Full Screen) and, for the
PCSX2 GS renderer, "Resolution" (Native, then up to five resolutions that the game fills in for the screen, such as
1920x1080: the internal resolution), "HDR" and "MetalFX Upscaling" rows (Off / On), made of the game's own widgets: copies of the page's Video Output row in option.mproject (the widget tree, text), with their texts added
to US/rtext.rt2 (RT03, scripts/gt4_rtext.py). A row stays hidden unless the option script finds its setting in the
host bridge (native/menu_bridge.hpp), so the edited files also work on a runtime without it.

The option script itself (option.adc) is compiled outside this repository: see docs/BUILD-MACOS.md, section "In-game
Graphics menu". This tool takes the compiled file and writes the disc overlay that serves the three files
(scripts/gt4_volume_overlay.py, read by the game through GT4_DISC_OVERLAY).

  build --iso <disc> --adc <compiled option.adc> --output private/<fresh folder>

Everything written is derived from game data and stays under private/.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import gt4_rtext  # noqa: E402
import gt4_volume as volume  # noqa: E402
import gt4_volume_overlay as overlay  # noqa: E402

ADC = 'projects/option/option.adc'
MPROJECT = 'projects/option/option.mproject'
RTEXT = 'projects/option/US/rtext.rt2'
SCREEN_PAGE = 'OptionProject::ScreenRoot'

# Hashes of the files this recipe was written against (NTSC-U v2.00).
ORIGINAL_SHA256 = {
    ADC: 'acd29dd0507bdb479b0a64e2d8603b3e40a2ad34ab270479772a3e40bf56448c',
    MPROJECT: '8870c95015af1ab8dc6d7183d3dd7dc86dbe1d74cf6c72c462a3a0ee161cb7eb',
    RTEXT: '169d4e963c988d2d6ade3cc0124356305e46fb2e82d99c7d83fc6c1f8fa95aa4',
}

# Our texts (US English, the game's capitalisation).
SCREEN_TEXTS = {
    'LabelDisplay': 'Display Mode',
    'Window': 'Window',
    'FullScreen': 'Full Screen',
    'TOOLTIP|Display': 'Show the game in a window or on the whole screen.',
    'LabelResolution': 'Resolution',
    'ResNative': 'Native',
    'TOOLTIP|Resolution': 'Draw the game at the PS2 resolution or higher. Higher is sharper and needs a faster GPU.',
    'LabelHDR': 'HDR',
    'LabelMetalFX': 'MetalFX Upscaling',
    'ItemOff': 'Off',
    'ItemOn': 'On',
    'TOOLTIP|HDR': 'Brighter lights and reflections on an HDR display, such as a MacBook Pro XDR screen.',
    'TOOLTIP|MetalFX': 'Enlarge the picture to the screen with Apple MetalFX when the resolution is lower than the screen.',
}
# The Resolution items after Native have no stored text: the option script writes the screen's resolutions into them
# at run time (native/gs_resolution.hpp) and removes the items the screen does not use. (A stored text would win: the
# closed list shows an item's text key, not the text the script wrote.)
RESOLUTION_SLOTS = 5

# The rows added after the Video Output row, in order: (widget name, label key, popup items as (widget name, text
# key or None for a text the script writes), background colour). Rows alternate the page's two colours and Video
# Output has the first.
ROWS = [
    ('Display', 'LabelDisplay', [('Window', 'Window'), ('FullScreen', 'FullScreen')], 'RGBA {154 154 161 183}'),
    ('Resolution', 'LabelResolution',
     [('ResNative', 'ResNative')] + [(f'Res{slot}', None) for slot in range(1, RESOLUTION_SLOTS + 1)],
     'RGBA {144 144 150 183}'),
    ('HDR', 'LabelHDR', [('HdrOff', 'ItemOff'), ('HdrOn', 'ItemOn')], 'RGBA {154 154 161 183}'),
    ('MetalFX', 'LabelMetalFX', [('MetalFXOff', 'ItemOff'), ('MetalFXOn', 'ItemOn')], 'RGBA {144 144 150 183}'),
]
# The page's pane moves up so that its rows stay above the tooltip bar (y 438) when all of them show.
SCREEN_PANE = ('geometry rectangle {160 130 320 150}', 'geometry rectangle {160 82 320 150}')
VIDEO_OUTPUT_COLOUR = 'RGBA {144 144 150 183}'
VIDEO_OUTPUT_TOP = 116
ROW_HEIGHT = 32


def _block_end(lines, start):
    """Index of the line closing the block opened at lines[start] (same indentation, '}')."""
    indent = lines[start][:len(lines[start]) - len(lines[start].lstrip('\t'))]
    for index in range(start + 1, len(lines)):
        if lines[index] == indent + '}':
            return index
    raise ValueError(f'unclosed block at line {start + 1}')


def _find_line(lines, text, start=0, end=None):
    end = len(lines) if end is None else end
    for index in range(start, end):
        if lines[index].strip() == text:
            return index
    raise ValueError(f'{text!r} not found')


def _item_block(item, template):
    """A popup item (Composite with bgf, dot and label) from the Normal item of the Video Output row."""
    name, key = item
    return [line.replace('name string {"Normal"}', f'name string {{"{name}"}}')
                .replace('key string {"Normal"}', f'key string {{"{key}"}}') for line in template
            if key is not None or line.strip() != 'key string {"Normal"}']


def option_row(hivision, position):
    """Row ROWS[position]: a copy of the Video Output row with our name, texts, place, colour and popup items."""
    name, label, popup_items, colour = ROWS[position]
    top = VIDEO_OUTPUT_TOP + ROW_HEIGHT * (position + 1)
    row = list(hivision)
    replacements = {
        'name string {"HiVision"}': f'name string {{"{name}"}}',
        'key string {"LabelHiVision"}': f'key string {{"{label}"}}',
        'tooltip_key string {"HiVision"}': f'tooltip_key string {{"{name}"}}',
        f'geometry rectangle {{0 {VIDEO_OUTPUT_TOP} 320 32}}': f'geometry rectangle {{0 {top} 320 32}}',
        VIDEO_OUTPUT_COLOUR: colour,
    }
    for old, new in replacements.items():
        hits = [index for index, line in enumerate(row) if line.strip() == old]
        if len(hits) != 1:
            raise ValueError(f'Video Output row: {old!r} found {len(hits)} times')
        row[hits[0]] = row[hits[0]].replace(old, new)
    # The popup list: keep its background, replace the three items by ours.
    vbox = _find_line(row, 'name string {"vbox"}')
    children = vbox + 2
    if row[children].strip() != 'children [4] {':
        raise ValueError('Video Output popup: unexpected item list')
    items = []
    index = children + 1
    while row[index].strip() != '}':
        end = _block_end(row, index)
        items.append((index, end))
        index = end + 1
    names = [row[start + 1].strip() for start, _ in items]
    if names != ['name string {"bg"}', 'name string {"Normal"}', 'name string {"Mode480p"}',
                 'name string {"Mode1080i"}']:
        raise ValueError(f'Video Output popup items: {names}')
    template = row[items[1][0]:items[1][1] + 1]
    new_items = row[items[0][0]:items[0][1] + 1]
    for index, item in enumerate(popup_items):
        block = _item_block(item, template)
        block = [line.replace('geometry rectangle {0 0 160 24}', f'geometry rectangle {{0 {24 * index} 160 24}}')
                 for line in block]
        new_items += block
    indent = row[children][:len(row[children]) - len(row[children].lstrip('\t'))]
    return (row[:children] + [f'{indent}children [{1 + len(popup_items)}] {{'] + new_items +
            row[items[-1][1] + 1:])


def edit_mproject(text):
    """Adds the ROWS after the Video Output row of the Screen page."""
    lines = text.split('\n')
    page = _find_line(lines, 'name string {"ScreenRoot"}')
    page_end = _block_end(lines, page - 1)
    pane = _find_line(lines, 'name string {"Pane"}', page, page_end)
    pane_children = next(index for index in range(pane, page_end) if lines[index].strip().startswith('children ['))
    if lines[pane_children].strip() != 'children [7] {':
        raise ValueError('Screen page: unexpected row count')
    lines[pane_children] = lines[pane_children].replace('children [7]', f'children [{7 + len(ROWS)}]')
    pane_geometry = _find_line(lines, SCREEN_PANE[0], pane, pane_children)
    lines[pane_geometry] = lines[pane_geometry].replace(*SCREEN_PANE)
    hivision = _find_line(lines, 'name string {"HiVision"}', pane, page_end) - 1
    hivision_end = _block_end(lines, hivision)
    rows = [line for position in range(len(ROWS)) for line in option_row(lines[hivision:hivision_end + 1], position)]
    return '\n'.join(lines[:hivision_end + 1] + rows + lines[hivision_end + 1:])


def edit_rtext(data):
    pages = gt4_rtext.read(data)
    screen = pages[SCREEN_PAGE]
    for key in SCREEN_TEXTS:
        if key in screen:
            raise ValueError(f'{SCREEN_PAGE} already has {key}')
    screen.update(SCREEN_TEXTS)
    return gt4_rtext.write(pages)


def build(iso, adc_path, output):
    originals = {path: overlay.original_file(iso, path) for path in ORIGINAL_SHA256}
    for path, digest in ORIGINAL_SHA256.items():
        if overlay.sha256(originals[path]) != digest:
            raise ValueError(f'{path} differs from the file this recipe was written for')
    replacements = {
        ADC: Path(adc_path).read_bytes(),
        MPROJECT: edit_mproject(originals[MPROJECT].decode('latin-1')).encode('latin-1'),
        RTEXT: edit_rtext(originals[RTEXT]),
    }
    disc_size, virtual_size, extents, facts = overlay.build(iso, replacements)
    overlay.write_overlay(output / 'overlay.gt4ovl', disc_size, virtual_size, extents)
    for path, data in replacements.items():
        (output / Path(path).name).write_bytes(data)
    facts.update({'disc_size': disc_size, 'virtual_size': virtual_size,
                  'overlay_sha256': overlay.sha256((output / 'overlay.gt4ovl').read_bytes())})
    (output / 'overlay.json').write_text(json.dumps(facts, indent=2) + '\n', encoding='utf-8')
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    build_command = commands.add_parser('build')
    build_command.add_argument('--iso', type=Path, required=True)
    build_command.add_argument('--adc', type=Path, required=True, help='the compiled option script')
    build_command.add_argument('--output', type=Path, required=True, help='fresh folder under private/')
    arguments = parser.parse_args(argv)
    try:
        output = volume.fresh_output_directory(arguments.output, ROOT / 'private')
        facts = build(arguments.iso, arguments.adc, output)
        print(f"overlay: {len(facts['files'])} files, catalogue {facts['catalogue_bytes']} of "
              f"{facts['catalogue_capacity']} bytes, {output / 'overlay.gt4ovl'}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f'gt4-graphics-menu: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
