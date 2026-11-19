"""Settings for the test suite: development defaults, so tests never depend
on a local .env (CI has none). Values already in the environment still win."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from config.settings import *  # noqa: E402,F403
