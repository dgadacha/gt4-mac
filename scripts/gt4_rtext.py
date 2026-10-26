"""GT4 menu text files (RText RT03, projects/<name>/<language>/rtext.rt2): read, edit and write.

Layout (checked on projects/option/US/rtext.rt2 of the NTSC-U v2.00 disc, which this writer reproduces byte for byte):
  "RT03", u32 0, u32 0, u32 page count
  page table: per page u32 name offset, u32 entry count, u32 entry table offset, "^^^^"
  per page, in page order: the page name, its entry table (u32 key offset, u32 text offset per entry), then the key
  and text of every entry
Strings are NUL-terminated and padded with NULs to a multiple of 4 bytes. Pages are sorted by name and entries by key
(byte order), which the game's lookup relies on; write() keeps both sorted.

The text of a game file is game data: edited files are written under private/ and never committed.
"""

import struct

MAGIC = b'RT03'
PAGE_MARK = b'^^^^'
ENCODING = 'latin-1'


def _string(data, offset):
    end = data.index(b'\0', offset)
    return data[offset:end].decode(ENCODING)


def read(data):
    """Returns {page name: {key: text}}."""
    if data[:4] != MAGIC:
        raise ValueError('not an RT03 text file')
    _, _, count = struct.unpack_from('<III', data, 4)
    pages = {}
    for index in range(count):
        name_offset, entries, table, mark = struct.unpack_from('<III4s', data, 16 + 16 * index)
        if mark != PAGE_MARK:
            raise ValueError(f'page {index}: missing page mark')
        page = {}
        for entry in range(entries):
            key_offset, text_offset = struct.unpack_from('<II', data, table + 8 * entry)
            page[_string(data, key_offset)] = _string(data, text_offset)
        pages[_string(data, name_offset)] = page
    return pages


def _padded(text):
    raw = text.encode(ENCODING) + b'\0'
    return raw + b'\0' * (-len(raw) % 4)


def write(pages):
    """The RT03 bytes of {page name: {key: text}}, pages and keys sorted."""
    names = sorted(pages, key=lambda name: name.encode(ENCODING))
    header = bytearray(MAGIC + struct.pack('<III', 0, 0, len(names)))
    table_offset = len(header)
    body = bytearray()
    page_table = bytearray()
    base = table_offset + 16 * len(names)
    for name in names:
        entries = sorted(pages[name].items(), key=lambda item: item[0].encode(ENCODING))
        name_offset = base + len(body)
        body += _padded(name)
        entry_table = base + len(body)
        strings = bytearray()
        offsets = []
        string_base = entry_table + 8 * len(entries)
        for key, text in entries:
            key_offset = string_base + len(strings)
            strings += _padded(key)
            text_offset = string_base + len(strings)
            strings += _padded(text)
            offsets.append((key_offset, text_offset))
        for key_offset, text_offset in offsets:
            body += struct.pack('<II', key_offset, text_offset)
        body += strings
        page_table += struct.pack('<III', name_offset, len(entries), entry_table) + PAGE_MARK
    return bytes(header + page_table + body)
