"""In-game Graphics menu: the edits of GT4's option project, applied to the user's own disc files.

The Options menu gets a Graphics page for the PCSX2 GS renderer, in the slot of a page the disc ships unused, Camera
(CameraRoot: its images, projects/option/US/CameraRoot.gpb, are the Screen page's; its texts; its tile icon). Its rows:
"Resolution" (Native, then up to five resolutions that the game fills in for the screen, such as 1920x1080: the internal
resolution), "MetalFX Upscaling", "Anisotropic Filtering", "Anti-Aliasing", "Sharpening", "Color Boost" and "HDR". Its tile follows Sound in the General group, with an icon drawn from the Picture Quality icon
(scripts/gt4_option_icon.py). The Screen page gets a "Display Mode" row (Window / Full Screen).

Every row is made of the game's own widgets: a copy of the Screen page's Video Output row in option.mproject (the widget
tree), with its texts added to US/rtext.rt2 (RT03, scripts/gt4_rtext.py). A row stays hidden unless the option script
finds its setting in the host bridge (native/menu_bridge.hpp), and the tile shows only when the host has the renderer's
settings, so the edited files also work on a runtime without them.

The option script itself (option.adc) is compiled outside this repository: see docs/BUILD-MACOS.md, section "In-game
Graphics menu". This tool takes the compiled file and writes the disc overlay that serves the four files
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

import gt4_option_icon  # noqa: E402
import gt4_rtext  # noqa: E402
import gt4_volume as volume  # noqa: E402
import gt4_volume_overlay as overlay  # noqa: E402

ADC = 'projects/option/option.adc'
MPROJECT = 'projects/option/option.mproject'
RTEXT = 'projects/option/US/rtext.rt2'
ICONS = 'projects/option/US/OptionRoot.gpb'
OPTION_PAGE = 'OptionProject::OptionRoot'
SCREEN_PAGE = 'OptionProject::ScreenRoot'
GRAPHICS_ROOT = 'CameraRoot'
GRAPHICS_PAGE = f'OptionProject::{GRAPHICS_ROOT}'

# Hashes of the files this recipe was written against (NTSC-U v2.00).
ORIGINAL_SHA256 = {
    ADC: 'acd29dd0507bdb479b0a64e2d8603b3e40a2ad34ab270479772a3e40bf56448c',
    MPROJECT: '8870c95015af1ab8dc6d7183d3dd7dc86dbe1d74cf6c72c462a3a0ee161cb7eb',
    RTEXT: '169d4e963c988d2d6ade3cc0124356305e46fb2e82d99c7d83fc6c1f8fa95aa4',
    ICONS: '2317439fcb2e3bb97fd62e212e40fc8353444751349b692f063a51426159aa78',
}

# Our texts (US English, the game's capitalisation and tooltip style).
OPTION_TEXTS = {
    'Graphics': 'Graphics',
    'TOOLTIP|Graphics': 'Graphics Settings: Set the resolution, texture filtering, anti-aliasing, sharpening, colors '
                        'and HDR',
}
SCREEN_TEXTS = {
    'LabelDisplay': 'Display Mode',
    'Window': 'Window',
    'FullScreen': 'Full Screen',
    'TOOLTIP|Display': 'Show the game in a window or on the whole screen.',
}
GRAPHICS_TEXTS = {
    'TitleGraphics': 'Graphics Settings',
    'LabelResolution': 'Resolution',
    'ResNative': 'Native',
    'TOOLTIP|Resolution': 'Draw the game at the PS2 resolution or higher. Higher is sharper and needs a faster GPU.',
    'LabelMetalFX': 'MetalFX Upscaling',
    'TOOLTIP|MetalFX': 'Enlarge the picture to the screen with Apple MetalFX when the resolution is lower than the screen.',
    'LabelAnisotropic': 'Anisotropic Filtering',
    'TOOLTIP|Anisotropic': 'Keep the road and distant textures sharp up to the horizon. 16x is the sharpest.',
    'LabelAntiAliasing': 'Anti-Aliasing',
    'TOOLTIP|AntiAliasing': 'Smooth the jagged edges that remain, such as fences and cables (FXAA).',
    'LabelSharpening': 'Sharpening',
    'TOOLTIP|Sharpening': 'Make the picture crisper with AMD FidelityFX CAS.',
    'LabelColorBoost': 'Color Boost',
    'TOOLTIP|ColorBoost': 'Richer colors and more contrast than the original picture.',
    'LabelHDR': 'HDR',
    'TOOLTIP|HDR': 'Brighter lights and reflections on an HDR display, such as a MacBook Pro XDR screen.',
    'ItemOff': 'Off',
    'ItemOn': 'On',
    'Item2x': '2x',
    'Item4x': '4x',
    'Item8x': '8x',
    'Item16x': '16x',
    'ItemFXAA': 'FXAA',
    'ItemLow': 'Low',
    'ItemMedium': 'Medium',
    'ItemHigh': 'High',
}
# The Graphics page keeps these texts of the disc's Camera page (its buttons); the Camera settings texts go.
GRAPHICS_KEPT = ('OK', 'Cancel', 'TOOLTIP|ok', 'TOOLTIP|cancel')

# The Resolution items after Native have no stored text: the option script writes the screen's resolutions into them
# at run time (native/gs_resolution.hpp) and removes the items the screen does not use. (A stored text would win: the
# closed list shows an item's text key, not the text the script wrote.)
RESOLUTION_SLOTS = 5

# Rows as (widget name, label key, popup items as (widget name, text key or None for a text the script writes)).
# The tooltip key of a row is its widget name.
SCREEN_ROWS = [
    ('Display', 'LabelDisplay', [('Window', 'Window'), ('FullScreen', 'FullScreen')]),
]
GRAPHICS_ROWS = [
    ('Resolution', 'LabelResolution',
     [('ResNative', 'ResNative')] + [(f'Res{slot}', None) for slot in range(1, RESOLUTION_SLOTS + 1)]),
    ('MetalFX', 'LabelMetalFX', [('MetalFXOff', 'ItemOff'), ('MetalFXOn', 'ItemOn')]),
    ('Anisotropic', 'LabelAnisotropic',
     [('AnisotropicOff', 'ItemOff')] + [(f'Anisotropic{level}x', f'Item{level}x') for level in (2, 4, 8, 16)]),
    ('AntiAliasing', 'LabelAntiAliasing', [('AntiAliasingOff', 'ItemOff'), ('AntiAliasingFXAA', 'ItemFXAA')]),
    ('Sharpening', 'LabelSharpening', [('SharpeningOff', 'ItemOff'), ('SharpeningLow', 'ItemLow'),
                                       ('SharpeningMedium', 'ItemMedium'), ('SharpeningHigh', 'ItemHigh')]),
    ('ColorBoost', 'LabelColorBoost', [('ColorBoostOff', 'ItemOff'), ('ColorBoostLow', 'ItemLow'),
                                       ('ColorBoostMedium', 'ItemMedium'), ('ColorBoostHigh', 'ItemHigh')]),
    ('HDR', 'LabelHDR', [('HdrOff', 'ItemOff'), ('HdrOn', 'ItemOn')]),
]

# The Screen page's rows alternate two colours, from the light one under the title; Video Output has the dark one.
LIGHT_ROW, DARK_ROW = 'RGBA {154 154 161 183}', 'RGBA {144 144 150 183}'
VIDEO_OUTPUT_TOP = 116
ROWS_TOP = 20  # under the 20-pixel title
ROW_HEIGHT = 32
SCREEN_PANE_ROWS = ['bg', 'Title', 'Wide', 'Vertical', 'Horizontal', 'HiVision', 'Buttons']
# The Graphics page's pane sits higher than the Screen page's, so that its seven rows stay above the tooltip bar (y 438).
PANE_GEOMETRY = ('geometry rectangle {160 130 320 150}', 'geometry rectangle {160 98 320 150}')


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


def _replace_once(lines, old, new):
    hits = [index for index, line in enumerate(lines) if line.strip() == old]
    if len(hits) != 1:
        raise ValueError(f'{old!r} found {len(hits)} times')
    lines[hits[0]] = lines[hits[0]].replace(old, new)


def _children(lines, start):
    """The child blocks [(first line, last line)] of the 'children [n] {' line at lines[start]."""
    blocks = []
    index = start + 1
    while lines[index].strip() != '}':
        end = _block_end(lines, index)
        blocks.append((index, end))
        index = end + 1
    return blocks, index


def _item_block(item, template):
    """A popup item (Composite with bgf, dot and label) from the Normal item of the Video Output row."""
    name, key = item
    return [line.replace('name string {"Normal"}', f'name string {{"{name}"}}')
                .replace('key string {"Normal"}', f'key string {{"{key}"}}') for line in template
            if key is not None or line.strip() != 'key string {"Normal"}']


def option_row(hivision, row, top, colour):
    """A copy of the Video Output row with our name, texts, place, colour and popup items."""
    name, label, popup_items = row
    lines = list(hivision)
    for old, new in (('name string {"HiVision"}', f'name string {{"{name}"}}'),
                     ('key string {"LabelHiVision"}', f'key string {{"{label}"}}'),
                     ('tooltip_key string {"HiVision"}', f'tooltip_key string {{"{name}"}}'),
                     (f'geometry rectangle {{0 {VIDEO_OUTPUT_TOP} 320 32}}', f'geometry rectangle {{0 {top} 320 32}}'),
                     (DARK_ROW, colour)):
        _replace_once(lines, old, new)
    # The popup list: keep its background, replace the three items by ours.
    vbox = _find_line(lines, 'name string {"vbox"}')
    children = vbox + 2
    if lines[children].strip() != 'children [4] {':
        raise ValueError('Video Output popup: unexpected item list')
    items, _ = _children(lines, children)
    names = [lines[start + 1].strip() for start, _ in items]
    if names != ['name string {"bg"}', 'name string {"Normal"}', 'name string {"Mode480p"}',
                 'name string {"Mode1080i"}']:
        raise ValueError(f'Video Output popup items: {names}')
    template = lines[items[1][0]:items[1][1] + 1]
    new_items = lines[items[0][0]:items[0][1] + 1]
    for index, item in enumerate(popup_items):
        new_items += [line.replace('geometry rectangle {0 0 160 24}', f'geometry rectangle {{0 {24 * index} 160 24}}')
                      for line in _item_block(item, template)]
    indent = lines[children][:len(lines[children]) - len(lines[children].lstrip('\t'))]
    return (lines[:children] + [f'{indent}children [{1 + len(popup_items)}] {{'] + new_items +
            lines[items[-1][1] + 1:])


def _pane_rows(page):
    """The Screen page's pane: (index of its 'children' line, its row blocks by name, index of its closing line)."""
    pane = _find_line(page, 'name string {"Pane"}')
    children = next(index for index in range(pane, len(page)) if page[index].strip().startswith('children ['))
    if page[children].strip() != f'children [{len(SCREEN_PANE_ROWS)}] {{':
        raise ValueError('Screen page: unexpected row count')
    blocks, closing = _children(page, children)
    names = [page[start + 1].strip() for start, _ in blocks]
    if names != [f'name string {{"{name}"}}' for name in SCREEN_PANE_ROWS]:
        raise ValueError(f'Screen page rows: {names}')
    return children, dict(zip(SCREEN_PANE_ROWS, blocks)), closing


