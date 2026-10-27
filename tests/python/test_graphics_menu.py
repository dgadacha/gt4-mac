"""In-game Graphics menu: RT03 texts, the Screen page's Display Mode row, the Graphics page, its tile icon and the menu
runtime capsule, on hand-made inputs."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import gt4_graphics_menu as menu
import gt4_option_icon as icon
import gt4_rtext as rtext
import prepare_menu_runtime as capsule


def widget(kind, depth, lines, children=()):
    """A .mproject block: tab indentation, one property per line, children counted as the game writes them."""
    tabs = "\t" * depth
    block = [f"{tabs}{kind} {{"] + [f"{tabs}\t{line}" for line in lines]
    if children:
        block.append(f"{tabs}\tchildren [{len(children)}] {{")
        for child in children:
            block += child(depth + 2)
        block.append(f"{tabs}\t}}")
    return block + [f"{tabs}}}"]


def popup_item(name, top):
    return lambda depth: widget("Composite", depth, [f'name string {{"{name}"}}', f"geometry rectangle {{0 {top} 160 24}}"], [
        lambda d: widget("ColorFace", d, ['name string {"bgf"}']),
        lambda d: widget("TextFace", d, ['name string {"label"}', f'key string {{"{name}"}}']),
    ])


def video_output_row(depth):
    vbox = lambda d: widget("VBox", d, ['name string {"vbox"}', "geometry rectangle {0 0 160 24}"], [
        lambda e: widget("ColorFace", e, ['name string {"bg"}']),
        popup_item("Normal", 0), popup_item("Mode480p", 24), popup_item("Mode1080i", 48)])
    option_menu = lambda d: widget("OptionMenu", d, ['name string {"OptionMenu"}', 'tooltip_key string {"HiVision"}'], [
        lambda e: widget("FrameImageFace", e, ['name string {"bg"}']),
        lambda e: widget("Composite", e, ['name string {"popup"}'], [
            lambda f: widget("ColorFace", f, ['name string {"shadow"}']), vbox])])
    return widget("Composite", depth, ['name string {"HiVision"}', "visible digit {0}",
                                       "geometry rectangle {0 116 320 32}"], [
        lambda d: widget("ColorFace", d, ['name string {"bg"}', "RGBA {144 144 150 183}"]),
        lambda d: widget("TextFace", d, ['name string {"label"}', 'key string {"LabelHiVision"}']),
        option_menu])


def screen_page():
    """A project with the option menu's Screen page between two other pages."""
    title = lambda d: widget("Composite", d, ['name string {"Title"}'], [
        lambda e: widget("TextFace", e, ['name string {"title"}', 'key string {"TitleScreen"}'])])
    rows = [lambda d, n=name: widget("Composite", d, [f'name string {{"{n}"}}']) for name in
            ("Wide", "Vertical", "Horizontal")]
    rows = ([lambda d: widget("FrameImageFace", d, ['name string {"bg"}']), title] + rows +
            [video_output_row, lambda d: widget("Composite", d, ['name string {"Buttons"}'])])
    pane = lambda d: widget("VBox", d, ['name string {"Pane"}', "packing digit {1}", "geometry rectangle {160 130 320 150}"],
                           rows)
    tooltip = lambda d: widget("Composite", d, ['name string {"ToolTip"}'])
    page = widget("RootWindow", 2, ['name string {"ScreenRoot"}'], [pane, tooltip])
    before = widget("RootWindow", 2, ['name string {"LanguageRoot"}'])
    after = widget("RootWindow", 2, ['name string {"RaceRoot"}'])
    return "\n".join(["Project {", '\tname string {"OptionProject"}', "\tchildren [3] {"] + before + page + after +
                     ["\t}", "}"])


def page_block(lines, name):
    """The lines of the page `name` (its RootWindow block)."""
    start = [line.strip() for line in lines].index(f'name string {{"{name}"}}') - 1
    return lines[start:menu._block_end(lines, start) + 1]


def row_block(lines, name):
    start = [line.strip() for line in lines].index(f'name string {{"{name}"}}') - 1
    return lines[start:menu._block_end(lines, start) + 1]


