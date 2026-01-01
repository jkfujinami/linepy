from typing import TYPE_CHECKING, Union, Optional
from .models.talk import Message, Chat

if TYPE_CHECKING:
    from .client import Client


def reply_message(client: "Client", message: Message, text: str) -> Optional[Message]:
    """
    Reply to a message.

    Args:
        client: Client instance
        message: Message object (Pydantic model) to reply to
        text: Text to send

    Returns:
        Sent message object or None
    """
    if not message.from_ or not message.to:
        return None

    # Determine reply target
    # If generic "to" (group/room), reply to that context.
    # But if "to" is myself (1:1 chat), reply to "from_".

    # Logic:
    # If to starts with 'c' (Group) or 'r' (Room), target is 'to'
    # Else (1:1), target is 'from_' unless 'to' is not me?
    # Usually in 1:1, 'to' is me, 'from' is sender. So reply to 'from'.
    # If I sent the message, 'from' is me, 'to' is receiver. Reply to 'to'.

    # Simple logic:
    target = message.to
    if not (target.startswith("c") or target.startswith("r")):
        # 1:1 chat
        # If I am the sender, reply to the receiver (to)
        # If I am the receiver, reply to the sender (from)
        if message.from_ != client.mid:
            target = message.from_
        else:
            target = message.to

    return client.talk.send_message(to=target, text=text, related_message_id=message.id)


def send_chat_message(client: "Client", chat: Chat, text: str) -> Optional[Message]:
    """
    Send a message to a chat.

    Args:
        client: Client instance
        chat: Chat object (Pydantic model)
        text: Text to send

    Returns:
        Sent message object or None
    """
    if not chat.chat_mid:
        return None

    return client.talk.send_message(to=chat.chat_mid, text=text)
