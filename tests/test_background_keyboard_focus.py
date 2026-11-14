"""Keyboard input in the background backend borrows front-process status and
hands the user's app back only when iPhone Mirroring is still in front.

    python -m unittest tests.test_background_keyboard_focus
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

try:
    from phone_harness import background
except Exception:                         # not macOS / no pyobjc / no SkyLight
    background = None

MIRRORING, USER, OTHER = 100, 200, 300


@unittest.skipIf(background is None, "background backend needs macOS")
class KeyboardFocusTest(unittest.TestCase):
    def run_keys(self, fronts, body=lambda: None):
        """Run body inside _keyboard_focus with _front_pid answering `fronts`
        in order; return the pids handed focus back to."""
        handed = []
        with mock.patch.object(background, "_front_pid", side_effect=list(fronts)), \
             mock.patch.object(background, "_activate_pid", side_effect=handed.append):
            with background._keyboard_focus(MIRRORING):
                body()
        return handed

    def test_hands_back_when_mirroring_kept_front(self):
        self.assertEqual(self.run_keys([USER, MIRRORING]), [USER])

    def test_leaves_an_app_the_user_switched_to(self):
        self.assertEqual(self.run_keys([USER, OTHER]), [])

    def test_hands_back_even_when_the_keys_fail(self):
        def boom():
            raise RuntimeError("key path failed")
        with self.assertRaises(RuntimeError):
            self.run_keys([USER, MIRRORING], boom)
        self.assertEqual(background._keyboard_depth, 0)

    def test_nested_sequence_hands_back_once(self):
        # type_text -> paste_with -> press: one borrow, one hand-back.
        def inner():
            with background._keyboard_focus(MIRRORING):
                self.assertEqual(background._keyboard_depth, 2)
        self.assertEqual(self.run_keys([USER, MIRRORING], inner), [USER])
        self.assertEqual(background._keyboard_depth, 0)

    def test_front_process_only_during_keys(self):
        with mock.patch.object(background._sky, "_SLPSSetFrontProcessWithOptions") as front, \
             mock.patch.dict(background.os.environ, {}, clear=False):
            background.os.environ.pop("PHONE_HARNESS_FRONT_PROCESS", None)
            background._front_process(None, 1)
            self.assertFalse(front.called)          # a tap stays in the background
            background._keyboard_depth = 1
            try:
                background._front_process(None, 1)
            finally:
                background._keyboard_depth = 0
            self.assertTrue(front.called)


if __name__ == "__main__":
    unittest.main()
