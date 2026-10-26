"""The icon of the Graphics tile in GT4's Options menu, drawn from the disc's own Picture Quality icon.

The option tiles' icons are Tex1 textures in a gpb2 package (projects/option/US/OptionRoot.gpb, checked on the NTSC-U
v2.00 disc):
  gpb2: "gpb2", u32 0, u32 0, u32 entry count, then per entry u32 name offset, u32 data offset, u32 data size, u32 0
  Tex1 of an icon: one 104x45 picture of 8-bit indices (PSMT8) and a 256-colour palette (PSMCT32 16x16, alpha 0-128,
  entries in the PS2's CSM1 order: within each run of 32, entries 8-15 and 16-23 are swapped). The transfer records
  (u32 data offset, u16 buffer, u8 buffer width, u8 format, u16 width, u16 height) start at the offset in the header's
  u32 at 0x1C, their count is the u16 at 0x16.
The Graphics icon is the Picture Quality television (image/option/Color.png) with its colour bars replaced by a blue
screen showing "HD", drawn in the screen's perspective. It goes into the slot of the disc's unused Camera tile icon
(image/option/Camera.png), whose size and layout are the same, so the package keeps its size.

Everything written is derived from game data and stays under private/.
"""

import struct

ICON_SOURCE = 'image/option/Color.png'
ICON_SLOT = 'image/option/Camera.png'
PSMT8 = 0x13
PSMCT32 = 0x00

# The television's screen in the Picture Quality icon (pixel corners: top left, top right, bottom right, bottom left),
# inside its dark frame.
SCREEN = ((33.6, 7.8), (63.2, 9.7), (63.2, 33.9), (33.6, 30.9))
# The picture drawn on it, in screen units (30 wide, 23 high): "HD" in a sans-serif bold, white on a blue gradient.
SCREEN_UNITS = (30.0, 23.0)
TOP_BLUE, BOTTOM_BLUE, LETTERS = (20, 34, 86), (38, 78, 168), (238, 242, 250)
SAMPLES = 4  # per axis, for anti-aliasing


def gpb_entries(data):
    """[(name, data offset, data size)] of a gpb2 package."""
    if data[:4] != b'gpb2':
        raise ValueError('not a gpb2 package')
    count = struct.unpack_from('<I', data, 12)[0]
    entries = []
    for index in range(count):
        name_offset, offset, size, _ = struct.unpack_from('<IIII', data, 16 + 16 * index)
        name = data[name_offset:data.index(b'\0', name_offset)].decode('latin-1')
        entries.append((name, offset, size))
    return entries


def _transfers(texture):
    if texture[:4] != b'Tex1':
        raise ValueError('not a Tex1 texture')
    count = struct.unpack_from('<H', texture, 0x16)[0]
    table = struct.unpack_from('<I', texture, 0x1C)[0]
    records = [struct.unpack_from('<IHBBHH', texture, table + 12 * index) for index in range(count)]
    pictures = [record for record in records if record[3] == PSMT8]
    palettes = [record for record in records if record[3] == PSMCT32 and record[4:] == (16, 16)]
    if len(records) != 2 or len(pictures) != 1 or len(palettes) != 1:
        raise ValueError('not a one-picture 8-bit Tex1 texture')
    return pictures[0], palettes[0]


def _csm1(entries):
    """The palette in the PS2's CSM1 order, or back (the swap is its own inverse)."""
    entries = list(entries)
    for base in range(0, 256, 32):
        entries[base + 8:base + 16], entries[base + 16:base + 24] = entries[base + 16:base + 24], entries[base + 8:base + 16]
    return entries


