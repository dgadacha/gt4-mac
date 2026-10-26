"""Start GT4Recomp on macOS (Apple silicon) after scripts/macos_build.py, in a window or in fullscreen.

The game runs from private/macos-play: the guest executable SCUS_973.28 (a copy of the verified reconstructed ELF, the
name the game expects) and the memory card card.ps2, which keeps the saves between sessions. A copy of the card is
kept in private/macos-play/backups before every session (the ten newest stay). The environment is the Windows
launcher's for the built-in renderer: 16:9 at boot, 480p in races, the aspect ratio of the window, FIFO presentation.

  private/tooling-venv/bin/python scripts/macos_play.py                   play in a window
  private/tooling-venv/bin/python scripts/macos_play.py --fullscreen      play in fullscreen (also Cmd+F, F11, Alt+Enter)
  private/tooling-venv/bin/python scripts/macos_play.py --mute            no sound (the device plays silence)

In-game Graphics menu (docs/BUILD-MACOS.md): when private/macos-graphics-menu/overlay.gt4ovl exists (built by
scripts/gt4_graphics_menu.py), the game reads its option files through it (GT4_DISC_OVERLAY) and Options > Screen gets
the Display Mode row; --no-menu-overlay starts without it.

PCSX2 GS renderer (docs/BUILD-MACOS.md, section "GS process"): --renderer pcsx2 draws the picture with gt4-gs, the
macOS build of the PCSX2 GS process, at a higher internal resolution. Its settings are private/macos-play/gs/gt4-gs.ini
(created on first use, internal resolution 3x); --upscale N (1 to 12) sets the internal resolution multiplier,
--hdr on|off the HDR output on an EDR display and --metalfx on|off the MetalFX upscaling. The game's Options > Screen
page changes the same settings while playing.

  private/tooling-venv/bin/python scripts/macos_play.py --renderer pcsx2 --upscale 6 --hdr on

A PNG at private/macos-play/gt4-icon.png (your own, the repository ships no game artwork) becomes the game's icon in the
Dock while it runs (GT4_WINDOW_ICON).

Keyboard (docs/CONTROLS.md): W or Enter accelerate and confirm, S brake, Space handbrake, A/D or the arrows steer and
move, Backspace or Esc go back, Shift nitro, R/F shift up/down, Q look back, C or Tab camera, P start or pause. Any
gamepad that SDL3 knows works (Xbox, DualShock 4, DualSense, Switch Pro). Close the window or press Cmd+Q to quit.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / 'private/macos-build/gt4vulkan'
ELF = ROOT / 'private/reconstructed/SCUS_973.28.elf'
ISO_NAME = 'Gran Turismo 4 (USA) (v2.00).iso'
PLAY = ROOT / 'private/macos-play'
MENU_OVERLAY = ROOT / 'private/macos-graphics-menu/overlay.gt4ovl'
GS_PROCESS = ROOT / 'private/tooling/gt4gs-build/pcsx2-gt4gs/gt4-gs'
GAME_ICON = PLAY / 'gt4-icon.png'
GS_FOLDER = PLAY / 'gs'
BACKUPS_KEPT = 10


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare(card):
    """The run folder: the guest executable (verified copy) and a backup of the card."""
    if not GAME.exists():
        raise ValueError('missing private/macos-build/gt4vulkan; run scripts/macos_build.py first')
    pinned = json.loads((ROOT / 'docs/inputs/usa-v2.00-native.json').read_text(encoding='utf-8'))['native_elf_sha256']
    PLAY.mkdir(parents=True, exist_ok=True)
    guest = PLAY / 'SCUS_973.28'
    if not guest.exists() or sha256(guest) != pinned:
        if not ELF.exists() or sha256(ELF) != pinned:
            raise ValueError('missing or changed private/reconstructed/SCUS_973.28.elf; run scripts/macos_build.py')
        shutil.copyfile(ELF, guest)
    if card.exists():
        backups = PLAY / 'backups'
        backups.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copyfile(card, backups / f'{card.stem}-{stamp}.ps2')
        for old in sorted(backups.glob(f'{card.stem}-*.ps2'))[:-BACKUPS_KEPT]:
            old.unlink()
    return guest


def with_ini_value(text, section, key, value):
    """INI text with `key = value` in [section]: the key's line replaced, else added after the section's last line."""
    lines = text.splitlines()
    inside, insert_at = False, None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if inside:
                break
            inside = stripped[1:-1].strip() == section
            insert_at = index + 1 if inside else insert_at
        elif inside and '=' in stripped and stripped.split('=', 1)[0].strip() == key:
            lines[index] = f'{key} = {value}'
            return '\n'.join(lines) + '\n'
        elif inside and stripped:
            insert_at = index + 1
    if insert_at is None:
        lines += ['', f'[{section}]']
        insert_at = len(lines)
    lines.insert(insert_at, f'{key} = {value}')
    return '\n'.join(lines) + '\n'


def gs_config(upscale, hdr=None, metalfx=None):
    """The GS process settings (docs/GS-SETTINGS.md): created on first use, then only the options given change."""
    GS_FOLDER.mkdir(parents=True, exist_ok=True)
    config = GS_FOLDER / 'gt4-gs.ini'
    text = config.read_text(encoding='utf-8') if config.exists() else (
        f'[EmuCore/GS]\nupscale_multiplier = 3\n\n[GT4GS]\nDataRoot = {GS_FOLDER / "data"}\n')
    if upscale:
        text = with_ini_value(text, 'EmuCore/GS', 'upscale_multiplier', str(upscale))
    for key, value in (('HDR', hdr), ('MetalFX', metalfx)):
        if value:
            text = with_ini_value(text, 'GT4GS', key, 'true' if value == 'on' else 'false')
    config.write_text(text, encoding='utf-8')
    return config


def environment(arguments):
    """The launcher's game environment (launcher/crates/gt4l-app launch.rs) for the built-in renderer."""
    values = {key: value for key, value in os.environ.items()
              if not (key.startswith('PS2_') or (key.startswith('GT4_') and key != 'GT4_ASPECT_FOV_EXTRA'))}
    values.update({'PS2_SCALE': '1', 'PS2_GS': 'gpu', 'GT4_FORCE_WIDESCREEN': '1', 'GT4_FORCE_480P': '1',
                   'GT4_DISPLAY_ASPECT': 'auto', 'GT4_PRESENT_MODE': 'fifo', 'GT4_PERF': '1',
                   'GT4_FULLSCREEN': '1' if arguments.fullscreen else '0'})
    if arguments.mute:
        values['GT4_MUTE'] = '1'
    if arguments.controls:
        values['GT4_CONTROLS_FILE'] = str(arguments.controls.resolve())
    if not arguments.no_menu_overlay and arguments.menu_overlay.is_file():
        values['GT4_DISC_OVERLAY'] = str(arguments.menu_overlay.resolve())
    if GAME_ICON.is_file():
        values['GT4_WINDOW_ICON'] = str(GAME_ICON)
    if arguments.renderer == 'pcsx2':
        values['GT4_RENDERER'] = 'pcsx2'
        values['GT4_GS_PROCESS'] = str(arguments.gs_process.resolve())
        values['GT4_GS_CONFIG'] = str(gs_config(arguments.upscale, arguments.hdr, arguments.metalfx))
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fullscreen', action='store_true', help='start in fullscreen')
    parser.add_argument('--mute', action='store_true', help='no sound (GT4_MUTE=1)')
    parser.add_argument('--iso', type=Path, default=ROOT / ISO_NAME, help='disc image (Gran Turismo 4 USA v2.00)')
    parser.add_argument('--card', type=Path, default=PLAY / 'card.ps2', help='memory card file (created when missing)')
    parser.add_argument('--controls', type=Path, help='controls file (GT4_CONTROLS_FILE, docs/CONTROLS.md)')
    parser.add_argument('--frames', type=int, default=0, help='stop after this many frames (0: play until closed)')
    parser.add_argument('--log', type=Path, default=PLAY / 'game.log', help='game log file')
    parser.add_argument('--menu-overlay', type=Path, default=MENU_OVERLAY,
                        help='in-game Graphics menu overlay, used when the file exists (GT4_DISC_OVERLAY)')
    parser.add_argument('--no-menu-overlay', action='store_true', help='start without the in-game Graphics menu')
    parser.add_argument('--renderer', choices=('donor', 'pcsx2'), default='donor',
                        help='donor: the built-in renderer (default); pcsx2: the GS process gt4-gs (GT4_RENDERER)')
    parser.add_argument('--gs-process', type=Path, default=GS_PROCESS, help='gt4-gs executable (with --renderer pcsx2)')
    parser.add_argument('--upscale', type=int, choices=range(1, 13), metavar='N',
                        help='internal resolution multiplier of gt4-gs, 1 to 12 (kept in private/macos-play/gs/gt4-gs.ini)')
    parser.add_argument('--hdr', choices=('on', 'off'), help='HDR output of gt4-gs on an EDR display (kept likewise)')
    parser.add_argument('--metalfx', choices=('on', 'off'), help='MetalFX upscaling in gt4-gs (kept likewise)')
    arguments = parser.parse_args(argv)
    try:
        if not arguments.iso.is_file():
            raise ValueError(f'missing disc image: {arguments.iso}')
        if arguments.renderer == 'pcsx2' and not arguments.gs_process.is_file():
            raise ValueError(f'missing GS process {arguments.gs_process}; build it (docs/BUILD-MACOS.md, "GS process")')
        if (arguments.upscale or arguments.hdr or arguments.metalfx) and arguments.renderer != 'pcsx2':
            raise ValueError('--upscale, --hdr and --metalfx need --renderer pcsx2')
        card = arguments.card.resolve()
        guest = prepare(card)
        command = [str(GAME), guest.name, '--ntsc', '--disc', str(arguments.iso.resolve()), '--memcard', str(card),
                   '--misses', 'misses.txt', '--window']
        if arguments.fullscreen:
            command.append('--fullscreen')
        if arguments.frames:
            command += ['--frames', str(arguments.frames)]
        print(f'[macos-play] {arguments.log.relative_to(ROOT) if arguments.log.is_relative_to(ROOT) else arguments.log}'
              f' holds the game log; card {card}', flush=True)
        with arguments.log.open('w', encoding='utf-8') as log:
            # caffeinate keeps the Mac awake while the game runs (a race has no keyboard or mouse input).
            result = subprocess.run(['caffeinate', '-i', *command], cwd=PLAY, env=environment(arguments),
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print(f'[macos-play] the game stopped with code {result.returncode}; see {arguments.log}', file=sys.stderr)
        return result.returncode
    except (ValueError, OSError) as error:
        print(f'macos-play: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
