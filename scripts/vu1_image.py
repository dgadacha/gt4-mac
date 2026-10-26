"""Static VU1 microcode image of GT4 USA v2.00, and explicit entry lists for gt4_vu_recomp.

Slice 155. The 16 KiB VU1 code memory is one static image (docs/VU1-MICROCODE-SOURCE.md).
Its first 0x3FF0 bytes are stored XOR-encrypted in the pinned reconstructed ELF at file
offset 0x525DD0. The keystream is state = 0x32277070; for each byte the state is advanced
(state = 0x5D588B65 * state + 1 mod 2^32) and plain = enc ^ (state & 0xFF). The last 16
bytes (instructions 0x3FF0 and 0x3FF8) are not stored in the blob; they come from the
recorded snapshots, which must all agree on them. Every snapshot must equal the decrypted
blob over 0x0000-0x3FEF; a mismatch refuses the build.

Commands:
  build    decrypt the pinned ELF blob, append the snapshot tail and write a fresh image directory;
           --pinned-tail takes the tail recorded in docs/inputs/slice155-vu1-image.json instead of a
           corpus (a machine without the recorded snapshots), and then the image must equal the pin
  check    verify an image file against the pins in docs/inputs/slice155-vu1-image.json
  entries  write an explicit entry list for gt4_vu_recomp --entries (one 4-digit hex address per line)
  corpus   write one KEY_ENTRY.bin file per entry (the recorded-file layout of gt4_vu_recomp), so the
           corpus differential test covers the same entries; the keys are the donor program keys

  compare  check that the targeted table rows (key, digest, flag elision, sites) equal the full table
           rows, and print the full table's flag-elision counts (slice 157)

Entry policies (see docs/BUILD.md, slices 155 and 157). `entries` also writes LIST.json with the policy label:

  all       every 8-byte aligned address of the image (2048 entries)
  targeted  address 0, the 8-byte address after each E-bit delay slot, every branch and jump-link
            return target, every branch target, every IADDIU constant that can feed a JR/JALR
            (the donor emitter's rule), the entries of a previous table, and the block starts
            after each branch or jump delay slot
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELF_OFFSET = 0x525DD0
BLOB_BYTES = 0x3FF0
IMAGE_BYTES = 16384
CODE_MASK = IMAGE_BYTES - 1
KEY_STATE = 0x32277070
KEY_MULTIPLIER = 0x5D588B65
END_BIT = 0x40000000
IMMEDIATE_BIT = 0x80000000
PINS = ROOT / 'docs/inputs/slice155-vu1-image.json'
ELF_PIN = ROOT / 'docs/inputs/usa-v2.00-native.json'


def decrypt_blob(encrypted):
    """Returns the plain bytes; the keystream is advanced before each byte is XORed."""
    state = KEY_STATE
    plain = bytearray(len(encrypted))
    for index, byte in enumerate(encrypted):
        state = (KEY_MULTIPLIER * state + 1) & 0xFFFFFFFF
        plain[index] = byte ^ (state & 0xFF)
    return bytes(plain)


def check_snapshots(blob, snapshots):
    """Returns (tail, count). Every snapshot must match the blob and agree on the tail."""
    if not snapshots:
        raise ValueError('no VU1 snapshots to control the image')
    tails = set()
    for name, data in snapshots:
        if len(data) != IMAGE_BYTES:
            raise ValueError(f'snapshot {name} is {len(data)} bytes, not {IMAGE_BYTES}')
        if data[:BLOB_BYTES] != blob:
            raise ValueError(f'snapshot {name} differs from the decrypted blob')
        tails.add(data[BLOB_BYTES:])
    if len(tails) != 1:
        raise ValueError('snapshots disagree on the tail instructions 0x3FF0/0x3FF8')
    return tails.pop(), len(snapshots)


def build_image(elf_bytes, snapshots):
    """Builds the 16 KiB image from the ELF bytes and the snapshot list of (name, bytes)."""
    encrypted = elf_bytes[ELF_OFFSET:ELF_OFFSET + BLOB_BYTES]
    if len(encrypted) != BLOB_BYTES:
        raise ValueError('ELF is too short for the VU1 blob')
    blob = decrypt_blob(encrypted)
    tail, count = check_snapshots(blob, snapshots)
    image = blob + tail
    return image, {'blob_sha256': hashlib.sha256(blob).hexdigest(), 'tail_hex': tail.hex(),
                   'snapshots_matching': count}


def build_image_from_pins(elf_bytes, pins):
    """Builds the image with the tail of the pins (no snapshots); the whole image must then equal the pinned image."""
    encrypted = elf_bytes[ELF_OFFSET:ELF_OFFSET + BLOB_BYTES]
    if len(encrypted) != BLOB_BYTES:
        raise ValueError('ELF is too short for the VU1 blob')
    blob = decrypt_blob(encrypted)
    tail = bytes.fromhex(pins['tail_hex'])
    image = blob + tail
    if len(tail) != IMAGE_BYTES - BLOB_BYTES or hashlib.sha256(image).hexdigest() != pins['image']['sha256']:
        raise ValueError('image with the pinned tail differs from the pinned image')
    return image, {'blob_sha256': hashlib.sha256(blob).hexdigest(), 'tail_hex': tail.hex(), 'snapshots_matching': 0}


def read_snapshots(directory):
    files = sorted(Path(directory).glob('*.bin'))
    return [(path.name, path.read_bytes()) for path in files]


def word(image, at):
    return struct.unpack_from('<I', image, at & CODE_MASK)[0]


def lower_major(lower):
    return lower >> 25


def is_branch(lower):
    """Donor is_branch: includes the jump-register opcodes, excludes 0x2A and 0x2B."""
    op = lower_major(lower)
    return op in (0x20, 0x21, 0x24, 0x25) or (0x28 <= op <= 0x2F and op not in (0x2A, 0x2B))


def branch_target(lower, pc):
    """Target of a branch with the 11-bit signed offset in instruction units (donor branch_target)."""
    offset_field = (lower & 0x7FF) - (0x800 if lower & 0x400 else 0)
    return (pc + 8 + offset_field * 8) & CODE_MASK


def iaddiu_constant_target(lower):
    """Donor rule: IADDIU with base vi0 loads imm15; the value times 8 is a plausible JR target."""
    if lower_major(lower) != 0x08 or ((lower >> 11) & 15) != 0:
        return None
    imm15 = ((lower >> 10) & 0x7800) | (lower & 0x7FF)
    return (imm15 * 8) & CODE_MASK


def all_entries():
    return list(range(0, IMAGE_BYTES, 8))


def targeted_entries(image, table_entries=()):
    """Union of the rules in the module docstring, as sorted 8-byte aligned addresses."""
    entries = {0}
    entries.update(address & CODE_MASK for address in table_entries)
    for pc in range(0, IMAGE_BYTES, 8):
        lower, upper = word(image, pc), word(image, pc + 4)
        if upper & END_BIT:
            entries.add((pc + 16) & CODE_MASK)
        immediate = bool(upper & IMMEDIATE_BIT)
        if immediate:
            continue
        if is_branch(lower):
            entries.add((pc + 16) & CODE_MASK)
            if lower_major(lower) not in (0x24, 0x25):
                entries.add(branch_target(lower, pc))
        target = iaddiu_constant_target(lower)
        if target is not None:
            entries.add(target)
    return sorted(entries)


def write_entry_list(path, entries):
    text = ''.join(f'{address:04X}\n' for address in entries)
    with open(path, 'x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def compare_tables(targeted_manifest, full_manifest):
    """Checks that the targeted table is a subset of the full table with identical rows (slice157).

    Compares every field that the emitter derives per program: key, identity digest, the
    flag-elision flags, the MAC and clip site counts, the reachable size and the function name.
    Returns (checked_rows, problems). An empty problems list means the rows agree.
    """
    full = {program['entry']: program for program in full_manifest['programs']}
    problems = []
    fields = ('key', 'digest_sha256', 'image_flags_used', 'image_status_used', 'mac_mode', 'mac_writers', 'mac_sites',
              'mac_reader_sites', 'clip_writers', 'clip_sites', 'clip_reader_sites', 'fallback_sites', 'upper_nop_sites',
              'budget_heads', 'reachable_instructions', 'exit_pcs', 'status', 'function')
    for program in targeted_manifest['programs']:
        other = full.get(program['entry'])
        if other is None:
            problems.append(f"entry {program['entry']} missing from the full table")
            continue
        for field in fields:
            if program[field] != other[field]:
                problems.append(f"entry {program['entry']} field {field}: {program[field]!r} != {other[field]!r}")
    return len(targeted_manifest['programs']), problems


def elision_counts(manifest):
    """Per-program flag-elision facts of a table manifest, for the summary line of the slice157 record."""
    programs = manifest['programs']
    return {
        'programs': len(programs),
        'emitted': sum(1 for p in programs if p['status'] == 'emitted'),
        'refused': sum(1 for p in programs if p['status'] != 'emitted'),
        'image_flags_used': sum(1 for p in programs if p['image_flags_used']),
        'image_status_used': sum(1 for p in programs if p['image_status_used']),
        'interpreter_exit_sites': sum(len(p['exit_pcs']) for p in programs),
        'mac_mode': sorted({p['mac_mode'] for p in programs}),
    }


FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
U64 = 0xFFFFFFFFFFFFFFFF


def donor_reachable(image, entry):
    """Port of the donor ps2::vu::reachable (sorted PCs reached from entry, delay slots included)."""
    seen = set()
    work = [entry & CODE_MASK]
    out = []
    while work:
        pc = work.pop()
        stop_after = -1
        for _ in range(4096):
            if pc in seen:
                break
            seen.add(pc)
            out.append(pc)
            if stop_after == 0:
                break
            if stop_after > 0:
                stop_after -= 1
            lower, upper = word(image, pc), word(image, pc + 4)
            if upper & END_BIT:
                stop_after = 0
            if not (upper & IMMEDIATE_BIT) and is_branch(lower):
                if lower_major(lower) not in (0x24, 0x25):
                    work.append(branch_target(lower, pc))
                if lower_major(lower) in (0x21, 0x25):
                    work.append((pc + 16) & CODE_MASK)
                if lower_major(lower) in (0x20, 0x21, 0x24, 0x25):
                    stop_after = 0
            pc = (pc + 8) & CODE_MASK
    return sorted(out)


def donor_program_key(image, pcs, entry):
    """Port of the donor ps2::vu::program_key: FNV-1a over entry, then pc, lower, upper words."""
    key = (FNV_OFFSET ^ entry) & U64

    def mix(value):
        nonlocal key
        for shift in (0, 8, 16, 24):
            key ^= (value >> shift) & 0xFF
            key = (key * FNV_PRIME) & U64

    for pc in pcs:
        mix(pc)
        mix(word(image, pc))
        mix(word(image, pc + 4))
    return key


def program_key_of(image, entry):
    return donor_program_key(image, donor_reachable(image, entry), entry)


def write_corpus(image, entries, directory):
    """Writes KEY16_ENTRY4.bin files; the emitter re-derives every key and refuses a mismatch."""
    for entry in entries:
        name = f'{program_key_of(image, entry):016X}_{entry:04X}.bin'
        with open(Path(directory) / name, 'xb') as handle:
            handle.write(image)
    return len(entries)


def read_table_entries(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    return [program['entry'] for program in manifest['programs']]


def fresh_directory(path):
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f'output must be a fresh or empty directory: {path}')
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_build(arguments):
    elf_path = Path(arguments.elf)
    elf_bytes = elf_path.read_bytes()
    elf_sha = hashlib.sha256(elf_bytes).hexdigest()
    pinned = json.loads(ELF_PIN.read_text(encoding='utf-8'))['native_elf_sha256']
    if elf_sha != pinned:
        raise ValueError(f'ELF differs from the pin in {ELF_PIN.name}: {elf_sha}')
    if arguments.pinned_tail:
        image, facts = build_image_from_pins(elf_bytes, json.loads(PINS.read_text(encoding='utf-8')))
        control = f'no snapshots: the tail of {PINS.name}, and the image equals the pinned image'
    else:
        image, facts = build_image(elf_bytes, read_snapshots(arguments.corpus))
        control = 'every snapshot equals the blob over 0x0000-0x3FEF and all snapshots agree on the tail'
    out = fresh_directory(arguments.out)
    (out / 'vu1_image.bin').write_bytes(image)
    receipt = {'elf_sha256': elf_sha, 'elf_offset': ELF_OFFSET, 'blob_bytes': BLOB_BYTES,
               'image_bytes': IMAGE_BYTES, 'key_state': KEY_STATE, 'key_multiplier': KEY_MULTIPLIER,
               'image_sha256': hashlib.sha256(image).hexdigest(), 'corpus_snapshots': facts['snapshots_matching'],
               'corpus_control': control, 'tail_hex': facts['tail_hex'], 'blob_sha256': facts['blob_sha256']}
    (out / 'vu1_image.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f"vu1-image: {IMAGE_BYTES} bytes sha256={receipt['image_sha256']} snapshots={facts['snapshots_matching']}")
    return 0


def cmd_check(arguments):
    pins = json.loads(PINS.read_text(encoding='utf-8'))
    actual = sha256_file(arguments.image)
    if Path(arguments.image).stat().st_size != IMAGE_BYTES or actual != pins['image']['sha256']:
        raise ValueError(f'image differs from the pin: {actual}')
    print(f'vu1-image: pin verified {actual}')
    return 0


def read_entry_file(path):
    entries = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            entries.append(int(line, 16))
    return entries


def cmd_corpus(arguments):
    image = Path(arguments.image).read_bytes()
    if len(image) != IMAGE_BYTES:
        raise ValueError('image must be 16384 bytes')
    entries = read_entry_file(arguments.entries)
    out = fresh_directory(arguments.out)
    count = write_corpus(image, entries, out)
    print(f'vu1-corpus: {count} KEY_ENTRY.bin files written to {out}')
    return 0


def cmd_entries(arguments):
    image = Path(arguments.image).read_bytes()
    if len(image) != IMAGE_BYTES:
        raise ValueError('image must be 16384 bytes')
    if arguments.policy == 'all':
        entries = all_entries()
    else:
        table = read_table_entries(arguments.table_manifest) if arguments.table_manifest else []
        entries = targeted_entries(image, table)
    list_sha = write_entry_list(arguments.out, entries)
    # Sidecar with the policy label; gt4_vu_recomp --entry-policy copies the same label into its manifest.
    sidecar = {'policy': arguments.policy, 'entries': len(entries), 'entry_list_sha256': list_sha,
               'image_sha256': hashlib.sha256(image).hexdigest(),
               'table_manifest': arguments.table_manifest or None,
               'rules': 'every 8-byte aligned address (2048)' if arguments.policy == 'all' else
               'slice155 targeted rules (docs/BUILD.md slice155) plus the entries of --table-manifest'}
    Path(str(arguments.out) + '.json').write_text(json.dumps(sidecar, indent=2) + '\n', encoding='utf-8')
    print(f'vu1-entries: {len(entries)} {arguments.policy} entries, sha256={list_sha}')
    return 0


def cmd_compare(arguments):
    targeted = json.loads(Path(arguments.targeted).read_text(encoding='utf-8'))
    full = json.loads(Path(arguments.full).read_text(encoding='utf-8'))
    checked, problems = compare_tables(targeted, full)
    counts = elision_counts(full)
    print(f"vu1-compare: {checked} targeted rows checked against {len(full['programs'])} full rows, {len(problems)} differences")
    print(f"vu1-compare: full table {json.dumps(counts, sort_keys=True)}")
    for problem in problems[:20]:
        print(f'FAIL: {problem}', file=sys.stderr)
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--elf', required=True)
    tail = build.add_mutually_exclusive_group(required=True)
    tail.add_argument('--corpus', help='directory of recorded 16 KiB snapshots (read only)')
    tail.add_argument('--pinned-tail', action='store_true',
                      help='no snapshots: take the tail from docs/inputs/slice155-vu1-image.json and require the pinned image')
    build.add_argument('--out', required=True, help='fresh output directory')
    build.set_defaults(run=cmd_build)
    check = commands.add_parser('check')
    check.add_argument('--image', required=True)
    check.set_defaults(run=cmd_check)
    entries = commands.add_parser('entries')
    entries.add_argument('--image', required=True)
    entries.add_argument('--policy', choices=('all', 'targeted'), required=True)
    entries.add_argument('--table-manifest', help='manifest.json of a previous table whose entries are included')
    entries.add_argument('--out', required=True, help='new entry list file (must not exist)')
    entries.set_defaults(run=cmd_entries)
    compare = commands.add_parser('compare')
    compare.add_argument('--targeted', required=True, help='manifest.json of the targeted table')
    compare.add_argument('--full', required=True, help='manifest.json of the full table (must contain the targeted rows)')
    compare.set_defaults(run=cmd_compare)
    corpus = commands.add_parser('corpus')
    corpus.add_argument('--image', required=True)
    corpus.add_argument('--entries', required=True, help='entry list written by the entries command')
    corpus.add_argument('--out', required=True, help='fresh output directory')
    corpus.set_defaults(run=cmd_corpus)
    arguments = parser.parse_args(argv)
    try:
        return arguments.run(arguments)
    except (OSError, ValueError, KeyError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
