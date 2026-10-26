"""In-game Graphics menu: RT03 texts, the Display Mode and Resolution row edits and the menu runtime capsule, on
hand-made inputs."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import gt4_graphics_menu as menu
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
    rows = [lambda d, n=name: widget("Composite", d, [f'name string {{"{n}"}}']) for name in
            ("bg", "Title", "Wide", "Vertical", "Horizontal")]
    rows += [video_output_row, lambda d: widget("Composite", d, ['name string {"Buttons"}'])]
    pane = lambda d: widget("VBox", d, ['name string {"Pane"}', "packing digit {1}", "geometry rectangle {160 130 320 150}"],
                           rows)
    page = widget("RootWindow", 2, ['name string {"ScreenRoot"}'], [pane])
    return "\n".join(["Project {", "\tchildren [1] {"] + page + ["\t}", "}"])


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


class DisplayRowTests(unittest.TestCase):
    def test_row_is_added_after_video_output(self):
        edited = menu.edit_mproject(screen_page()).split("\n")
        stripped = [line.strip() for line in edited]
        pane = stripped.index('name string {"Pane"}')
        self.assertEqual(stripped[pane + 3], "children [11] {")
        self.assertEqual(stripped[pane + 2], "geometry rectangle {160 82 320 150}")
        names = [line for line in stripped if line.startswith('name string {"')]
        self.assertLess(names.index('name string {"HiVision"}'), names.index('name string {"Display"}'))
        self.assertLess(names.index('name string {"Display"}'), names.index('name string {"Buttons"}'))
        start = stripped.index('name string {"Display"}') - 1
        row = edited[start:menu._block_end(edited, start) + 1]
        text = "\n".join(row)
        for expected in ('key string {"LabelDisplay"}', 'tooltip_key string {"Display"}', "visible digit {0}",
                         "geometry rectangle {0 148 320 32}", "RGBA {154 154 161 183}", 'name string {"Window"}',
                         'name string {"FullScreen"}', 'key string {"FullScreen"}', "geometry rectangle {0 24 160 24}"):
            self.assertIn(expected, text)
        self.assertNotIn("Mode480p", text)
        self.assertIn("children [3] {", [line.strip() for line in row])
        self.assertEqual(sum(line.count("{") - line.count("}") for line in row), 0)
        # The original row is untouched and both rows are siblings in the pane.
        hivision = stripped.index('name string {"HiVision"}') - 1
        self.assertEqual(edited[hivision][:-len("Composite {")], edited[start][:-len("Composite {")])
        self.assertIn('key string {"Mode1080i"}', stripped)

    def test_resolution_row_follows_the_display_row(self):
        edited = menu.edit_mproject(screen_page()).split("\n")
        stripped = [line.strip() for line in edited]
        names = [line for line in stripped if line.startswith('name string {"')]
        self.assertLess(names.index('name string {"Display"}'), names.index('name string {"Resolution"}'))
        self.assertLess(names.index('name string {"Resolution"}'), names.index('name string {"Buttons"}'))
        start = stripped.index('name string {"Resolution"}') - 1
        row = edited[start:menu._block_end(edited, start) + 1]
        text = "\n".join(row)
        for expected in ('key string {"LabelResolution"}', 'tooltip_key string {"Resolution"}', "visible digit {0}",
                         "geometry rectangle {0 180 320 32}", "RGBA {144 144 150 183}", 'key string {"ResNative"}',
                         'name string {"Res1"}', 'name string {"Res5"}', "geometry rectangle {0 120 160 24}"):
            self.assertIn(expected, text)
        # The script writes the resolutions: the items after Native have no text key.
        self.assertNotIn('key string {"Res1"}', text)
        self.assertEqual(text.count("key string {"), 3)  # the row label, its tooltip and the Native item
        self.assertIn("children [7] {", [line.strip() for line in row])
        self.assertEqual(sum(line.count("{") - line.count("}") for line in row), 0)

    def test_hdr_and_metalfx_rows_close_the_list(self):
        edited = menu.edit_mproject(screen_page()).split("\n")
        stripped = [line.strip() for line in edited]
        names = [line for line in stripped if line.startswith('name string {"')]
        order = [names.index(f'name string {{"{name}"}}') for name in ("Resolution", "HDR", "MetalFX", "Buttons")]
        self.assertEqual(order, sorted(order))
        start = stripped.index('name string {"MetalFX"}') - 1
        text = "\n".join(edited[start:menu._block_end(edited, start) + 1])
        for expected in ('key string {"LabelMetalFX"}', "geometry rectangle {0 244 320 32}", 'name string {"MetalFXOn"}',
                         'key string {"ItemOn"}'):
            self.assertIn(expected, text)

    def test_unexpected_pages_are_refused(self):
        with self.assertRaises(ValueError):
            menu.edit_mproject(screen_page().replace('children [7]', 'children [6]'))
        with self.assertRaises(ValueError):
            menu.edit_mproject(screen_page().replace('"Mode1080i"', '"Mode720p"'))

    def test_texts_are_added_to_the_screen_page_once(self):
        data = rtext.write({menu.SCREEN_PAGE: {"LabelWide": "Aspect Ratio"}, "Other": {"k": "v"}})
        pages = rtext.read(menu.edit_rtext(data))
        self.assertEqual(pages[menu.SCREEN_PAGE]["LabelDisplay"], "Display Mode")
        self.assertEqual(pages[menu.SCREEN_PAGE]["FullScreen"], "Full Screen")
        self.assertEqual(pages[menu.SCREEN_PAGE]["LabelResolution"], "Resolution")
        self.assertEqual(pages[menu.SCREEN_PAGE]["ResNative"], "Native")
        self.assertNotIn("Res5", pages[menu.SCREEN_PAGE])
        self.assertEqual(pages[menu.SCREEN_PAGE]["LabelMetalFX"], "MetalFX Upscaling")
        self.assertEqual(pages["Other"], {"k": "v"})
        with self.assertRaises(ValueError):
            menu.edit_rtext(menu.edit_rtext(data))


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
