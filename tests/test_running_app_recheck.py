"""running_app() answers None only after a second lookup path and one bounded
re-check agree. No phone needed.

    python -m unittest tests.test_running_app_recheck
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from phone_harness import mirror
except Exception:                         # not macOS / no pyobjc
    mirror = None


class _App:
    def __init__(self, bid):
        self._b = bid

    def bundleIdentifier(self):
        return self._b


@unittest.skipIf(mirror is None, "needs macOS")
class RunningAppTest(unittest.TestCase):
    def _patch(self, by_id, workspace):
        nsra = mock.Mock()
        nsra.runningApplicationsWithBundleIdentifier_.side_effect = by_id
        nsws = mock.Mock()
        nsws.sharedWorkspace.return_value.runningApplications.side_effect = workspace
        return (mock.patch.object(mirror, "NSRunningApplication", nsra),
                mock.patch.object(mirror, "NSWorkspace", nsws),
                mock.patch.object(mirror.time, "sleep"))

    def test_transient_empty_is_found_on_recheck(self):
        app = _App(mirror.BUNDLE_ID)
        a, b, c = self._patch([[], [app]], [[], []])
        with a, b, c as sleep:
            self.assertIs(mirror.running_app(), app)
            sleep.assert_called_once()

    def test_workspace_scan_finds_it_when_bundle_lookup_is_empty(self):
        app = _App(mirror.BUNDLE_ID)
        a, b, c = self._patch([[]], [[_App("x"), app]])
        with a, b, c as sleep:
            self.assertIs(mirror.running_app(), app)
            sleep.assert_not_called()

    def test_really_not_running_checks_once_more_then_none(self):
        a, b, c = self._patch([[], []], [[], []])
        with a, b, c as sleep:
            self.assertIsNone(mirror.running_app())
            sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
