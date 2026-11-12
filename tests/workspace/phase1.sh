# tests/workspace/phase1.sh: boot 1 of the workspace recovery acceptance (docs/guide/workspace-recovery.md).
# Run by cish as the image's sh under `grant disk`. Every native command reports `ws-step NAME STATUS`, every file
# digest `ws-hash LABEL SHA256 FILE`; tools/check-workspace.py reads only those lines.
echo ws-phase 1 begin
mkdir -p /home/work
echo ws-step mkdir-work $?
mkdir "/home/work/proj one"
echo ws-step mkdir-proj $?
cd "/home/work/proj one"
echo ws-step cd-proj $?
cat > hello.ci <<'SRC'
void main() {
    I64 n = 6 * 7;
    "workspace result: {n} ok\n";
}
// SPDX-License-Identifier: Apache-2.0
SRC
echo ws-step write-src $?
cp hello.ci hello.ci.bak
echo ws-step backup-src $?
/home/opt/cint/cib out-1 hello.ci
echo ws-step cib-1 $?
./out-1 > run-1.out
echo ws-step run-1 $?
cat run-1.out
cmp run-1.out /fx/expected.txt
echo ws-step cmp-run-1 $?
echo ws-hash src $(sha256sum hello.ci)
echo ws-hash bak $(sha256sum hello.ci.bak)
echo ws-hash exe1 $(sha256sum out-1)
echo ws-hash run-1-out $(sha256sum run-1.out)
sync
echo ws-step sync-1 $?
echo ws-phase 1 end
