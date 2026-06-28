"""Guards for the production settings module.

Production must never boot with the insecure development SECRET_KEY. Because the
settings module makes that decision at import time, these tests import it in a
fresh subprocess with a controlled environment and assert on the exit code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_IMPORT_PROD = "import config.settings.prod"


def _load_prod_settings(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Import the prod settings in a subprocess; return the completed process."""
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(_BACKEND_DIR),
        # ALLOWED_HOSTS is required by prod with no default; supply it so the test
        # isolates the SECRET_KEY behaviour rather than tripping on hosts.
        "DJANGO_ALLOWED_HOSTS": "example.com",
        **extra_env,
    }
    return subprocess.run(
        [sys.executable, "-c", _IMPORT_PROD],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_prod_refuses_to_boot_with_the_insecure_default_key() -> None:
    # No DJANGO_SECRET_KEY override -> the value falls back to the insecure
    # development default, which production must reject.
    result = _load_prod_settings(extra_env={})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_boots_with_a_real_secret_key() -> None:
    result = _load_prod_settings(
        extra_env={"DJANGO_SECRET_KEY": "a-properly-set-production-secret-value"}
    )

    assert result.returncode == 0, result.stderr
