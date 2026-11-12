# tests/rs/guest/sh/noleak.sh, in the guest as /rs/noleak: about_console's check that `touch /tmp/leak`, typed while
# the About sheet was up, never reached the shell (DN-43). Status 0 when /tmp holds no leak.
[ -z "$(ls /tmp | grep leak)" ]
