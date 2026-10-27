"""Pytest configuration for the repo-root test suite.

Puts the integration directory on ``sys.path`` so the vendored
``purelinepro_ble`` library imports as a standalone top-level package —
without triggering the Home Assistant integration ``__init__.py`` (which
requires ``homeassistant`` to be installed).
"""

import pathlib
import sys

_INTEGRATION_DIR = pathlib.Path(__file__).parent / "custom_components" / "novy_pureline_pro"
if str(_INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEGRATION_DIR))