def screen_page(page):
    """The Screen page with SCREEN_ROWS after the Video Output row."""
    page = list(page)
    children, blocks, _ = _pane_rows(page)
    start, end = blocks['HiVision']
    hivision = page[start:end + 1]
    colours = [LIGHT_ROW, DARK_ROW]
    rows = [line for position, row in enumerate(SCREEN_ROWS)
            for line in option_row(hivision, row, VIDEO_OUTPUT_TOP + ROW_HEIGHT * (position + 1), colours[position % 2])]
    page[children] = page[children].replace(f'children [{len(SCREEN_PANE_ROWS)}]',
                                            f'children [{len(SCREEN_PANE_ROWS) + len(SCREEN_ROWS)}]')
    return page[:end + 1] + rows + page[end + 1:]


def graphics_page(page):
    """The Graphics page: the Screen page's frame (background, title, buttons, tooltip bar) with GRAPHICS_ROWS."""
    page = list(page)
    _replace_once(page, 'name string {"ScreenRoot"}', f'name string {{"{GRAPHICS_ROOT}"}}')
    _replace_once(page, 'key string {"TitleScreen"}', 'key string {"TitleGraphics"}')
    _replace_once(page, *PANE_GEOMETRY)
    children, blocks, closing = _pane_rows(page)
    start, end = blocks['HiVision']
    hivision = page[start:end + 1]
    colours = [LIGHT_ROW, DARK_ROW]
    rows = [line for position, row in enumerate(GRAPHICS_ROWS)
            for line in option_row(hivision, row, ROWS_TOP + ROW_HEIGHT * position, colours[position % 2])]
    kept = [page[blocks[name][0]:blocks[name][1] + 1] for name in ('bg', 'Title')]
    indent = page[children][:len(page[children]) - len(page[children].lstrip('\t'))]
    return (page[:children] + [f'{indent}children [{3 + len(GRAPHICS_ROWS)}] {{'] + kept[0] + kept[1] + rows +
            page[blocks['Buttons'][0]:blocks['Buttons'][1] + 1] + page[closing:])


