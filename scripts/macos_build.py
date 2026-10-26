"""Build GT4Recomp on macOS (Apple silicon) from your own disc image: every private input, then the game.

docs/BUILD-MACOS.md explains the recipe. It is the Windows release 1.2.x recipe (docs/BUILD.md, slice262), with
every input regenerated on this Mac from the disc and the frozen donor and checked against the same docs/inputs pins.
The one exception is the EE library, which is compiled here for arm64: its sources must equal the pinned source
inventory of the release library (docs/inputs/slice217-ee-libraries.json), and a receipt beside the library
(macos-library.json) ties the library bytes to those sources. The port is the slice191 derivation, whose four files
are pinned: the release port's main.cpp (slice200) is a hand edit for the Windows installer and cannot be derived.

Stages, in order. A stage whose output exists is checked against its pins instead of being produced again:
  ee       CORE.GT4 and the reconstructed ELF (private/fingerprint-check, private/reconstructed), the aspect ELF patch,
           the donor translator built here, the 1,105 accepted seeds and libps2game.a
           (private/macos-ee-aspect-producer)
  vu       the VU1 image and its 2,048-program table, the VU0 image and its 14-program table
  runtime  the slice262 runtime capsule, the slice200 memory card capsule and the slice262 license guard capsule
  port     the slice191 GS stream port (gpu.cpp, gpu.hpp, gs.cpp, main.cpp)
  shaders  the nine SPIR-V compute shaders (tools/wgsl_spirv, naga 30.0.0)
  game     CMake configure and build of gt4vulkan in private/macos-build

Usage (from the checkout root, after `python3 -m venv private/tooling-venv` and
`private/tooling-venv/bin/python -m pip install -r scripts/requirements.txt`):
  private/tooling-venv/bin/python scripts/macos_build.py               every stage
  private/tooling-venv/bin/python scripts/macos_build.py --stage game   one stage (repeatable)
  --iso PATH  the disc image (default: "Gran Turismo 4 (USA) (v2.00).iso" at the checkout root)
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import aspect_elf_patch  # noqa: E402
import ee_entries  # noqa: E402
import ee_producer  # noqa: E402

PYTHON = Path(sys.executable)
DONOR = ROOT / 'private/references/ps2-web-recomp'
DONOR_URL = 'https://github.com/snuri00/ps2-web-recomp'
ISO_NAME = 'Gran Turismo 4 (USA) (v2.00).iso'
EE_PRODUCER = ROOT / 'private/macos-ee-aspect-producer'
EE_RECEIPT = 'macos-library.json'
TOOLS = ROOT / 'private/macos-tools'
SHADER_COMPILER = ROOT / 'private/macos-shader-compiler'
BUILD = ROOT / 'private/macos-build'
RECONSTRUCTED_ELF = ROOT / 'private/reconstructed/SCUS_973.28.elf'
EXTRACTED_CORE = ROOT / 'private/fingerprint-check/CORE.GT4'
VU1_IMAGE = ROOT / 'private/slice155-vu1-image'
VU1_ENTRIES = ROOT / 'private/slice157-vu1-all-entries/entries-all.txt'
VU1_TABLE = ROOT / 'private/slice157-vu1-all-gen'
VU0_IMAGE = ROOT / 'private/slice160-vu0-image'
VU0_TABLE = ROOT / 'private/slice160-vu0-gen-r3'
RUNTIME_CAPSULE = ROOT / 'private/slice262-frame-cost-runtime'
MEMCARD_CAPSULE = ROOT / 'private/slice200-memcard-runtime'
GUARD_CAPSULE = ROOT / 'private/slice262-license-guard-runtime'
PORT = ROOT / 'private/slice191-gs-stream-port'
SHADERS = ROOT / 'private/slice153-pacing-shaders'
STAGES = ('ee', 'vu', 'runtime', 'port', 'shaders', 'game')


def pins(name):
    return json.loads((ROOT / 'docs/inputs' / name).read_text(encoding='utf-8'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run(arguments, **options):
    printable = ' '.join(str(argument) for argument in arguments)
    print(f'  $ {printable}', flush=True)
    subprocess.run([str(argument) for argument in arguments], check=True, **options)


def step(message):
    print(f'[macos-build] {message}', flush=True)


def files_of(directory):
    """The file names of a capsule directory, without the .DS_Store that Finder may leave."""
    return sorted(path.name for path in Path(directory).iterdir() if path.name != '.DS_Store')


def require_files(directory, expected):
    """Every expected file has its pinned SHA-256 and nothing else is in the directory."""
    directory = Path(directory)
    if files_of(directory) != sorted(expected):
        raise ValueError(f'{directory.relative_to(ROOT)} holds {files_of(directory)}, expected {sorted(expected)}')
    for name, digest in expected.items():
        if sha256(directory / name) != digest:
            raise ValueError(f'{directory.relative_to(ROOT)}/{name} differs from its pin')


def require_digest(path, digest, pin):
    if sha256(path) != digest:
        raise ValueError(f'{Path(path).relative_to(ROOT)} differs from the pin in {pin}')


def check_host():
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise ValueError('this recipe builds for macOS on Apple silicon (arm64)')
    commit = ee_producer.DONOR_COMMIT
    if not (DONOR / '.git').exists():
        raise ValueError(f'missing donor checkout; clone it with CRLF line endings (the pins hash Windows bytes):\n'
                         f'  git clone -c core.autocrlf=true {DONOR_URL} {DONOR.relative_to(ROOT)}\n'
                         f'  git -C {DONOR.relative_to(ROOT)} checkout {commit}')
    for tool in ('cmake', 'ninja', 'cargo', 'clang++'):
        if not shutil.which(tool):
            raise ValueError(f'{tool} not found; see docs/BUILD-MACOS.md for the Homebrew and Rust prerequisites')


# ---- ee -------------------------------------------------------------------------------------------------------------

def copy_checked(source, destination, digest, pin):
    """Copies a verified input to the path the other scripts read, or checks the copy already there."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(source, destination)
    require_digest(destination, digest, pin)


