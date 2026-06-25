import sys

from app.app_factory import create_app
from app.main_compat import install_main_compat_exports

app = create_app()

# Compatibility exports for existing tests and scripts that monkeypatch app.main.
install_main_compat_exports(sys.modules[__name__])