def row_names(page):
    """The names of the pane's rows, in order."""
    stripped = [line.strip() for line in page]
    pane = stripped.index('name string {"Pane"}')
    children = next(index for index in range(pane, len(page)) if stripped[index].startswith("children ["))
    blocks, _ = menu._children(page, children)
    return [stripped[start + 1][len('name string {"'):-len('"}')] for start, _ in blocks]


class RTextTests(unittest.TestCase):
    def test_layout_of_a_one_entry_file(self):
        expected = (b"RT03" + struct.pack("<III", 0, 0, 1) + struct.pack("<III", 32, 1, 36) + b"^^^^" +
                    b"P\0\0\0" + struct.pack("<II", 44, 48) + b"k\0\0\0" + b"v\0\0\0")
        self.assertEqual(rtext.write({"P": {"k": "v"}}), expected)
        self.assertEqual(rtext.read(expected), {"P": {"k": "v"}})

    def test_pages_and_keys_are_sorted_and_strings_padded(self):
        pages = {"b::Page": {"Zeta": "last", "TOOLTIP|x": "tip", "Alpha": "first"}, "A": {"key": "abcd"}}
        data = rtext.write(pages)
        self.assertEqual(rtext.read(data), pages)
        _, _, count = struct.unpack_from("<III", data, 4)
        names = []
        for index in range(count):
            name, entries, table, mark = struct.unpack_from("<III4s", data, 16 + 16 * index)
            self.assertEqual(mark, b"^^^^")
            self.assertEqual(name % 4, 0)
            names.append(data[name:data.index(b"\0", name)])
            keys = [data[k:data.index(b"\0", k)] for k, _ in
                    (struct.unpack_from("<II", data, table + 8 * entry) for entry in range(entries))]
            self.assertEqual(keys, sorted(keys))
        self.assertEqual(names, [b"A", b"b::Page"])
        # "abcd" with its NUL takes 8 bytes: strings are padded to 4.
        self.assertIn(b"abcd\0\0\0\0", data)

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            rtext.read(b"RT04" + bytes(12))


class ScreenPageTests(unittest.TestCase):
    def test_display_row_is_added_after_video_output(self):
        edited = menu.edit_mproject(screen_page()).split("\n")
        page = page_block(edited, "ScreenRoot")
        stripped = [line.strip() for line in page]
        self.assertEqual(row_names(page), ["bg", "Title", "Wide", "Vertical", "Horizontal", "HiVision", "Display",
                                           "Buttons"])
        # The page keeps its place on screen: five rows fit above the tooltip bar.
        self.assertIn("geometry rectangle {160 130 320 150}", stripped)
        row = row_block(page, "Display")
        text = "\n".join(row)
        for expected in ('key string {"LabelDisplay"}', 'tooltip_key string {"Display"}', "visible digit {0}",
                         "geometry rectangle {0 148 320 32}", "RGBA {154 154 161 183}", 'name string {"Window"}',
                         'name string {"FullScreen"}', 'key string {"FullScreen"}', "geometry rectangle {0 24 160 24}"):
            self.assertIn(expected, text)
        self.assertNotIn("Mode480p", text)
        self.assertIn("children [3] {", [line.strip() for line in row])
        self.assertEqual(sum(line.count("{") - line.count("}") for line in row), 0)
        # The original row is untouched and both rows are siblings in the pane.
        hivision = row_block(page, "HiVision")
        self.assertEqual(hivision[0], row[0])
        self.assertIn('key string {"Mode1080i"}', stripped)
        self.assertNotIn('name string {"Resolution"}', stripped)


