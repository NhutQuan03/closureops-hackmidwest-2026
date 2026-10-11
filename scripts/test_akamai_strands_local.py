"""Offline request-formatting tests; no inference or real credentials used."""

import unittest

from scripts.test_akamai_strands import build_model, load_strands_classes
from strands.models.openai import OpenAIModel


class AkamaiRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        loaded = load_strands_classes()
        self.assertIsNotNone(loaded)
        _, model_class = loaded
        self.model = build_model(model_class, "not-a-real-key")
        self.original = build_model(OpenAIModel, "not-a-real-key")
        self.messages = [{"role": "user", "content": [{"text": "Offline test"}]}]

    def test_empty_tools_remove_only_tool_fields(self) -> None:
        for tools in (None, []):
            for choice in (None, {"auto": {}}, {"any": {}}):
                with self.subTest(tools=tools, choice=choice):
                    expected = self.original.format_request(
                        self.messages, tools, "System prompt", choice
                    )
                    expected.pop("tools", None)
                    expected.pop("tool_choice", None)
                    actual = self.model.format_request(
                        self.messages, tools, "System prompt", choice
                    )
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual["model"], "hackathon-chat")
                    self.assertIs(actual["stream"], False)
                    self.assertEqual(actual["max_tokens"], 150)

    def test_nonempty_tools_and_choice_are_unchanged(self) -> None:
        tools = [{
            "name": "read_facility",
            "description": "Read synthetic facility data",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"facility_id": {"type": "string"}},
                "required": ["facility_id"],
                "additionalProperties": False,
            }},
        }]
        for choice in (None, {"auto": {}}, {"any": {}},
                       {"tool": {"name": "read_facility"}}):
            with self.subTest(choice=choice):
                kwargs = {
                    "messages": self.messages,
                    "tool_specs": tools,
                    "system_prompt": "System prompt",
                    "tool_choice": choice,
                }
                self.assertEqual(
                    self.model.format_request(**kwargs),
                    self.original.format_request(**kwargs),
                )


if __name__ == "__main__":
    unittest.main()
