"""Manual capture wrapper uses existing save/lock flow; no game is launched."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import play_external_runtime as launcher
import play_shape_capture as capture


class ManualCaptureLauncherTests(unittest.TestCase):
    def prepare(self, root, qualified=True):
        inputs = root / 'docs/inputs'
        inputs.mkdir(parents=True)
        manifest = inputs / 'slice136-keyboard-input.json'
        manifest.write_text(json.dumps({'profile': 'observation', 'capture_activation_implemented': qualified,
                                       'capture_schema_version': 1,
                                       'runtime': {'path': 'private/slice136-keyboard-input/build/gt4vulkan.exe'}}))
        directory = root / 'private/manual-play'
        directory.mkdir(parents=True)
        card = directory / 'card.ps2'
        card.write_bytes(b'c' * 8650752)
        return manifest, directory, card

    def test_cli_refuses_aspect_and_selects_only_pinned_manual_capture_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(capture, 'ROOT', root), patch.object(capture, 'play') as play, \
                    patch.object(sys, 'argv', ['capture', '--assets-root', str(root), '--aspect', '4:3']):
                with self.assertRaises(SystemExit):
                    capture.main()
            play.assert_not_called()

    def test_cli_selects_only_pinned_manual_capture_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(capture, 'ROOT', root), patch.object(capture, 'play') as play, \
                    patch.object(sys, 'argv', ['capture', '--assets-root', str(root)]):
                self.assertEqual(capture.main(), 0)
            play.assert_called_once_with(root, root / 'docs/inputs/slice136-keyboard-input.json', capture_shapes=True)

    def test_capture_holds_save_lock_and_releases_after_probe_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, directory, card = self.prepare(root)
            original = card.read_bytes()
            def reject(*args, **options):
                self.assertTrue(options['capture_shapes'])
                self.assertEqual(options['play_card'], card)
                self.assertEqual(options['runtime_workspace'], root)
                with (directory / 'session.lock').open('r+b') as second:
                    with self.assertRaises(OSError):
                        launcher.lock_session_byte(second)
                raise ValueError('synthetic runtime preflight failure')
            with patch.object(launcher, 'ROOT', root), patch.object(launcher, 'run_probe', side_effect=reject):
                with self.assertRaisesRegex(ValueError, 'preflight'):
                    launcher.play(root, manifest, capture_shapes=True)
            self.assertEqual(card.read_bytes(), original)
            self.assertFalse(any(directory.glob('session-*')))
            with (directory / 'session.lock').open('r+b') as released:
                launcher.lock_session_byte(released)
                launcher.unlock_session_byte(released)

    def test_active_session_and_unqualified_profile_preserve_card(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, directory, card = self.prepare(root, qualified=False)
            original = card.read_bytes()
            with patch.object(launcher, 'ROOT', root), patch.object(launcher, 'run_probe') as execute:
                with self.assertRaisesRegex(ValueError, 'qualified manual observation'):
                    launcher.play(root, manifest, capture_shapes=True)
                lock_path = directory / 'session.lock'
                with lock_path.open('r+b') as active:
                    launcher.lock_session_byte(active)
                    try:
                        with self.assertRaisesRegex(ValueError, 'already running'):
                            launcher.play(root, manifest, capture_shapes=True)
                    finally:
                        launcher.unlock_session_byte(active)
                execute.assert_not_called()
            self.assertEqual(card.read_bytes(), original)
            self.assertFalse(any(directory.glob('session-*')))


if __name__ == '__main__':
    unittest.main()