def stage_ee(iso):
    out = EE_PRODUCER
    library = out / 'game-build/libps2game.a'
    receipt_path = out / EE_RECEIPT
    profile = pins('slice217-ee-libraries.json')['profiles']['aspect']
    native = pins('usa-v2.00-native.json')
    core_pin = pins('usa-v2.00.json')['files']['/CORE.GT4;1']
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['source_inventory'] != profile['source_inventory'] or sha256(library) != receipt['library']['sha256']:
            raise ValueError(f'{out.relative_to(ROOT)} differs from its receipt; delete the folder and build it again')
        step(f'ee: {out.relative_to(ROOT)} verified (sources = release inventory {profile["source_inventory"]["inventory_sha256"][:8]})')
    else:
        if not (out / 'producer.json').exists():
            if out.exists():
                raise ValueError(f'{out.relative_to(ROOT)} exists without producer.json (an interrupted start); '
                                 'delete it and run again')
            if not iso.is_file():
                raise ValueError(f'missing disc image: {iso} (see docs/BUILD-MACOS.md)')
            step(f'ee: checking the disc image and reconstructing the ELF ({iso.name})')
            ee_producer.prepare(ROOT, out, iso=iso)
        _, metadata, _ = ee_producer.existing_producer(out)
        original = (out / 'SCUS_973.28.elf').read_bytes()
        patched_path = out / 'SCUS_973.28.aspect.elf'
        if not patched_path.exists():
            patched_path.write_bytes(aspect_elf_patch.patch_elf(original))
        patched_digest = sha256(patched_path)
        if patched_digest != profile['patched_elf_sha256']:
            raise ValueError('the aspect ELF differs from docs/inputs/slice217-ee-libraries.json')
        seed_file, seeds, seed_pin = ee_entries.seed_set_pin(aspect_elf_patch.SEED_SET)
        ee_entries.check_seeds_executable(patched_path.read_bytes(), seeds)
        entries = out / f'entries-{aspect_elf_patch.SEED_SET}.txt'
        if not entries.exists():
            entries.write_bytes(seed_file.read_bytes())
        ee_producer.verify_identity(entries, {key: seed_pin[key] for key in ('size_bytes', 'sha256')})

        step('ee: building the donor translator (eerecomp)')
        run(['cmake', '-S', ROOT / 'tools/ee_producer', '-B', out / 'tool-build', '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=Release', f'-DGT4_DONOR={DONOR}', '-DGT4_BUILD_TRANSLATOR=ON'],
            stdout=subprocess.DEVNULL)
        run(['cmake', '--build', out / 'tool-build', '--target', 'eerecomp'])
        translator = out / 'tool-build/eerecomp'

        generated = out / 'generated'
        if generated.exists():
            shutil.rmtree(generated)  # derived data of this producer only; regenerated from the verified ELF
        step('ee: translating the aspect ELF with the accepted seeds')
        arguments = [translator, patched_path, '--out', generated, '--stats', '--entries', entries]
        log = subprocess.run([str(argument) for argument in arguments], capture_output=True, text=True, check=True)
        (out / 'generation-aspect.log').write_text(log.stdout + log.stderr, encoding='utf-8')
        stats = ee_entries.parse_stats(log.stdout + log.stderr)
        ee_entries.validate_stats(stats, seed_pin)
        records = ee_producer.generated_inventory(generated)
        summary = ee_producer.inventory_summary(records)
        if summary != profile['source_inventory']:
            raise ValueError(f'generated sources differ from the release inventory: {summary}')
        step(f'ee: {summary["file_count"]} generated files equal the release sources ({summary["inventory_sha256"][:8]})')

        step('ee: compiling libps2game.a (about 330 units; a few minutes)')
        run(['cmake', '-S', ROOT / 'tools/ee_producer', '-B', out / 'game-build', '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=Release', f'-DGT4_DONOR={DONOR}', f'-DGT4_GENERATED={generated}',
             '-DGT4_BUILD_TRANSLATOR=OFF'], stdout=subprocess.DEVNULL)
        run(['cmake', '--build', out / 'game-build', '--target', 'ps2game'])
        toolchain = dict(line.partition('=')[::2] for line in
                         (out / 'game-build/toolchain.txt').read_text(encoding='utf-8').splitlines())
        receipt = {'schema_version': 1, 'profile': 'aspect', 'platform': 'macOS arm64',
                   'donor_commit': metadata['donor_commit'], 'elf_sha256': sha256(out / 'SCUS_973.28.elf'),
                   'patched_elf_sha256': patched_digest, 'seed_set': aspect_elf_patch.SEED_SET,
                   'seed_sha256': seed_pin['sha256'], 'translator': ee_producer.identity(translator),
                   'translator_stats': stats, 'source_inventory': summary,
                   'source_pin': 'docs/inputs/slice217-ee-libraries.json profiles.aspect.source_inventory',
                   'library': {'path': library.relative_to(ROOT).as_posix(), **ee_producer.identity(library)},
                   'compiler': {key: toolchain.get(key, '') for key in
                                ('compiler', 'compiler_id', 'compiler_version', 'build_type', 'flags', 'release_flags')},
                   'qualification': 'Sources identical to the release library; arm64 library compiled on this Mac'}
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        step(f'ee: library recorded in {receipt_path.relative_to(ROOT)}')
    copy_checked(out / 'CORE.GT4', EXTRACTED_CORE, core_pin['sha256'], 'usa-v2.00.json')
    copy_checked(out / 'SCUS_973.28.elf', RECONSTRUCTED_ELF, native['native_elf_sha256'], 'usa-v2.00-native.json')