class GraphicsPageTests(unittest.TestCase):
    def setUp(self):
        self.edited = menu.edit_mproject(screen_page()).split("\n")
        self.page = page_block(self.edited, menu.GRAPHICS_ROOT)

    def test_page_follows_the_screen_page_in_the_project(self):
        roots = [line.strip() for line in self.edited if line.startswith("\t\t\tname string")]
        self.assertEqual(roots, ['name string {"LanguageRoot"}', 'name string {"ScreenRoot"}',
                                 'name string {"CameraRoot"}', 'name string {"RaceRoot"}'])
        self.assertEqual(self.edited[2], "\tchildren [4] {")
        self.assertEqual(sum(line.count("{") - line.count("}") for line in self.edited), 0)

    def test_page_has_the_screen_frame_and_our_rows(self):
        stripped = [line.strip() for line in self.page]
        self.assertEqual(row_names(self.page), ["bg", "Title"] + [row[0] for row in menu.GRAPHICS_ROWS] + ["Buttons"])
        self.assertIn('key string {"TitleGraphics"}', stripped)
        self.assertNotIn('key string {"TitleScreen"}', stripped)
        self.assertIn("geometry rectangle {160 62 320 150}", stripped)
        self.assertIn('name string {"ToolTip"}', stripped)
        for screen_row in ("Wide", "Vertical", "Horizontal", "HiVision", "Display"):
            self.assertNotIn(f'name string {{"{screen_row}"}}', stripped)

    def test_rows_alternate_colours_from_the_top(self):
        for position, (name, label, items) in enumerate(menu.GRAPHICS_ROWS):
            text = "\n".join(row_block(self.page, name))
            self.assertIn(f"geometry rectangle {{0 {20 + 32 * position} 320 32}}", text)
            self.assertIn(menu.LIGHT_ROW if position % 2 == 0 else menu.DARK_ROW, text)
            self.assertIn(f'key string {{"{label}"}}', text)
            self.assertIn(f'tooltip_key string {{"{name}"}}', text)
            self.assertIn(f"children [{1 + len(items)}] {{", text)

    def test_resolution_items_after_native_have_no_text(self):
        row = row_block(self.page, "Resolution")
        text = "\n".join(row)
        for expected in ('key string {"ResNative"}', 'name string {"Res1"}', 'name string {"Res5"}',
                         "geometry rectangle {0 120 160 24}"):
            self.assertIn(expected, text)
        # The script writes the resolutions: the items after Native have no text key.
        self.assertNotIn('key string {"Res1"}', text)
        self.assertEqual(text.count("key string {"), 3)  # the row label, its tooltip and the Native item
        self.assertEqual(sum(line.count("{") - line.count("}") for line in row), 0)

    def test_anisotropic_filtering_offers_five_levels(self):
        text = "\n".join(row_block(self.page, "Anisotropic"))
        for level, key in enumerate(("ItemOff", "Item2x", "Item4x", "Item8x", "Item16x")):
            self.assertIn(f'key string {{"{key}"}}', text)
            self.assertIn(f"geometry rectangle {{0 {24 * level} 160 24}}", text)

    def test_unexpected_projects_are_refused(self):
        with self.assertRaises(ValueError):
            menu.edit_mproject(screen_page().replace('"Mode1080i"', '"Mode720p"'))
        with self.assertRaises(ValueError):
            menu.edit_mproject(screen_page().replace('name string {"Horizontal"}', 'name string {"Other"}'))
        with self.assertRaises(ValueError):
            menu.edit_mproject(screen_page().replace('"TitleScreen"', '"TitleOther"'))
        with self.assertRaises(ValueError):
            menu.edit_mproject(menu.edit_mproject(screen_page()))


class TextTests(unittest.TestCase):
    def setUp(self):
        camera = {"OK": "OK", "Cancel": "Cancel", "TOOLTIP|ok": "Apply changes", "TOOLTIP|cancel": "Cancel",
                  "LabelFocus": "Focus", "TitleCamera": "Camera Settings"}
        self.data = rtext.write({menu.OPTION_PAGE: {"Screen": "Screen"}, menu.SCREEN_PAGE: {"LabelWide": "Aspect Ratio"},
                                 menu.GRAPHICS_PAGE: camera, "Other": {"k": "v"}})

    def test_texts_go_to_their_pages(self):
        pages = rtext.read(menu.edit_rtext(self.data))
        self.assertEqual(pages[menu.OPTION_PAGE]["Graphics"], "Graphics")
        self.assertTrue(pages[menu.OPTION_PAGE]["TOOLTIP|Graphics"].startswith("Graphics Settings: "))
        self.assertEqual(pages[menu.SCREEN_PAGE]["LabelDisplay"], "Display Mode")
        self.assertEqual(pages[menu.SCREEN_PAGE]["FullScreen"], "Full Screen")
        self.assertNotIn("LabelResolution", pages[menu.SCREEN_PAGE])
        graphics = pages[menu.GRAPHICS_PAGE]
        self.assertEqual(graphics["TitleGraphics"], "Graphics Settings")
        self.assertEqual(graphics["LabelAnisotropic"], "Anisotropic Filtering")
        self.assertEqual(graphics["Item16x"], "16x")
        self.assertNotIn("Res5", graphics)
        # The Camera page keeps its buttons' texts only.
        self.assertEqual(graphics["TOOLTIP|ok"], "Apply changes")
        self.assertNotIn("LabelFocus", graphics)
        self.assertNotIn("TitleCamera", graphics)
        self.assertEqual(pages["Other"], {"k": "v"})

    def test_every_key_of_the_rows_has_a_text(self):
        graphics = rtext.read(menu.edit_rtext(self.data))[menu.GRAPHICS_PAGE]
        for name, label, items in menu.GRAPHICS_ROWS:
            self.assertIn(label, graphics)
            self.assertIn(f"TOOLTIP|{name}", graphics)
            for _, key in items:
                if key is not None:
                    self.assertIn(key, graphics)

    def test_editing_twice_is_refused(self):
        with self.assertRaises(ValueError):
            menu.edit_rtext(menu.edit_rtext(self.data))


