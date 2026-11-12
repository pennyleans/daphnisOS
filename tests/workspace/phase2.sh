# tests/workspace/phase2.sh: boot 2 of the workspace recovery acceptance. It checks what boot 1 saved, makes a
# deliberate syntax error (the one expected nonzero native command, cib-bad), restores the source from its backup and
# rebuilds. Then it writes and syncs the final marker, prints ws-marker final-synced only after sync succeeded, and
# waits: the host stops this QEMU process without a guest shutdown (the stop is the end of this boot).
echo ws-phase 2 begin
cd "/home/work/proj one"
echo ws-step cd-proj $?
echo ws-hash v-src $(sha256sum hello.ci)
echo ws-hash v-bak $(sha256sum hello.ci.bak)
echo ws-hash v-exe1 $(sha256sum out-1)
./out-1 > saved-run.out
echo ws-step run-saved $?
echo ws-hash run-saved-out $(sha256sum saved-run.out)
echo "void broken( {" >> hello.ci
echo ws-step break-src $?
/home/opt/cint/cib out-bad hello.ci > bad.log 2>&1
echo ws-step cib-bad $?
echo ws-diag-begin
cat bad.log
echo ws-diag-end
echo ws-hash bak-after-fail $(sha256sum hello.ci.bak)
echo ws-hash exe1-after-fail $(sha256sum out-1)
./out-1 > after-fail.out
echo ws-step run-after-fail $?
echo ws-hash run-after-fail-out $(sha256sum after-fail.out)
cp hello.ci.bak hello.ci
echo ws-step restore-src $?
echo ws-hash restored-src $(sha256sum hello.ci)
/home/opt/cint/cib out-2 hello.ci
echo ws-step cib-2 $?
echo ws-hash exe2 $(sha256sum out-2)
cmp out-1 out-2
echo ws-step cmp-exe $?
./out-2 > run-2.out
echo ws-step run-2 $?
echo ws-hash run-2-out $(sha256sum run-2.out)
cmp run-1.out run-2.out
echo ws-step cmp-run-2 $?
echo ws-phase 2 end
echo ws-phase 3 begin
printf 'workspace recovery final marker\n' > final.marker
echo ws-step write-marker $?
sync
s=$?
echo ws-step sync-final $s
test $s = 0 && echo ws-marker final-synced
sleep 3600