# ---- vu -------------------------------------------------------------------------------------------------------------

def vu_recomp_tool():
    """gt4_vu_recomp (tools/vu_recomp), compiled here when missing or older than its sources."""
    tool = TOOLS / 'gt4_vu_recomp'
    sources = [ROOT / 'tools/vu_recomp/src' / name for name in ('vurecomp_main.cpp', 'vurecomp.cpp', 'sha256.cpp')]
    newest = max(path.stat().st_mtime for path in sources + list((ROOT / 'tools/vu_recomp/src').glob('*.hpp')))
    if not tool.exists() or tool.stat().st_mtime < newest:
        TOOLS.mkdir(parents=True, exist_ok=True)
        step('vu: compiling gt4_vu_recomp')
        run(['clang++', '-std=c++20', '-O2', '-DNDEBUG', '-ffp-contract=off', '-fno-strict-aliasing',
             f'-I{ROOT / "tools/vu_recomp/src"}', f'-I{DONOR / "runtime/include"}', f'-I{DONOR / "runtime/src"}',
             *sources, '-o', tool])
    return tool


def check_table(directory, source_name, source_digest, manifest_digest, pin):
    require_digest(directory / source_name, source_digest, pin)
    require_digest(directory / 'manifest.json', manifest_digest, pin)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    for part in manifest.get('generated_parts', []):
        require_digest(directory / part['file'], part['sha256'], f'{directory.name}/manifest.json')


