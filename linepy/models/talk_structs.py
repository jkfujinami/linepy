# -*- coding: utf-8 -*-
"""Re-export shim: all Talk-service structs now live in the single
generated module ``_generated.py`` (built from line.thrift + chrline.thrift,
see tools/generate_models.py). Kept as its own file so existing
``from .talk_structs import ...`` imports keep working unchanged.
"""
from ._generated import *  # noqa: F401,F403
