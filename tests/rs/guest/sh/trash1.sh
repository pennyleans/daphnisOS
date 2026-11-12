# tests/rs/guest/sh/trash1.sh, in the guest as /rs/t1: the trash leg's link on the volume, then Index on its folder
# (FF 3h). The window types only `sh /rs/t1`.
mkdir -p /home/rs/notes
echo a > /home/rs/notes/a.txt
cd /home/rs || exit 1
ln -s notes/a.txt link
finder /home/rs