def stage_vu():
    release = pins('slice262-pcsx2.json')
    vu1, vu0 = release['vu1_aot'], release['vu0_aot']
    if not VU1_IMAGE.exists():
        run([PYTHON, ROOT / 'scripts/vu1_image.py', 'build', '--elf', RECONSTRUCTED_ELF, '--pinned-tail',
             '--out', VU1_IMAGE])
    run([PYTHON, ROOT / 'scripts/vu1_image.py', 'check', '--image', VU1_IMAGE / 'vu1_image.bin'])
    if not VU1_ENTRIES.exists():
        VU1_ENTRIES.parent.mkdir(parents=True, exist_ok=True)
        run([PYTHON, ROOT / 'scripts/vu1_image.py', 'entries', '--image', VU1_IMAGE / 'vu1_image.bin', '--policy', 'all',
             '--out', VU1_ENTRIES])
    require_digest(VU1_ENTRIES, vu1['entry_list_sha256'], 'slice262-pcsx2.json vu1_aot')
    if not VU1_TABLE.exists():
        run([vu_recomp_tool(), '--programs-per-file', '16', '--entry-policy', 'all', '--image',
             VU1_IMAGE / 'vu1_image.bin', '--entries', VU1_ENTRIES, VU1_TABLE])
    check_table(VU1_TABLE, 'vu1_generated.cpp', vu1['generated_source_sha256'], vu1['generated_manifest_sha256'],
                'slice262-pcsx2.json vu1_aot')
    step(f'vu: VU1 table verified ({vu1["programs"]} programs)')
    if not VU0_IMAGE.exists():
        run([PYTHON, ROOT / 'scripts/vu0_image.py', 'build', '--elf', RECONSTRUCTED_ELF, '--out', VU0_IMAGE])
    entries = VU0_IMAGE / 'entries-vcallms.txt'
    if not entries.exists():
        run([PYTHON, ROOT / 'scripts/vu0_image.py', 'entries', '--image', VU0_IMAGE / 'vu0_image.bin', '--out', entries])
    run([PYTHON, ROOT / 'scripts/vu0_image.py', 'check', '--image', VU0_IMAGE / 'vu0_image.bin'])
    require_digest(entries, vu0['entry_list_sha256'], 'slice262-pcsx2.json vu0_aot')
    if not VU0_TABLE.exists():
        run([vu_recomp_tool(), '--unit', '0', '--namespace', 'gt4::vugen::vu0', '--entry-policy', 'vcallms',
             '--image', VU0_IMAGE / 'vu0_image.bin', '--entries', entries, VU0_TABLE])
    check_table(VU0_TABLE, 'vu0_generated.cpp', vu0['table_sha256'], vu0['manifest_sha256'],
                'slice262-pcsx2.json vu0_aot')
    step(f'vu: VU0 table verified ({vu0["programs"]} programs)')


# ---- runtime, port, shaders -----------------------------------------------------------------------------------------

