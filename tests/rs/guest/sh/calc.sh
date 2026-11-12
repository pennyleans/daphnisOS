# tests/rs/guest/sh/calc.sh, in the guest as /rs/calc.sh: core/calc.ci through ccalc, the arithmetic Calc's window
# shares (RS-CALC; the values of tests/rs/calc_test.ci). Exits K at the first case K that is not as written.
[ "$(ccalc '12 * 4')" = 48 ] || exit 1
[ "$(ccalc '48 / 7')" = '~6.857142857' ] || exit 2
[ "$(ccalc '0.1 + 0.2')" = 0.3 ] || exit 3
[ "$(ccalc '-7 % 3')" = 2 ] || exit 4
[ "$(ccalc 'hex 255')" = 0xff ] || exit 5
ccalc '2 ^ 63' > /tmp/rs.calc 2> /tmp/rs.err && exit 6
ccalc '7 / 0' > /tmp/rs.calc 2> /tmp/rs.err && exit 7
exit 0
