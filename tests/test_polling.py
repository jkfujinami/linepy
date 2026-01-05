import unittest
from unittest.mock import MagicMock
from linepy.client import Client, Message as ClientMessage
from linepy.models.talk import Message as PydanticMessage, Operation, OpType


class TestPollingLogic(unittest.TestCase):
    def setUp(self):
        # Mock BaseClient and Polling
        self.mock_client_base = MagicMock()
        self.mock_client_base.polling = MagicMock()
        self.mock_client_base.mid = "u123"  # Mock own mid

        # Create Client instance with mocked base
        self.client = Client()
        self.client.base = self.mock_client_base

        # Mock event handler
        self.mock_handler = MagicMock()
        self.client.on("message")(self.mock_handler)

    def test_handle_operation_message(self):
        """Test handling of RECEIVE_MESSAGE operation"""
        # Create a mock operation with Pydantic Message
        # Note: We must be careful with aliases. PydanticMessage expects input to match field names or aliases depending on config.
        # But when model_dump is called, it produces aliases if by_alias=True.
        # client.py does:
        # msg = Message(
        #    operation.message.model_dump(by_alias=True) ...,
        # )

        pydantic_msg = PydanticMessage(
            from_="u123", to="u456", text="Hello world", id="msg1", content_type=0
        )

        operation = Operation(
            revision=100, type=OpType.RECEIVE_MESSAGE, message=pydantic_msg
        )

        # Verify model dump outputs aliases
        dump = pydantic_msg.model_dump(by_alias=True)
        # print("DEBUG: Dumped msg:", dump)

        # Simulate polling yielding this operation
        self.client._handle_operation(operation)

        # Check if handler was called
        self.assertTrue(self.mock_handler.called)

        # Check argument passed to handler
        args, _ = self.mock_handler.call_args
        msg = args[0]

        self.assertIsInstance(msg, ClientMessage)
        self.assertEqual(msg.text, "Hello world")
        self.assertEqual(msg.from_, "u123")

        # Verify Message wrapper behavior
        self.assertEqual(msg._raw.get(1), "u123")
        self.assertEqual(msg._raw.get(10), "Hello world")

    def test_reply_logic_1on1(self):
        """Test reply logic for 1:1 chat"""
        # 1:1 message: from=Other, to=Me
        pydantic_msg = PydanticMessage(from_="uOther", to="uMe", text="Hi", id="msg1")
        self.client.base.send_message = MagicMock()

        # Construct wrapper
        dump = pydantic_msg.model_dump(by_alias=True)
        msg_wrapper = ClientMessage(dump, self.client)

        # Reply
        msg_wrapper.reply("Hello")

        # Should send to "uOther" (the sender)
        self.client.base.send_message.assert_called_with("uOther", "Hello")

    def test_reply_logic_group(self):
        """Test reply logic for Group chat"""
        # Group message: from=Other, to=Group
        pydantic_msg = PydanticMessage(
            from_="uOther", to="cGroup", text="Hi group", id="msg2"
        )
        self.client.base.send_message = MagicMock()

        # Construct wrapper
        dump = pydantic_msg.model_dump(by_alias=True)
        msg_wrapper = ClientMessage(dump, self.client)

        # Reply
        msg_wrapper.reply("Hello group")

        # Should send to "cGroup" (the group mid)
        self.client.base.send_message.assert_called_with("cGroup", "Hello group")


if __name__ == "__main__":
    unittest.main()