def stage_runtime():
    capsule = pins('slice262-frame-cost-runtime.json')
    if not RUNTIME_CAPSULE.exists():
        run([PYTHON, ROOT / 'scripts/prepare_perf_runtime.py', RUNTIME_CAPSULE, '--assets-root', ROOT, '--mtvu',
             '--gs-stream', '--frame-cost'])
    require_files(RUNTIME_CAPSULE, {**capsule['source_sha256'], 'runtime.json': capsule['receipt_sha256']})
    step('runtime: slice262 frame-cost capsule verified')
    if not MEMCARD_CAPSULE.exists():
        run([PYTHON, ROOT / 'scripts/prepare_memcard_flush.py', MEMCARD_CAPSULE, '--assets-root', ROOT])
    require_digest(MEMCARD_CAPSULE / 'sio2.cpp', pins('slice262-pcsx2.json')['memcard_capsule_sha256']['sio2.cpp'],
                   'slice262-pcsx2.json memcard_capsule_sha256')
    step('runtime: slice200 memory card capsule verified')
    guard = pins('slice262-license-guard-runtime.json')
    if not GUARD_CAPSULE.exists():
        run([PYTHON, ROOT / 'scripts/prepare_license_guard.py', GUARD_CAPSULE, '--assets-root', ROOT,
             '--display-aspect', '--frame-counters'])
    expected = dict(guard['source_sha256'])
    expected['runtime.json'] = sha256(GUARD_CAPSULE / 'runtime.json')  # CMake checks the sources, not the receipt
    require_files(GUARD_CAPSULE, expected)
    step('runtime: slice262 license guard capsule verified')


def stage_port():
    if not PORT.exists():
        run([PYTHON, ROOT / 'scripts/prepare_external_vulkan.py', PORT, '--assets-root', ROOT, '--gs-stream-hooks'])
    require_files(PORT, pins('slice191-gs-stream-runtime.json')['inputs']['PORT'])
    step('port: slice191 GS stream port verified')


def stage_shaders():
    expected = pins('slice262-frame-cost-runtime.json')['inputs']['SHADERS']
    if not SHADERS.exists():
        run(['cargo', 'build', '--locked', '--release', '--manifest-path', ROOT / 'tools/wgsl_spirv/Cargo.toml',
             '--target-dir', SHADER_COMPILER])
        run([SHADER_COMPILER / 'release/gt4-wgsl-spirv', DONOR / 'runtime/src/gs/gpu/gs.wgsl', SHADERS])
    require_files(SHADERS, expected)
    step('shaders: nine SPIR-V shaders verified')


# ---- game -----------------------------------------------------------------------------------------------------------

def stage_game():
    step('game: configuring private/macos-build')
    run(['cmake', '-S', ROOT, '-B', BUILD, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DGT4_EE_PROFILE=aspect',
         f'-DGT4_ASSETS_ROOT={ROOT}', f'-DGT4_PYTHON={PYTHON}', f'-DGT4_MACOS_EE_PRODUCER={EE_PRODUCER}',
         f'-DGT4_PERF_RUNTIME_SOURCE={RUNTIME_CAPSULE}', f'-DGT4_PORT_DIR={PORT}', f'-DGT4_SHADER_DIR={SHADERS}',
         f'-DGT4_VU1_GENERATED_DIR={VU1_TABLE}', f'-DGT4_VU0_GENERATED_DIR={VU0_TABLE}',
         f'-DGT4_VU0_IMAGE_FILE={VU0_IMAGE / "vu0_image.bin"}', f'-DGT4_MEMCARD_RUNTIME_SOURCE={MEMCARD_CAPSULE}',
         f'-DGT4_LICENSE_GUARD_SOURCE={GUARD_CAPSULE}', '-DGT4_RELEASE_DISTRIBUTION=ON'])
    step('game: building gt4vulkan')
    run(['cmake', '--build', BUILD, '--target', 'gt4vulkan'])
    step(f'game: {(BUILD / "gt4vulkan").relative_to(ROOT)} is ready; start it with scripts/macos_play.py')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--stage', action='append', choices=STAGES, help='run only this stage (repeatable)')
    parser.add_argument('--iso', type=Path, default=ROOT / ISO_NAME, help='disc image (Gran Turismo 4 USA v2.00)')
    arguments = parser.parse_args(argv)
    stages = arguments.stage or list(STAGES)
    try:
        check_host()
        for stage in STAGES:
            if stage not in stages:
                continue
            if stage == 'ee':
                stage_ee(arguments.iso.resolve())
            elif stage == 'vu':
                stage_vu()
            elif stage == 'runtime':
                stage_runtime()
            elif stage == 'port':
                stage_port()
            elif stage == 'shaders':
                stage_shaders()
            else:
                stage_game()
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f'macos-build: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
