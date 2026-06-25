"""
Cython compilation setup.
Compiles all Python business logic files into .so binary extensions.
The compiled .so files are NOT readable — they are native machine code.
"""
import os
import sys
from setuptools import setup, find_packages
from Cython.Build import cythonize

# ─── Files to compile with Cython ──────────────────────────
# These are your core business logic files that contain proprietary code.
# Templates, static files, and __init__.py are NOT compiled.
COMPILE_FILES = [
    "app/database.py",
    "app/models/schemas.py",
    "app/api/agent.py",
    "app/api/analytics.py",
    "app/api/apikeys.py",
    "app/api/campaigns.py",
    "app/api/devices.py",
    "app/api/media.py",
    "app/api/pages.py",
    "app/api/tasks.py",
    "app/api/tuning.py",
]

# Verify all files exist
for f in COMPILE_FILES:
    if not os.path.exists(f):
        print(f"ERROR: File not found: {f}")
        sys.exit(1)

setup(
    name="wa-campaign-dashboard",
    ext_modules=cythonize(
        COMPILE_FILES,
        compiler_directives={
            "language_level": "3",      # Python 3
            "boundscheck": False,       # Disable bounds checking for speed
            "wraparound": False,        # Disable negative indexing for speed
            "annotation_typing": False, # <--- THE MAGIC FIX: Ignores FastAPI type hints
        },
        build_dir="build_cython",
    ),
    packages=find_packages(),
)