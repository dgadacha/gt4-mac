"""GT4.VOL overlay: replacement files for the user's own disc, read by the game through native/disc_overlay.cpp.

The game reads its files from the volume GT4.VOL through a catalogue (RoFS, scripts/gt4_volume.py). An overlay
places each replacement file, PS2ZIP-compressed, in sectors past the end of the disc image, and rewrites the catalogue
records of those files to point there (data page, stored and decoded sizes). Only the catalogue pages that hold a
changed record are recompressed; every other stored page keeps its bytes. The overlay file lists the disc extents
to serve instead of (or past the end of) the image: the new catalogue and the new files.

The overlay is derived from game data: it is written under private/ and never committed. What the repository holds
is the recipe (our own edits, checked against the original files' hashes).

  build --iso <disc> --output private/<fresh folder> --replace <volume path>=<file> ... --text <volume path>=<old>=<new>
        --replace serves a whole new file; --text replaces every occurrence of a text by one of the same length.
"""

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import gt4_volume as volume  # noqa: E402

MAGIC = b'GT4OVL01'
SECTOR = 2048
PAGE_KEY = 0x14AC327A
PS2ZIP_MAGIC = 0xFFF7EEC5


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def stored_page_offsets(stored, logical_pages):
    return [struct.unpack_from('<I', stored, 64 + index * 4)[0] ^ (((index + 1) * PAGE_KEY) & 0xFFFFFFFF)
            for index in range(logical_pages + 1)]


def decode_page(segment):
    return bytes(value ^ 0x55 for value in volume.inflate_exact(segment, SECTOR, SECTOR, page=True))


def encode_page(page, final):
    """A page segment as the original encoder framed it: raw DEFLATE ended by a sync flush, the last page by a final
    block."""
    encoder = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = encoder.compress(bytes(value ^ 0x55 for value in page))
    return data + encoder.flush(zlib.Z_FINISH if final else zlib.Z_SYNC_FLUSH)


