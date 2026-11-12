"""Independent Ex projection to corroborate the new PTY-captured records."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from motion_cases import CASES, EXCEPTIONS

HERE = Path(__file__).resolve().parent
def capture(case):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p/'f').write_text(case['text'])
        script = re.sub(r'<([^>]+)>', lambda m: '\\<'+m[1]+'>', case['keys'])
        script = script.replace('\\', '\\\\').replace('"', '\\"')
        script = re.sub(r'\\\\<([^>]+)>', r'\\<\1>', script)
        commands = 'source '+str(HERE/'oracle.vim')+'\ncall cursor(1,1)\ncall feedkeys("'+script+'", "xt")\n'
        commands += "call writefile([string([line('.'),col('.')]),getregtype('\"')] + getreg('\"',1,1),'cursor')\nwrite!\nqa!\n"
        (p/'commands.vim').write_text(commands)
        subprocess.run(['vim','--clean','-u','NONE','-i','NONE','-n','-N','-X','-es','-S','commands.vim','f'],cwd=p,check=True,capture_output=True)
        rows=(p/'cursor').read_text().splitlines()
        kind=rows[1]; reg='\n'.join(rows[2:])+('\n' if kind=='V' else '')
        if kind not in ['v','V']: kind,reg='v',''
        return dict(text=(p/'f').read_text(),cursor=json.loads(rows[0]),mode=0,register=[kind,reg]), hashlib.sha256(commands.encode()).hexdigest()

if __name__ == '__main__':
    import sys
    records={}; hashes={}
    for c in CASES+EXCEPTIONS:
        records[c['id']],hashes[c['id']]=capture(c)
    output=Path(sys.argv[1]); output.mkdir(parents=True,exist_ok=True)
    (output/'independent-vim.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    (output/'command-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    frozen=json.loads((HERE/'motion_golden.json').read_text())
    bad=[k for k in records if records[k]!=frozen[k]]
    print('independent Vim:',len(records)-len(bad),'of',len(records),'pass',bad)
    if bad:
        for k in bad: print(k,records[k],frozen[k])
    raise SystemExit(bool(bad))
