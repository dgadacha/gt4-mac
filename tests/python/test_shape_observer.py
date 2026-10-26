"""Run the actual bounded C++ observer controls through native test discovery."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

# The native fixtures carry the .exe suffix on Windows only.
EXECUTABLE_SUFFIX = '.exe' if os.name == 'nt' else ''


class ShapeObserverTests(unittest.TestCase):
    def test_native_observer_contract(self):
        root = Path(__file__).resolve().parents[2]
        build = Path(os.environ.get('GT4_NATIVE_BUILD', root / 'private/slice114-native-base/build'))
        executable = build / ('shape_observer_fixture' + EXECUTABLE_SUFFIX)
        if not executable.exists() and 'GT4_NATIVE_BUILD' not in os.environ:
            self.skipTest('Build the native observer fixture or set GT4_NATIVE_BUILD')
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                check=True, timeout=30)
        self.assertIn('PASS: shape observer memory, frontier, ownership and bounds controls', result.stdout)

    def test_actual_runtime_adapter_matches_unoverlaid_guest_control(self):
        if os.environ.get('GT4_SHAPE_RUNTIME_TESTS') != '1':
            self.skipTest('Experimental runtime overlay fixture is not configured')
        build = Path(os.environ['GT4_NATIVE_BUILD'])
        results = [subprocess.run([str(build / name)], capture_output=True, check=True, timeout=30)
                   for name in ('shape_runtime_control' + EXECUTABLE_SUFFIX, 'shape_runtime_fixture' + EXECUTABLE_SUFFIX)]
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertIn(b'PASS: synthetic runtime adapter/lifecycle controls', results[1].stderr)
        self.assertIn(b'[probe] 0x00707070', results[1].stderr)
        cache = (build / 'CMakeCache.txt').read_text()
        if 'GT4_EE_PROFILE:STRING=observation' not in cache:
            return
        root = Path(__file__).resolve().parents[2]
        profile = json.loads((root / 'docs/inputs/slice131-observation-library.json').read_text())['profile']
        self.assertEqual((root / profile['path']).stat().st_size, profile['size_bytes'])
        self.assertEqual(hashlib.sha256((root / profile['path']).read_bytes()).hexdigest(), profile['sha256'])
        graph = (build / 'build.ninja').read_text().splitlines()
        game = next(line for line in graph if line.startswith('build gt4vulkan.exe:'))
        control = next(line for line in graph if line.startswith('build shape_runtime_control.exe:'))
        for name in ('dispatch.cpp.obj', 'kernel.cpp.obj', 'system.cpp.obj',
                     'shape_observer.cpp.obj', 'shape_observer_adapter.cpp.obj',
                     'shape_capture_control.cpp.obj', 'shape_capture_export.cpp.obj'):
            self.assertIn(name, game)
        for name in ('dispatch.cpp.obj', 'kernel.cpp.obj', 'system.cpp.obj'):
            self.assertNotIn(name, control)
        self.assertIn('slice131-observation-library', game)
        bindings = (build / 'observation-game.map').read_text().splitlines()
        symbols = {'?register_units@ps2@@': 'dispatch.cpp.obj', '?dispatch@ps2@@': 'dispatch.cpp.obj',
                   '?probe@ps2@@': 'dispatch.cpp.obj', '?reset@kernel@ps2@@': 'kernel.cpp.obj',
                   '?start_main_thread@kernel@ps2@@': 'kernel.cpp.obj',
                   '?in_handler@kernel@ps2@@': 'kernel.cpp.obj', '?current_thread@kernel@ps2@@': 'kernel.cpp.obj',
                   '?handle_syscall@kernel@ps2@@': 'kernel.cpp.obj', '?state@kernel@ps2@@': 'kernel.cpp.obj',
                   '?boot@ps2@@': 'system.cpp.obj', '?load_state@ps2@@': 'system.cpp.obj',
                   '?g_cpu@ps2@@': 'system.cpp.obj', '?g_options@ps2@@': 'system.cpp.obj',
                   '?observe_probe@observation@gt4@@': 'shape_observer_adapter.cpp.obj',
                   '?request_toggle@CaptureControl@observation@gt4@@': 'shape_capture_control.cpp.obj',
                   '?service@CaptureControl@observation@gt4@@': 'shape_capture_control.cpp.obj',
                   '?finish@CaptureControl@observation@gt4@@': 'shape_capture_control.cpp.obj',
                   '?serialize_capture@observation@gt4@@': 'shape_capture_export.cpp.obj',
                   '?export_capture@observation@gt4@@': 'shape_capture_export.cpp.obj'}
        for prefix, expected_object in symbols.items():
            selected = [line.split() for line in bindings
                        if len(line.split()) >= 4 and line.split()[1].startswith(prefix)]
            self.assertEqual(len(selected), 2 if prefix == '?load_state@ps2@@' else 1, prefix)
            for row in selected:
                self.assertEqual(row[-1], expected_object, row)
        self.assertTrue(any('ps2game:unit_00D5.cpp.obj' in line for line in bindings))


if __name__ == '__main__':
    unittest.main()