def edit_mproject(text):
    """Adds the Display Mode row to the Screen page and the Graphics page after it."""
    lines = text.split('\n')
    project_pages = next((index for index, line in enumerate(lines) if line.startswith('\tchildren [')), None)
    if lines[0] != 'Project {' or project_pages is None:
        raise ValueError('not an option project')
    if any(line.strip() == f'name string {{"{GRAPHICS_ROOT}"}}' for line in lines):
        raise ValueError(f'the project already has a {GRAPHICS_ROOT} page')
    pages = int(lines[project_pages].strip()[len('children ['):-len('] {')])
    start = _find_line(lines, 'name string {"ScreenRoot"}') - 1
    end = _block_end(lines, start)
    original = lines[start:end + 1]
    lines[project_pages] = f'\tchildren [{pages + 1}] {{'
    return '\n'.join(lines[:start] + screen_page(original) + graphics_page(original) + lines[end + 1:])


def edit_rtext(data):
    pages = gt4_rtext.read(data)
    for page, texts in ((OPTION_PAGE, OPTION_TEXTS), (SCREEN_PAGE, SCREEN_TEXTS)):
        for key in texts:
            if key in pages[page]:
                raise ValueError(f'{page} already has {key}')
        pages[page].update(texts)
    camera = pages[GRAPHICS_PAGE]
    pages[GRAPHICS_PAGE] = {key: camera[key] for key in GRAPHICS_KEPT}
    pages[GRAPHICS_PAGE].update(GRAPHICS_TEXTS)
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
        ICONS: gt4_option_icon.with_graphics_icon(originals[ICONS]),
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
