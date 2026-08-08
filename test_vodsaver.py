import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import vodsaver


class VODSaverTests(unittest.TestCase):
    def test_show_name_supports_singular_and_plural_settings(self):
        self.assertEqual(vodsaver.resolve_show_name("channel", 0, [], "My Show"), "My Show")
        self.assertEqual(vodsaver.resolve_show_name("channel", 1, ["First", "Second"], "Legacy"), "Second")
        self.assertEqual(vodsaver.resolve_show_name("channel", 0, [], ""), "channel")

    def test_quoted_comma_separated_show_names(self):
        names = vodsaver.normalize_show_names('Primeagen,"Michael Reeves"')
        self.assertEqual(names, ["Primeagen", "Michael Reeves"])
        self.assertEqual(vodsaver.resolve_show_name("theprimeagen", 0, names), "Primeagen")
        self.assertEqual(vodsaver.resolve_show_name("michaelreeves", 1, names), "Michael Reeves")

    def test_build_paths_uses_channel_month_and_date(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            vod_date = dt.datetime(2026, 8, 8, 12, 30)
            target, basename, season, episode = vodsaver.build_paths(
                output, "Example", "Example", vod_date
            )
            self.assertEqual(target, output / "Example" / "August")
            self.assertEqual(basename, "2026-08-08")
            self.assertEqual((season, episode), (8, 8))

    def test_second_vod_on_same_day_gets_time_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "2026-08-08.mp4").touch()
            vod_date = dt.datetime(2026, 8, 8, 12, 30)
            self.assertEqual(vodsaver.choose_base_name(target, vod_date), "2026-08-08-12-30")

    def test_state_write_is_valid_and_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = {"last_vod_id": "123"}
            vodsaver.save_state(state_path, state)
            self.assertEqual(json.loads(state_path.read_text()), state)
            self.assertFalse((Path(directory) / "state.json.tmp").exists())

    def test_lock_rejects_concurrent_run_and_can_be_reacquired(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "vodsaver.lock"
            first = vodsaver.acquire_lock(lock_path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(vodsaver.acquire_lock(lock_path))
            finally:
                first.close()
            second = vodsaver.acquire_lock(lock_path)
            self.assertIsNotNone(second)
            second.close()


if __name__ == "__main__":
    unittest.main()
