"""Tests for config load/save/validation."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from agent2telegram.config import Config, ConfigError, load, save


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.json"

    def tearDown(self):
        self.dir.cleanup()
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    def test_roundtrip(self):
        cfg = Config(agent="codex", token="123:secret", allowed_user_ids=[7])
        save(cfg, self.path)
        loaded = load(self.path)
        self.assertEqual(loaded.agent, "codex")
        self.assertEqual(loaded.allowed_user_ids, [7])

    def test_saved_file_is_0600(self):
        save(Config(agent="codex", token="1:2", allowed_user_ids=[1]), self.path)
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)

    def test_missing_token_invalid(self):
        with self.assertRaises(ConfigError):
            Config(agent="codex", token="", allowed_user_ids=[]).validate()

    def test_malformed_token_invalid(self):
        with self.assertRaises(ConfigError):
            Config(agent="codex", token="no-colon", allowed_user_ids=[]).validate()

    def test_redacted_masks_token(self):
        cfg = Config(agent="codex", token="123456:supersecret", allowed_user_ids=[1])
        self.assertNotIn("supersecret", str(cfg.redacted()))

    def test_env_token_override(self):
        save(Config(agent="codex", token="111:fromfile", allowed_user_ids=[1]), self.path)
        os.environ["TELEGRAM_BOT_TOKEN"] = "999:fromenv"
        self.assertEqual(load(self.path).token, "999:fromenv")

    def test_missing_file_raises(self):
        with self.assertRaises(ConfigError):
            load(Path(self.dir.name) / "nope.json")


if __name__ == "__main__":
    unittest.main()