def read_icon(texture):
    """(width, height, [(r, g, b, a) per pixel, a 0-255])."""
    (offset, _, _, _, width, height), (palette_offset, *_) = _transfers(texture)
    palette = _csm1(struct.unpack_from('<4B', texture, palette_offset + 4 * index) for index in range(256))
    colours = [(r, g, b, min(255, a * 255 // 128)) for r, g, b, a in palette]
    return width, height, [colours[index] for index in texture[offset:offset + width * height]]


def quantize(pixels, count=256):
    """Median cut, then a few k-means passes: (palette of at most `count` RGBA colours, index per pixel)."""
    unique = sorted(set(pixels))
    if len(unique) <= count:
        lookup = {colour: index for index, colour in enumerate(unique)}
        return unique, [lookup[colour] for colour in pixels]
    boxes = [unique]
    while len(boxes) < count:
        box = max((box for box in boxes if len(box) > 1), key=lambda box: max(
            max(colour[channel] for colour in box) - min(colour[channel] for colour in box) for channel in range(4)))
        channel = max(range(4), key=lambda c: max(colour[c] for colour in box) - min(colour[c] for colour in box))
        box.sort(key=lambda colour: colour[channel])
        boxes.remove(box)
        boxes += [box[:len(box) // 2], box[len(box) // 2:]]
    palette = [tuple(sum(colour[c] for colour in box) // len(box) for c in range(4)) for box in boxes]
    nearest = {}
    for _ in range(4):
        nearest = {colour: min(range(len(palette)), key=lambda index: sum(
            (colour[c] - palette[index][c]) ** 2 for c in range(4))) for colour in unique}
        sums = [[0, 0, 0, 0, 0] for _ in palette]
        for colour in pixels:
            total = sums[nearest[colour]]
            for c in range(4):
                total[c] += colour[c]
            total[4] += 1
        palette = [tuple(total[c] // total[4] for c in range(4)) if total[4] else palette[index]
                   for index, total in enumerate(sums)]
    return palette, [nearest[colour] for colour in pixels]


def write_icon(texture, pixels):
    """The texture with its picture and palette replaced by `pixels` (same size), quantized to 256 colours."""
    (offset, _, _, _, width, height), (palette_offset, *_) = _transfers(texture)
    if len(pixels) != width * height:
        raise ValueError('the picture does not have the texture size')
    palette, indices = quantize(pixels)
    palette = list(palette) + [(0, 0, 0, 0)] * (256 - len(palette))
    output = bytearray(texture)
    output[offset:offset + width * height] = bytes(indices)
    for index, (r, g, b, a) in enumerate(_csm1(palette)):
        struct.pack_into('<4B', output, palette_offset + 4 * index, r, g, b, (a * 128 + 127) // 255)
    return bytes(output)


def _screen_point(px, py):
    """(u, v) in the unit square of the SCREEN quad for pixel point (px, py), by Newton on the bilinear map."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = SCREEN
    u = v = 0.5
    for _ in range(8):
        x = (1 - u) * (1 - v) * x0 + u * (1 - v) * x1 + u * v * x2 + (1 - u) * v * x3
        y = (1 - u) * (1 - v) * y0 + u * (1 - v) * y1 + u * v * y2 + (1 - u) * v * y3
        dxu, dyu = (1 - v) * (x1 - x0) + v * (x2 - x3), (1 - v) * (y1 - y0) + v * (y2 - y3)
        dxv, dyv = (1 - u) * (x3 - x0) + u * (x2 - x1), (1 - u) * (y3 - y0) + u * (y2 - y1)
        determinant = dxu * dyv - dxv * dyu
        u -= ((x - px) * dyv - (y - py) * dxv) / determinant
        v -= ((y - py) * dxu - (x - px) * dyu) / determinant
    return u, v


def _letters(x, y):
    """True inside "HD" at screen units (x, y)."""
    top, bottom, stroke = 5.5, 17.5, 2.7
    middle = (top + bottom) / 2
    if 4.0 <= x <= 13.0 and top <= y <= bottom:  # H
        return x <= 4.0 + stroke or x >= 13.0 - stroke or abs(y - middle) <= stroke / 2
    radius = (bottom - top) / 2
    if 15.0 <= x <= 20.0 + radius and top <= y <= bottom:  # D: stem and bowl, less the counter
        outer = x <= 20.0 or (x - 20.0) ** 2 + (y - middle) ** 2 <= radius ** 2
        inner_radius = radius - stroke
        inner = x >= 15.0 + stroke and abs(y - middle) <= inner_radius and (
            x <= 20.0 or (x - 20.0) ** 2 + (y - middle) ** 2 <= inner_radius ** 2)
        return outer and not inner
    return False


def _screen_colour(u, v):
    if _letters(u * SCREEN_UNITS[0], v * SCREEN_UNITS[1]):
        return LETTERS
    return tuple(round(top + (bottom - top) * v) for top, bottom in zip(TOP_BLUE, BOTTOM_BLUE))


def graphics_icon(width, height, pixels):
    """The Picture Quality icon's pixels with the HD screen drawn over its colour bars."""
    output = list(pixels)
    xs = [x for x, _ in SCREEN]
    ys = [y for _, y in SCREEN]
    for py in range(int(min(ys)), int(max(ys)) + 2):
        for px in range(int(min(xs)), int(max(xs)) + 2):
            if not (0 <= px < width and 0 <= py < height):
                continue
            original = pixels[py * width + px]
            total = [0, 0, 0, 0]
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    u, v = _screen_point(px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES)
                    colour = _screen_colour(u, v) + (255,) if 0 <= u <= 1 and 0 <= v <= 1 else original
                    for c in range(4):
                        total[c] += colour[c]
            output[py * width + px] = tuple(round(value / SAMPLES ** 2) for value in total)
    return output


def with_graphics_icon(package):
    """OptionRoot.gpb with the Graphics icon in the Camera icon's slot."""
    entries = {name: (offset, size) for name, offset, size in gpb_entries(package)}
    if ICON_SOURCE not in entries or ICON_SLOT not in entries:
        raise ValueError(f'{ICON_SOURCE} or {ICON_SLOT} is missing from the package')
    source_offset, source_size = entries[ICON_SOURCE]
    slot_offset, slot_size = entries[ICON_SLOT]
    width, height, pixels = read_icon(package[source_offset:source_offset + source_size])
    slot = package[slot_offset:slot_offset + slot_size]
    if read_icon(slot)[:2] != (width, height):
        raise ValueError('the Camera icon slot does not have the size of the Picture Quality icon')
    icon = write_icon(slot, graphics_icon(width, height, pixels))
    return package[:slot_offset] + icon + package[slot_offset + slot_size:]
