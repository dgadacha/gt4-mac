"""Open the qualified Windows pilot with a persistent private memory card."""
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import sys

from external_runtime_probe import (ROOT, VU1_CORPUS_NAME, binary_workspace_for, run_probe, separate_play_card,
                                    verify_manual_capture_profile, verify_performance_profile)

if os.name == 'nt':
    import msvcrt
else:
    import fcntl


def lock_session_byte(lock):
    """Locks the open session lock file without waiting; OSError when another open of it holds the lock.
    Windows locks the first byte (msvcrt), POSIX the whole file (flock, held per open file like the Windows lock).
    Both are released when the process ends, even after a crash."""
    if os.name == 'nt':
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_session_byte(lock):
    if os.name == 'nt':
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def play(assets_root=None, runtime_manifest=None, capture_shapes=False, performance=False, vu1_record=False,
         vu1_verify=0, vu1_interpret_only=False, force_480p=False, vu0_verify=0, cpu_cores=None, controls_file=None,
         renderer_override=None, play_card=None):
    workspace = Path(assets_root or ROOT).resolve()
    # --play-card (TASK-017 license checks): a separate existing card inside private/, never the owner's card.
    separate_card = separate_play_card(workspace, play_card) if play_card is not None else None
    if performance:
        manifest = Path(runtime_manifest).resolve()
        verify_performance_profile(manifest, json.loads(manifest.read_text(encoding='utf-8')), ROOT)
    play_directory = workspace / 'private/manual-play'
    if not play_directory.resolve().is_relative_to((workspace / 'private').resolve()):
        raise ValueError('Manual play directory must remain inside private/')
    play_directory.mkdir(parents=True, exist_ok=True)
    # The system releases this byte lock even when the launcher process crashes.
    with (play_directory / 'session.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            lock_session_byte(lock)
        except OSError as error:
            raise ValueError('Another manual game session is already running') from error
        try:
            run_directory = play_directory / datetime.now().strftime('session-%Y%m%d-%H%M%S-%f')
            card = separate_card or play_directory / 'card.ps2'
            manifest = Path(runtime_manifest or ROOT / 'docs/inputs/slice114-native-base.json').resolve()
            if not manifest.is_relative_to(ROOT / 'docs/inputs'):
                raise ValueError('Manual runtime manifest must stay inside repository docs/inputs')
            video = json.loads(manifest.read_text(encoding='utf-8'))
            if capture_shapes:
                verify_manual_capture_profile(manifest, video, ROOT)
            seed = None if card.exists() else workspace / video['default_card_seed']['path']
            print('GT4 experimental: audio + XInput. Close window to exit.', flush=True)
            print('Keyboard: Enter starts, arrow keys steer, Z accelerates, A brakes; S returns in options.', flush=True)
            print('Display: 16:9 fixed. Alt+Enter or F11 toggles borderless fullscreen.', flush=True)
            if force_480p:
                print('GT4_FORCE_480P=1: experimental 480p request rewrite; the owner checks menus and races.', flush=True)
            if separate_card:
                print(f'Separate test card (--play-card); the owner card is not used: {card}', flush=True)
            print(f'Local save: {card}\nSession log: {run_directory}', flush=True)
            if capture_shapes:
                print('Capture starts OFF. Select the scene yourself, then press F8 to start/stop.', flush=True)
                print(f'One capture per launch, up to 256 records: {run_directory / "shape-capture.json"}', flush=True)
            if renderer_override == 'donor':
                print('Restart with the built-in renderer (CoreGS 1.1) after the GS process stopped.', flush=True)
            elif video.get('gs_stream', {}).get('renderer') == 'pcsx2':
                readback = os.environ.get('GT4_GS_READBACK', 'accurate')
                if readback == 'no-readbacks':
                    readback += ' (Performance Mode on: faster, some effects skipped)'
                print(f'GS: PCSX2 GS process, readback mode {readback}, scale {os.environ.get("GT4_GS_SCALE", "3")}x.',
                      flush=True)
            if performance:
                print(f"Measurement mode: {video.get('measurement_mode', 'detailed')}", flush=True)
                print('Performance test: F7 starts, F8 reports, F9 toggles diagnostics. Owner controls gameplay.', flush=True)
            if vu1_record:
                print(f'VU1 recording: missed programs go to {run_directory / VU1_CORPUS_NAME}', flush=True)
                print('Summary is written when the game exits. Owner controls gameplay.', flush=True)
            if vu1_verify:
                print(f'VU1 verify: every {vu1_verify}th generated call is compared with the interpreter; '
                      'mismatches go to the session log.', flush=True)
            if vu1_interpret_only:
                print('VU1 interpret-only: this binary runs the interpreter for every VU1 call (A/B).', flush=True)
            if vu0_verify:
                print(f'VU0 verify: every {vu0_verify}th generated VU0 call is compared with the exact interpreter; '
                      'mismatches go to the session log.', flush=True)
            result = run_probe(workspace, run_directory, 0, 43200, [], seed,
                               manifest,
                               window=True, interactive=True, play_card=card,
                               runtime_workspace=ROOT, capture_shapes=capture_shapes, performance=performance,
                               vu1_record=vu1_record, vu1_verify=vu1_verify, vu1_interpret_only=vu1_interpret_only,
                               force_480p=force_480p, vu0_verify=vu0_verify, cpu_cores=cpu_cores,
                               binary_workspace=binary_workspace_for(ROOT, workspace),
                               controls_file=controls_file, renderer_override=renderer_override,
                               separate_card=separate_card is not None)
            if result.get('gs_restart_requested') == 'donor' and renderer_override is None:
                restart = True
            elif not result.get('manual_session_closed'):
                raise ValueError(f"Game stopped: {result.get('reason', 'see probe.log')}; log: {run_directory}")
            else:
                restart = False
        finally:
            lock.seek(0)
            unlock_session_byte(lock)
    if restart:
        # TASK-038: the player answered "yes" in the GS failure message box; same build, built-in renderer.
        print(f'GS process stopped; restarting with the built-in renderer (CoreGS 1.1). Previous log: {run_directory}',
              flush=True)
        play(assets_root, runtime_manifest, capture_shapes, performance, vu1_record, vu1_verify, vu1_interpret_only,
             force_480p, vu0_verify, cpu_cores, controls_file=controls_file, renderer_override='donor',
             play_card=play_card)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force-480p', action='store_true',
                        help='Experimental: rewrite the default 480i request to 480p progressive (GT4_FORCE_480P=1)')
    parser.add_argument('--controls', type=Path, default=None,
                        help='Controls TOML file (docs/CONTROLS.md); default: built-in bindings')
    options = parser.parse_args()
    try:
        play(force_480p=options.force_480p, controls_file=options.controls)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
