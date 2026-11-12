# tests/rs/guest/sh/trash2.sh, in the guest as /rs/t2: the link is in the trash with its record and gone from its
# folder.
[ -L /home/.trash/items/link ] && [ -f /home/.trash/records/link ] && [ ! -L /home/rs/link ]
