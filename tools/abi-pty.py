#!/usr/bin/env python3
"""tools/abi-pty.py ARGV... PATH: the ced session of tools/check-editor.py (its pty of 80 x 24 and its KEYS) with
ARGV in place of ced, so tools/abi-gap.sh can trace it: ARGV is the tracer, then ced, and PATH the file ced opens.
Writes what the pty showed, then `status N`."""
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location("check_editor", os.path.join(os.path.dirname(__file__), "check-editor.py"))
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)
argv = sys.argv[1:]
execv = os.execv
os.execv = lambda path, args: execv(argv[0], argv[:-1] + args[1:])   # check-editor.py's child: execv(ced, [ced, PATH])
status, shown = editor.run(argv[0], argv[-1])
sys.stdout.buffer.write(shown + b"status %d\n" % status)
