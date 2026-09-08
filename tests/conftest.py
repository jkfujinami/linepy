import os
import sys
import warnings

# Ensure the repo root is importable when tests run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The generated pydantic models emit class-based-config deprecation noise.
warnings.filterwarnings("ignore", category=DeprecationWarning)
