from __future__ import annotations

import threading
import unittest

from smart_drive_organizer.operation_control import OperationCancelled, OperationControl


class OperationControlTests(unittest.TestCase):
    def test_paused_checkpoint_waits_until_resumed(self):
        control = OperationControl(checkpoint_interval=0.01)
        entered = threading.Event()
        finished = threading.Event()
        errors = []

        def work():
            entered.set()
            try:
                control.checkpoint()
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        control.pause()
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(1))
        self.assertFalse(finished.wait(0.08))
        control.resume()
        self.assertTrue(finished.wait(1))
        self.assertEqual(errors, [])
        worker.join(timeout=1)

    def test_cancel_unblocks_paused_checkpoint_and_raises(self):
        control = OperationControl(checkpoint_interval=0.01)
        control.pause()
        control.cancel()
        with self.assertRaises(OperationCancelled):
            control.checkpoint()
        self.assertTrue(control.cancelled)
        self.assertFalse(control.paused)


if __name__ == "__main__":
    unittest.main()
