#!/bin/sh
# tools/core-bracket-oracle.sh ORACLE ARG...: busybox's `[` for check-core.sh (CT-5): busybox-oracle (built by
# user/busybox/oracle.sh, DOS-3) has no `[` applet, so its ash runs its builtin `[`, test_main, the same code as the
# applet.
o=$1
shift
exec "$o" ash -c '[ "$@"' '[' "$@"