def tex1(width, height, indices, palette):
    """A one-picture 8-bit Tex1 laid out as the option icons: header, two transfer records, indices, palette."""
    pixels_offset = 0x70
    palette_offset = pixels_offset + (width * height + 63) // 64 * 64
    size = palette_offset + 1024
    data = bytearray(size)
    data[0:4] = b"Tex1"
    struct.pack_into("<I", data, 0x0C, size)
    struct.pack_into("<HHII", data, 0x14, 1, 2, 0x30, 0x58)
    struct.pack_into("<IHBBHH", data, 0x58, pixels_offset, 0, 2, 0x13, width, height)
    struct.pack_into("<IHBBHH", data, 0x64, palette_offset, 29, 1, 0x00, 16, 16)
    data[pixels_offset:pixels_offset + width * height] = bytes(indices)
    for index, colour in enumerate(palette):
        struct.pack_into("<4B", data, palette_offset + 4 * index, *colour)
    return bytes(data)


def gpb(entries):
    """A gpb2 package of {name: data}."""
    header = bytearray(b"gpb2" + struct.pack("<III", 0, 0, len(entries)))
    names = bytearray()
    names_offset = 16 + 16 * len(entries)
    name_offsets = []
    for name in entries:
        name_offsets.append(names_offset + len(names))
        names += name.encode() + b"\0"
    body = bytearray()
    data_offset = names_offset + len(names)
    table = bytearray()
    for (name, data), name_offset in zip(entries.items(), name_offsets):
        table += struct.pack("<IIII", name_offset, data_offset + len(body), len(data), 0)
        body += data
    return bytes(header + table + names + body)


