# tests/rs/guest/sh/view.sh, in the guest as /rs/view.sh: View's decoder at the 512 MiB floor (RS-VIEW). The digest
# line of a 3840 x 2160 PNG is the one guest.py png wrote beside it. 1: cview -d failed; 2: another digest.
cview -d /rs/4k.png > /tmp/rs.view || exit 1
cmp -s /tmp/rs.view /rs/4k.png.want || exit 2
exit 0
