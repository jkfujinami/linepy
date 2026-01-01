from __future__ import annotations
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import IntEnum

# Import all auto-generated models from square_structs.py (Snake Case)
from .square_structs import *

# Manual definitions for types that are missing/incomplete in Thrift
# MessageStatusType is an empty enum in chrline.thrift, so we treat it as int
MessageStatusType = int
_any = Any

# Rebuild models to resolve forward references
FetchMyEventsResponse.model_rebuild()
FetchSquareChatEventsResponse.model_rebuild()
SquareEvent.model_rebuild()
SquareEventPayload.model_rebuild()

# Note: All other models like SquareEvent, FetchMyEventsResponse are imported from square_structs.py