def file_locations(pages):
    """Maps every file record to (logical page, metadata offset in the decoded page)."""
    records, locations = [], {}
    for page_index, page in enumerate(pages):
        kind, count = struct.unpack_from('<HH', page)
        if kind != 0:
            continue
        for index in range(count // 2):
            key_offset, key_size, meta_offset, meta_size = struct.unpack_from('<HHHH', page, SECTOR - (index + 1) * 8)
            key = page[key_offset:key_offset + key_size]
            meta = page[meta_offset:meta_offset + meta_size]
            parent, name = int.from_bytes(key[:4], 'big'), key[4:].decode('utf-8')
            if meta[0] == 0:
                record = volume.Record(parent, name, 0, struct.unpack_from('<I', meta, 1)[0])
            else:
                data_page, _, packed = struct.unpack_from('<III', meta, 1)
                size = packed if meta[0] == 1 else struct.unpack_from('<I', meta, 13)[0]
                record = volume.Record(parent, name, meta[0], offset=data_page, stored_size=packed, size=size)
                locations[record] = (page_index, meta_offset)
            records.append(record)
    files, _ = volume.resolve_records(records)
    return {path: locations[record] for path, record in files.items() if record in locations}


def ps2zip(data):
    encoder = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    body = encoder.compress(data) + encoder.flush()
    return struct.pack('<II', PS2ZIP_MAGIC, (-len(data)) & 0xFFFFFFFF) + body


def build(iso_path, replacements):
    """replacements: {volume path: new decoded bytes}. Returns (extents, facts)."""
    with volume.verified_volume(iso_path) as stream:
        catalogue = volume.read_catalogue(stream)
        disc_size = stream.seek(0, 2)
        base = volume.VOLUME_OFFSET + volume.TOC_OFFSET
        header = volume.read_at(stream, base, 64, volume.VOLUME_OFFSET + volume.VOLUME_SIZE)
        _, _, stored_size, physical_pages, _, logical_pages = struct.unpack_from('<IIIIHH', header)
        stored = volume.read_at(stream, base, stored_size, volume.VOLUME_OFFSET + volume.VOLUME_SIZE)
        originals = {path: volume.decode_payload(
            volume.read_at(stream, volume.VOLUME_OFFSET + catalogue.files[path].offset,
                           catalogue.files[path].stored_size, volume.VOLUME_OFFSET + volume.VOLUME_SIZE),
            catalogue.files[path].kind, catalogue.files[path].size) for path in replacements}
    offsets = stored_page_offsets(stored, logical_pages)
    segments = [stored[left:right] for left, right in zip(offsets, offsets[1:])]
    pages = [bytearray(decode_page(segment)) for segment in segments]
    locations = file_locations(pages)
    data_start = volume.TOC_OFFSET + physical_pages * SECTOR
    next_offset = (disc_size + SECTOR - 1) // SECTOR * SECTOR
    extents, facts, changed_pages = [], [], set()
    for path, data in replacements.items():
        if path not in locations:
            raise ValueError(f'{path} is not a file of GT4.VOL')
        page_index, meta_offset = locations[path]
        page = pages[page_index]
        if page[meta_offset] != 2:
            raise ValueError(f'{path} is not a PS2ZIP file; only those are supported')
        payload = ps2zip(data)
        data_page = (next_offset - volume.VOLUME_OFFSET - data_start) // SECTOR
        _, modified, _, _ = struct.unpack_from('<IIII', page, meta_offset + 1)
        struct.pack_into('<IIII', page, meta_offset + 1, data_page, modified, len(payload), len(data))
        changed_pages.add(page_index)
        extents.append((next_offset, payload))
        facts.append({'path': path, 'original_sha256': sha256(originals[path]), 'sha256': sha256(data),
                      'bytes': len(data), 'stored_bytes': len(payload), 'disc_offset': next_offset})
        next_offset += (len(payload) + SECTOR - 1) // SECTOR * SECTOR
    for page_index in changed_pages:
        segments[page_index] = encode_page(pages[page_index], page_index == logical_pages - 1)
    table_end = 64 + 4 * (logical_pages + 1)
    new_offsets = [table_end]
    for segment in segments:
        new_offsets.append(new_offsets[-1] + len(segment))
    new_stored = bytearray(header)
    struct.pack_into('<I', new_stored, 8, new_offsets[-1])
    for index, offset in enumerate(new_offsets):
        new_stored += struct.pack('<I', offset ^ (((index + 1) * PAGE_KEY) & 0xFFFFFFFF))
    for segment in segments:
        new_stored += segment
    if len(new_stored) > physical_pages * SECTOR:
        raise ValueError(f'the rewritten catalogue ({len(new_stored)} bytes) exceeds its {physical_pages} pages')
    # The rewritten catalogue must resolve every replaced file to its new pages and contents.
    virtual_volume = next_offset - volume.VOLUME_OFFSET
    check = volume.parse_catalogue(bytes(new_stored), virtual_volume)
    served = dict(extents)
    for path, data in replacements.items():
        record = check.files[path]
        payload = served[volume.VOLUME_OFFSET + record.offset]
        if volume.decode_payload(payload[:record.stored_size], record.kind, record.size) != data:
            raise ValueError(f'{path} does not decode to its replacement through the rewritten catalogue')
    extents.insert(0, (base, bytes(new_stored)))
    return disc_size, next_offset, extents, {
        'catalogue_bytes': len(new_stored), 'catalogue_capacity': physical_pages * SECTOR,
        'changed_catalogue_pages': sorted(changed_pages), 'files': facts}


def write_overlay(path, disc_size, virtual_size, extents):
    with open(path, 'xb') as output:
        output.write(MAGIC + struct.pack('<QQII', disc_size, virtual_size, len(extents), 0))
        for offset, data in extents:
            output.write(struct.pack('<QQ', offset, len(data)))
            output.write(data)


def original_file(iso_path, path):
    with volume.verified_volume(iso_path) as stream:
        catalogue = volume.read_catalogue(stream)
        record = catalogue.files[path]
        return volume.decode_payload(volume.read_at(stream, volume.VOLUME_OFFSET + record.offset, record.stored_size,
                                                    volume.VOLUME_OFFSET + volume.VOLUME_SIZE),
                                     record.kind, record.size)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    build_command = commands.add_parser('build')
    build_command.add_argument('--iso', type=Path, required=True)
    build_command.add_argument('--output', type=Path, required=True, help='fresh folder under private/')
    build_command.add_argument('--replace', action='append', default=[], help='<volume path>=<new file>')
    build_command.add_argument('--text', action='append', default=[], help='<volume path>=<old text>=<new text>')
    arguments = parser.parse_args(argv)
    try:
        output = volume.fresh_output_directory(arguments.output, ROOT / 'private')
        replacements = {}
        for item in arguments.replace:
            path, _, source = item.partition('=')
            replacements[path] = Path(source).read_bytes()
        for item in arguments.text:
            path, old, new = item.split('=', 2)
            data = replacements.get(path) or original_file(arguments.iso, path)
            old_bytes, new_bytes = old.encode('latin-1'), new.encode('latin-1')
            if len(old_bytes) != len(new_bytes) or not data.count(old_bytes):
                raise ValueError(f'{path}: "{old}" must occur and keep its length')
            print(f'{path}: "{old}" -> "{new}" ({data.count(old_bytes)} times)')
            replacements[path] = data.replace(old_bytes, new_bytes)
        disc_size, virtual_size, extents, facts = build(arguments.iso, replacements)
        write_overlay(output / 'overlay.gt4ovl', disc_size, virtual_size, extents)
        facts.update({'disc_size': disc_size, 'virtual_size': virtual_size,
                      'overlay_sha256': sha256((output / 'overlay.gt4ovl').read_bytes())})
        (output / 'overlay.json').write_text(json.dumps(facts, indent=2) + '\n', encoding='utf-8')
        print(f"overlay: {len(extents)} extents, catalogue {facts['catalogue_bytes']} of {facts['catalogue_capacity']} "
              f"bytes, {output / 'overlay.gt4ovl'}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f'gt4-volume-overlay: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
