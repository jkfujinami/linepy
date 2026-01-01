# -*- coding: utf-8 -*-
"""Pydantic models for LINE Talk API responses.

These models wrap the auto-generated thrift structures and add convenience methods.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from .talk_structs import *

# Export common types for easier access
# (They are already imported via * above)

# Add any manual helpers or extensions here if needed
# For now, most things are well-defined in talk_structs.py
