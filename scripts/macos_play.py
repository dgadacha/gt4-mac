"""Start GT4Recomp on macOS (Apple silicon) after scripts/macos_build.py, in a window or in fullscreen.

The game runs from private/macos-play: the guest executable SCUS_973.28 (a copy of the verified reconstructed ELF, the
name the game expects) and the memory card card.ps2, which keeps the saves between sessions. A copy of the card is
kept in private/macos-play/backups before every session (the ten newest stay). The environment is the Windows
launcher's for the built-in renderer: 16:9 at boot, 480p in races, the aspect ratio of the window, FIFO presentation.

  private/tooling-venv/bin/python scripts/macos_play.py                   play in a window
  private/tooling-venv/bin/python scripts/macos_play.py --fullscreen      play in fullscreen (also Cmd+F, F11, Alt+Enter)
  private/tooling-venv/bin/python scripts/macos_play.py --mute            no sound (the device plays silence)

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
    arguments = parser.parse_args(argv)
    try:
        if not arguments.iso.is_file():
            raise ValueError(f'missing disc image: {arguments.iso}')
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
