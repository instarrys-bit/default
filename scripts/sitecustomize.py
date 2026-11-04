"""Automatically install the production write guard for workflow Python processes."""
import os
if os.environ.get("AUTOMATION_WRITE_GUARD") == "1":
    import sys
    sys.dont_write_bytecode = True
    from fenced_file_writer import install_write_guard
    install_write_guard()
