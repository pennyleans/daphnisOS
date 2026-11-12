# tests/workspace/phase3.sh: boot 3 of the workspace recovery acceptance. A new QEMU process on the volume boot 2 was
# stopped on, without a guest shutdown: the final marker, the source, its backup and both executables must be there
# and the executables must run as they did.
echo ws-phase 3 verify begin
cd "/home/work/proj one"
echo ws-step cd-proj $?
echo ws-hash f-marker $(sha256sum final.marker)
echo ws-hash f-src $(sha256sum hello.ci)
echo ws-hash f-bak $(sha256sum hello.ci.bak)
echo ws-hash f-exe1 $(sha256sum out-1)
echo ws-hash f-exe2 $(sha256sum out-2)
./out-1 > f-run-1.out
echo ws-step f-run-1 $?
echo ws-hash f-run-1-out $(sha256sum f-run-1.out)
./out-2 > f-run-2.out
echo ws-step f-run-2 $?
echo ws-hash f-run-2-out $(sha256sum f-run-2.out)
echo ws-phase 3 verify end
