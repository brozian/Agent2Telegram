"""Tests for the agent adapters (argv building, registry, overrides)."""
import unittest

from agent2telegram import adapters
from agent2telegram.adapters import AdapterError, build
from agent2telegram.adapters.claude_code import ClaudeCodeAdapter
from agent2telegram.adapters.codex import CodexAdapter
from agent2telegram.config import Config


class AdapterArgvTests(unittest.TestCase):
    def test_claude_first_turn(self):
        a = ClaudeCodeAdapter()
        argv = a.build_argv("hello world", is_continuation=False)
        self.assertEqual(argv[0], "claude")
        self.assertIn("hello world", argv)
        self.assertNotIn("--continue", argv)

    def test_claude_continuation_uses_continue_flag(self):
        a = ClaudeCodeAdapter()
        argv = a.build_argv("again", is_continuation=True)
        self.assertIn("--continue", argv)
        self.assertIn("again", argv)

    def test_prompt_with_spaces_is_a_single_argv_token(self):
        # Critical: the message must be ONE argv element (no shell, no injection).
        a = CodexAdapter()
        argv = a.build_argv("rm -rf / ; echo pwned", is_continuation=False)
        self.assertIn("rm -rf / ; echo pwned", argv)

    def test_embedded_prompt_placeholder_substituted(self):
        a = adapters.GenericAdapter(command=["tool", "--msg={prompt}"])
        argv = a.build_argv("hi", is_continuation=False)
        self.assertEqual(argv, ["tool", "--msg=hi"])


class RegistryTests(unittest.TestCase):
    def test_build_known_agent(self):
        cfg = Config(agent="claude-code", token="1:2", allowed_user_ids=[1])
        self.assertIsInstance(build(cfg), ClaudeCodeAdapter)

    def test_build_unknown_agent_raises(self):
        cfg = Config(agent="does-not-exist", token="1:2", allowed_user_ids=[1])
        with self.assertRaises(AdapterError):
            build(cfg)

    def test_generic_requires_command(self):
        cfg = Config(agent="generic", token="1:2", allowed_user_ids=[1], command=None)
        with self.assertRaises(AdapterError):
            build(cfg)

    def test_command_override_applies(self):
        cfg = Config(agent="codex", token="1:2", allowed_user_ids=[1],
                     command=["codex", "exec", "--model", "gpt-5.5", "{prompt}"])
        a = build(cfg)
        argv = a.build_argv("x", is_continuation=False)
        self.assertIn("--model", argv)


if __name__ == "__main__":
    unittest.main()
