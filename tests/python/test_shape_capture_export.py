"""Parse the actual native capture fixture; preserve raw widths and every lane."""
import json
import os
from pathlib import Path
import subprocess
import unittest


class ShapeCaptureExportTests(unittest.TestCase):
    def test_native_capture_roundtrip_and_file_controls(self):
        root = Path(__file__).resolve().parents[2]
        build = Path(os.environ.get('GT4_NATIVE_BUILD', root / 'private/slice114-native-base/build'))
        if os.name != 'nt':
            self.skipTest('the shape capture fixtures are built on Windows only (native/CMakeLists.txt)')
        executable = build / 'shape_capture_export_fixture.exe'
        if not executable.exists() and 'GT4_NATIVE_BUILD' not in os.environ:
            self.skipTest('Build the native capture export fixture or set GT4_NATIVE_BUILD')
        result = subprocess.run([str(executable)], capture_output=True, text=True, check=True, timeout=30)
        self.assertIn('PASS: bounded capture JSON and exclusive file controls', result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 3)
        empty, one, full = [json.loads(line) for line in lines]
        self.assertEqual([item['record_count'] for item in (empty, one, full)], [0, 1, 256])
        self.assertEqual([item['stop_reason'] for item in (empty, one, full)],
                         ['shutdown', 'manual', 'observer_stopped'])
        self.assertEqual(one['counters']['aborted'], '0000000000000001')
        self.assertEqual(full['counters']['record_dropped'], '0000000000000001')
        for report in (empty, one, full):
            self.assertEqual(report['schema_version'], 1)
            self.assertEqual(set(report), {'schema_version', 'scope', 'call_pc', 'target_pc', 'return_pc',
                                          'stop_reason', 'record_count', 'counters', 'records'})
            self.assertEqual(set(report['counters']), {'started', 'completed', 'aborted', 'handler_skipped',
                              'orphan', 'rejected_return', 'ambiguous_stack', 'capacity_rejected',
                              'record_dropped', 'incomplete_samples'})
            self.assertEqual(report['scope'], 'shape_call_metadata_only')
            self.assertEqual([report[key] for key in ('call_pc', 'target_pc', 'return_pc')],
                             ['00455a5c', '0049d308', '00455a64'])
            self.assertLessEqual(len(json.dumps(report)), 256 * 1024)
            for value in report['counters'].values():
                self.assertRegex(value, r'^[0-9a-f]{16}$')
            for record in report['records']:
                self.assertEqual(set(record), {'epoch', 'incarnation', 'sequence', 'owner_id', 'before', 'after'})
                self.assertEqual(record['owner_id'], 'ffffffff')
                for name in ('epoch', 'incarnation', 'sequence'):
                    self.assertRegex(record[name], r'^[0-9a-f]{16}$')
                before = record['before']
                self.assertEqual(set(before), {'argument_bits', 'fpr12_bits', 'guest_sp', 'metadata'})
                self.assertEqual(before['fpr12_bits'], '7fc12345')
                self.assertEqual(before['guest_sp'], '01fff000')
                self.assertEqual(before['argument_bits'],
                                 [[f'{0xffffff00 + argument * 4 + lane:08x}' if (argument, lane) != (3, 3)
                                   else 'ffffffff' for lane in range(4)] for argument in range(4)])
                self.assertEqual(before['metadata'], {'valid_fields': '0000003f', 'enabled': 'ffffffff',
                                 'cached_bits': '80000000', 'cursor': '70002340', 'shape_bits': 'ffffffff',
                                 'descriptor_count': 'ffff', 'flag': 'ff'})
                self.assertEqual(record['after'], {**before['metadata'], 'valid_fields': '00000008', 'cursor': '700025a0'})
        sequences = [int(row['sequence'], 16) for row in full['records']]
        self.assertEqual(sequences, sorted(set(sequences)))


if __name__ == '__main__':
    unittest.main()
