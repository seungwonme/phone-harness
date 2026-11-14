"""Keyboard input in the background backend takes the front once per key
sequence, stops typing when the user switches apps, and hands the user's app
back only when iPhone Mirroring is still in front.

No phone needed: the SkyLight and event-posting calls are faked.

    python -m unittest tests.test_background_keyboard_focus
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

try:
    from phone_harness import background, mirror
except Exception:                         # not macOS / no pyobjc / no SkyLight
    background = None

MIRRORING, USER, OTHER = 100, 200, 300
WIN = {"id": 7, "x": 0, "y": 0, "w": 300, "h": 600}


@unittest.skipIf(background is None, "background backend needs macOS")
class KeyboardFocusTest(unittest.TestCase):
    def setUp(self):
        self.front = USER             # the app LaunchServices reports in front
        self.borrows = 0
        self.handed = []
        self.keys = []                # (keycode, down) actually posted
        self.on_key = None            # hook: runs after each posted key edge

        def borrow(_pid, _wid):
            self.borrows += 1
            self.front = MIRRORING

        def activate(pid):
            self.handed.append(pid)
            self.front = pid

        real_create = background.Quartz.CGEventCreateKeyboardEvent
        directions = {}

        def create(source, code, down):
            ev = real_create(source, code, down)
            directions[id(ev)] = (code, down)
            return ev

        def post(_pid, ev):
            code, down = directions.pop(id(ev))
            self.keys.append((code, down))
            if self.on_key:
                self.on_key(code, down)

        env = {k: v for k, v in background.os.environ.items()
               if k != "PHONE_HARNESS_FRONT_PROCESS"}
        for target, attr, fake in (
            (background, "_ctx", lambda: (MIRRORING, WIN)),
            (background, "_front_pid", lambda: self.front),
            (background, "_borrow_front", borrow),
            (background, "_activate_pid", activate),
            (background, "_make_key", lambda _p, _w: None),
            (background.Quartz, "CGEventCreateKeyboardEvent", create),
            (background.Quartz, "CGEventPostToPid", post),
            (background.time, "sleep", lambda _s: None),
            (background.os, "environ", env),
        ):
            p = mock.patch.object(target, attr, fake)
            p.start()
            self.addCleanup(p.stop)

    def test_typing_borrows_once_and_hands_back(self):
        background._type_keystrokes("Ab c")
        self.assertEqual(self.borrows, 1)
        self.assertEqual(self.handed, [USER])
        self.assertEqual(self.front, USER)

    def test_user_switch_stops_typing_and_is_left_alone(self):
        sent_downs = []

        def switch_after_second_char(code, down):
            if down:
                sent_downs.append(code)
            if len(sent_downs) == 2 and not down:
                self.front = OTHER          # user clicks into another app

        self.on_key = switch_after_second_char
        with self.assertRaises(background.KeyboardFocusLost):
            background._type_keystrokes("abcdef")
        self.assertEqual(len(sent_downs), 2)   # c..f never went out
        self.assertEqual(self.borrows, 1)      # never re-took the front
        self.assertEqual(self.handed, [])      # user's new app stays in front
        self.assertEqual(self.front, OTHER)
        self.assertEqual(background._keyboard_depth, 0)
        self.assertIsNone(background._keyboard_pid)

    def test_switch_while_modifiers_held_releases_them(self):
        cmd, shift = (mirror._MOD_KEYCODES[m] for m in ("cmd", "shift"))

        def switch_after_cmd_down(code, down):
            if code == cmd and down:
                self.front = OTHER

        self.on_key = switch_after_cmd_down
        with self.assertRaises(background.KeyboardFocusLost):
            background.press("cmd+shift+a")
        self.assertIn((cmd, False), self.keys)            # cmd released
        self.assertNotIn((shift, True), self.keys)        # shift never pressed
        self.assertNotIn((shift, False), self.keys)
        self.assertEqual(self.handed, [])

    def test_paste_shares_one_borrow(self):
        # type_text -> paste_with -> press: one borrow, one hand-back.
        with mock.patch.object(background.mirror, "paste_with",
                               lambda press_fn, _text: press_fn("cmd+v")):
            background.type_text("Settings")
        self.assertEqual(self.borrows, 1)
        self.assertEqual(self.handed, [USER])

    def test_unreadable_front_app_does_not_abort(self):
        background._keyboard_pid = None
        self.front = None                 # lsappinfo failed
        background.press("a")             # must not raise
        self.assertEqual(self.borrows, 1)
        self.assertEqual(self.handed, [])  # nothing known to hand back to


if __name__ == "__main__":
    unittest.main()