class IconTests(unittest.TestCase):
    def test_palette_is_read_in_csm1_order(self):
        palette = [(index, 0, 0, 0x80) for index in range(256)]
        texture = tex1(4, 1, [8, 16, 24, 40], palette)
        width, height, pixels = icon.read_icon(texture)
        self.assertEqual((width, height), (4, 1))
        # Stored entries 8 and 16 trade places (and 40 and 48 in the next run of 32); 24 stays.
        self.assertEqual([pixel[0] for pixel in pixels], [16, 8, 24, 48])
        self.assertEqual(pixels[0][3], 255)

    def test_a_written_icon_reads_back(self):
        texture = tex1(3, 2, [0] * 6, [(0, 0, 0, 0)] * 256)
        pixels = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128), (10, 20, 30, 0), (255, 0, 0, 255),
                  (1, 2, 3, 255)]
        written = icon.write_icon(texture, pixels)
        self.assertEqual(len(written), len(texture))
        self.assertEqual(written[:0x70], texture[:0x70])
        _, _, read = icon.read_icon(written)
        # Alpha goes through the PS2's 0-128 scale.
        self.assertEqual([pixel[:3] for pixel in read], [pixel[:3] for pixel in pixels])
        self.assertTrue(all(abs(a[3] - b[3]) <= 2 for a, b in zip(read, pixels)))

    def test_quantize_keeps_at_most_256_colours(self):
        pixels = [(red, green, 0, 255) for red in range(0, 256, 8) for green in range(0, 256, 8)]
        palette, indices = icon.quantize(pixels)
        self.assertLessEqual(len(palette), 256)
        self.assertEqual(len(indices), len(pixels))
        worst = max(sum((a - b) ** 2 for a, b in zip(pixel, palette[index])) for pixel, index in zip(pixels, indices))
        self.assertLess(worst, 3 * 16 ** 2)

    def test_the_screen_is_redrawn_and_the_rest_kept(self):
        width, height = 104, 45
        grey = (128, 128, 128, 255)
        pixels = [grey] * (width * height)
        drawn = icon.graphics_icon(width, height, pixels)
        self.assertEqual(drawn[2 * width + 2], grey)       # outside the television's screen
        self.assertEqual(drawn[40 * width + 90], grey)
        corner = drawn[12 * width + 36]                     # inside the screen, left of the letters: blue
        self.assertGreater(corner[2], corner[0] + 40)
        stem = drawn[20 * width + 40]                       # the H's left stem: white
        self.assertTrue(all(channel > 200 for channel in stem[:3]))

    def test_the_icon_goes_into_the_camera_slot(self):
        palette = [(index, index, index, 0x80) for index in range(256)]
        source = tex1(104, 45, [index % 256 for index in range(104 * 45)], palette)
        slot = tex1(104, 45, [0] * (104 * 45), palette)
        other = b"other entry"
        package = gpb({icon.ICON_SOURCE: source, icon.ICON_SLOT: slot, "image/option/Sound.png": other})
        edited = icon.with_graphics_icon(package)
        self.assertEqual(len(edited), len(package))
        entries = {name: (offset, size) for name, offset, size in icon.gpb_entries(edited)}
        offset, size = entries[icon.ICON_SOURCE]
        self.assertEqual(edited[offset:offset + size], source)
        offset, size = entries["image/option/Sound.png"]
        self.assertEqual(edited[offset:offset + size], other)
        offset, size = entries[icon.ICON_SLOT]
        self.assertNotEqual(edited[offset:offset + size], slot)
        with self.assertRaises(ValueError):
            icon.with_graphics_icon(gpb({icon.ICON_SOURCE: source}))


class MenuRuntimeCapsuleTests(unittest.TestCase):
    DISC = (capsule.INCLUDE_ANCHOR + "\nint open(const char *path) {\n" + capsule.OPEN_ANCHOR +
            "        std::fseek(file, 0, SEEK_SET);\n" + capsule.CLOSE_ANCHOR)
    DISPATCH = ("#include \"license_guard.hpp\"\n" + capsule.BRIDGE_INCLUDE_ANCHOR +
                "void dispatch(Cpu &c, std::uint32_t, std::uint32_t depth) {\n    const std::uint32_t pc = c.pc;\n" +
                capsule.BRIDGE_CALL_ANCHOR + "}\n")

    def test_hooks_reverse_to_their_inputs(self):
        disc = capsule.apply_disc_overlay(self.DISC)
        self.assertIn("gt4::disc_overlay::wrap(size", disc)
        self.assertEqual(capsule.remove_disc_overlay(disc), self.DISC)
        dispatch = capsule.apply_bridge(self.DISPATCH)
        self.assertIn("gt4::menu_bridge::run_callback(c, depth);", dispatch)
        self.assertIn("gt4::menu_bridge::is_native_invoker(pc)", dispatch)
        self.assertLess(dispatch.index(capsule.BRIDGE_CALL_ANCHOR), dispatch.index("run_callback"))
        self.assertEqual(capsule.remove_bridge(dispatch), self.DISPATCH)

    def test_missing_or_repeated_anchors_are_refused(self):
        with self.assertRaises(ValueError):
            capsule.apply_bridge(self.DISPATCH.replace(capsule.BRIDGE_CALL_ANCHOR, ""))
        with self.assertRaises(ValueError):
            capsule.apply_disc_overlay(self.DISC + capsule.OPEN_ANCHOR)

    def test_output_stays_under_private(self):
        with self.assertRaises(ValueError):
            capsule.prepare(Path("/tmp/menu-runtime"))


if __name__ == "__main__":
    unittest.main()
