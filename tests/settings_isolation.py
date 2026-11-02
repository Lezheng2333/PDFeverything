"""Isolate QSettings for GUI tests.

On macOS, QSettings("org", "app") uses NativeFormat and ignores
setPath(IniFormat). This module flips the application to an INI store backed by
a temporary directory before any widget is created, so test runs never touch the
user's real plist/registry.
"""

import os
import tempfile

from PyQt6.QtCore import QSettings

_TMP = tempfile.TemporaryDirectory(prefix="pdfeverything-test-settings-")
os.environ["PDFEVERYTHING_SETTINGS_INI"] = "1"
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _TMP.name)
