"""Actual host latch controls, without GUI messages or guest execution."""
import json
import os
from pathlib import Path
import subprocess
import unittest


class CaptureControlTests(unittest.TestCase):
    def test_deferred_control_and_real_export(self):
        root = Path(__file__).resolve().parents[2]
        build = Path(os.environ.get('GT4_NATIVE_BUILD', root / 'private/slice114-native-base/build'))
        if os.name != 'nt':
            self.skipTest('the shape capture fixtures are built on Windows only (native/CMakeLists.txt)')
        executable = build / 'shape_capture_control_fixture.exe'
        if not executable.exists() and 'GT4_NATIVE_BUILD' not in os.environ:
            self.skipTest('Build the manual capture fixture or set GT4_NATIVE_BUILD')
        result = subprocess.run([str(executable)], capture_output=True, text=True, check=True, timeout=30)
        self.assertIn('PASS: deferred manual capture, limits, shutdown and retry controls', result.stderr)
        manual, full, ambiguous, shutdown, retry, shutdown_retry = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([report['record_count'] for report in (manual, full, ambiguous, shutdown, retry, shutdown_retry)],
                         [1, 256, 0, 1, 1, 1])
        self.assertEqual([report['stop_reason'] for report in (manual, full, ambiguous, shutdown, retry, shutdown_retry)],
                         ['manual', 'observer_stopped', 'observer_stopped', 'shutdown', 'manual', 'manual'])
        self.assertEqual(full['counters']['record_dropped'], '0000000000000001')
        self.assertEqual(ambiguous['counters']['ambiguous_stack'], '0000000000000001')
        self.assertEqual(ambiguous['counters']['record_dropped'], '0000000000000000')
        self.assertEqual(manual, retry)
        self.assertEqual(manual, shutdown_retry)


if __name__ == '__main__':
    unittest.main()
