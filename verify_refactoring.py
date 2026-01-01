import unittest
from unittest.mock import MagicMock, patch
import json
import os
from linepy import Client
from linepy.helpers import reply_message, send_chat_message
from linepy.models.talk import Profile, Contact, Chat, Message


class TestClientRefactoring(unittest.TestCase):
    """
    Test suite to verify Client functionality after refactoring.
    Focuses on type safety and return values.
    """

    def setUp(self):
        # Initialize client with mock storage to avoid file I/O
        self.mock_storage = MagicMock()
        self.client = Client(storage=self.mock_storage)

        # Mock BaseClient's internal components to isolate Client tests
        self.client.base.talk = MagicMock()
        self.client.base.login = MagicMock()

    def test_init(self):
        """Test Client initialization"""
        self.assertIsInstance(self.client, Client)
        self.assertIsNotNone(self.client.base)
        self.assertFalse(self.client._polling)

    def test_close(self):
        """Test close method"""
        self.client.base.close = MagicMock()
        self.client.close()
        self.client.base.close.assert_called_once()

    def test_properties(self):
        """Test property forwarding to BaseClient"""
        self.client.base.auth_token = "token"
        self.client.base.mid = "u123"

        self.assertEqual(self.client.auth_token, "token")
        self.assertEqual(self.client.mid, "u123")
        # app_name might be computed, mock it
        with patch.object(self.client.base, "app_name", "LINE/1.0", create=True):
            self.assertEqual(self.client.app_name, "LINE/1.0")

    def test_get_profile(self):
        """Test get_profile returns Pydantic Profile model"""
        # Setup mock return value
        mock_profile = Profile(mid="u123", display_name="Test User")
        self.client.base.talk.get_profile.return_value = mock_profile

        # Call method
        result = self.client.get_profile()

        # Verify
        self.client.base.talk.get_profile.assert_called_once()
        self.assertIsInstance(result, Profile)
        self.assertEqual(result.mid, "u123")
        self.assertEqual(result.display_name, "Test User")

    def test_get_contact(self):
        """Test get_contact returns Pydantic Contact model"""
        mock_contact = Contact(mid="u456", display_name="Friend")
        self.client.base.talk.get_contact.return_value = mock_contact

        result = self.client.get_contact("u456")

        self.client.base.talk.get_contact.assert_called_once_with("u456")
        self.assertIsInstance(result, Contact)
        self.assertEqual(result.mid, "u456")

    def test_get_contacts(self):
        """Test get_contacts returns list of Contact models"""
        mock_contacts = [
            Contact(mid="u1", display_name="A"),
            Contact(mid="u2", display_name="B"),
        ]
        self.client.base.talk.get_contacts.return_value = mock_contacts

        result = self.client.get_contacts(["u1", "u2"])

        self.client.base.talk.get_contacts.assert_called_once_with(["u1", "u2"])
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], Contact)

    def test_get_chat(self):
        """Test get_chat returns Pydantic Chat model"""
        # Client.get_chat calls get_chats internaly
        # We need to mock get_chats
        mock_resp = MagicMock()
        mock_chat = Chat(chat_mid="c123", chat_name="Group")
        mock_resp.chats = [mock_chat]
        self.client.base.talk.get_chats.return_value = mock_resp

        result = self.client.get_chat("c123")

        self.client.base.talk.get_chats.assert_called_once()
        self.assertIsInstance(result, Chat)
        self.assertEqual(result.chat_mid, "c123")

    def test_send_message(self):
        """Test send_message returns Pydantic Message model"""
        mock_msg = Message(id="123", text="hello")
        self.client.base.talk.send_message.return_value = mock_msg

        result = self.client.send_message("uTarget", "hello")

        self.client.base.talk.send_message.assert_called_once_with("uTarget", "hello")
        self.assertIsInstance(result, Message)
        self.assertEqual(result.text, "hello")

    def test_helpers_reply_message(self):
        """Test helpers.reply_message logic"""
        # Mock client for helper
        self.client.base.mid = "uMe"

        # Case 1: Reply to Group (cXXX)
        msg_group = Message(to="cGroup", from_="uSender", text="Hi", id="msg1")
        reply_message(self.client, msg_group, "Reply Group")
        self.client.base.talk.send_message.assert_called_with(
            to="cGroup", text="Reply Group", related_message_id="msg1"
        )

        # Case 2: Reply to 1:1 (Sender is Other) -> Reply to Sender
        msg_friend = Message(to="uMe", from_="uFriend", text="Hi", id="msg2")
        reply_message(self.client, msg_friend, "Reply Friend")
        self.client.base.talk.send_message.assert_called_with(
            to="uFriend", text="Reply Friend", related_message_id="msg2"
        )

        # Case 3: Reply to 1:1 (Sender is Me) -> Reply to Receiver (to)
        msg_me = Message(to="uFriend", from_="uMe", text="Hi", id="msg3")
        reply_message(self.client, msg_me, "Reply Self")
        self.client.base.talk.send_message.assert_called_with(
            to="uFriend", text="Reply Self", related_message_id="msg3"
        )


if __name__ == "__main__":
    unittest.main()
