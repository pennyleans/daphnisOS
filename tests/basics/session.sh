# tests/basics/session.sh: the basics session (docs/specs/2026-11-07-bp-basics.md section 5, BP-4), under cish on
# Linux and under Daphnis. cish starts in the image root, so `cd b`. Descriptor 0 is the session itself, so every tool reads a file or its operands, and
# cless writes to a pipe, so it copies.
cd b
cless lines.txt | cat
cat odd.txt | cless | cat
cless missing.txt
echo "status $?"
ccalc '2 ^ 62 + 1'
ccalc 1 / 3
ccalc '-7 % 3'
ccalc < calc.txt
ccalc < calc-bad.txt
echo "status $?"
cview -d img/png-c6-d16-i1.png
cview -d img/png-c3-d4-i0.png
cview -d img/png-trns-rgb.png
cview -d img/png-wide.png
cview -d img/qoi-rgba.qoi
cview -d img/pnm-p6-16.ppm
cview -d img/bad-crc.png
echo "status $?"
exit
