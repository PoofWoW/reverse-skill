import importlib.util
from pathlib import Path
import unittest
from test_screenshot import make_device

spec = importlib.util.spec_from_file_location('mixed_touch', Path(__file__).resolve().parents[1] / 'diagnostics/mixed_touch.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class TouchClientTests(unittest.TestCase):
    def test_existing_tap_wire_format_and_fractional_coordinates(self):
        device = make_device([])
        device.touch(1, 7, 123.4, 567.8)
        self.assertEqual(device.s.sent, [b'1011070123405678\r\n'])
        self.assertEqual(harness.frame([(1, 7, 123.4, 567.8)]), device.s.sent[0])

    def test_two_finger_frame_accepts_float_coordinates(self):
        device = make_device([])
        device.touch_with_list([{'type':1,'finger_index':7,'x':123.4,'y':567.8},
                                {'type':1,'finger_index':9,'x':100,'y':200}])
        self.assertEqual(device.s.sent, [harness.frame([(1,7,123.4,567.8),(1,9,100,200)])])

    def test_invalid_inputs_do_not_send_any_bytes(self):
        device = make_device([])
        for values in [(3,7,1,2),(1,20,1,2),(1,-1,1,2),(1,7,-1,2),
                       (1,7,float('nan'),2),(1,7,float('inf'),2),(1,7,10000,2)]:
            with self.assertRaises(ValueError):
                device.touch(*values)
            with self.assertRaises(ValueError):
                harness.frame([values])
        for events in [[], [{'type':1,'finger_index':7,'x':1,'y':2}]*2,
                       [{'type':1,'finger_index':i,'x':1,'y':2} for i in range(10)]]:
            with self.assertRaises(ValueError):
                device.touch_with_list(events)
        self.assertEqual(device.s.sent, [])

    def test_release_and_status_commands(self):
        device = make_device([b'0\r\n', b'0;;{"appReceiptVerified":false}\r\n'])
        device.release_touches()
        device.touch_status()
        self.assertEqual(device.s.sent, [b'31\r\n', b'32\r\n'])

    def test_harness_releases_after_mid_gesture_failure(self):
        import contextlib
        import io
        from types import SimpleNamespace
        from unittest import mock
        class Socket:
            def __init__(self):
                self.sent = []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def settimeout(self, value): pass
            def sendall(self, payload):
                self.sent.append(payload)
                if len(self.sent) == 2:
                    raise OSError('simulated failed MOVE')
        sock = Socket()
        args = SimpleNamespace(slot=7, second_slot=9, mode='physical-first',x=800,y=1200,
                               spacing=200,distance=80,host='device',port=6000,
                               countdown=0,duration=6,output=None)
        with mock.patch.object(harness.socket, 'create_connection', return_value=sock), \
             mock.patch.object(harness.time, 'sleep'), \
             mock.patch.object(harness.time, 'monotonic', side_effect=[0,0,0.1,0.1,0.1,0.1]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                harness.run(args)
        self.assertEqual(len(sock.sent), 3)
        self.assertEqual(sock.sent[0][3:6], b'107')
        self.assertEqual(sock.sent[-1][3:6], b'007')
