import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
TERMINALS = {'WORD': '/(?!(?:a|an|one|the|is|be|does|not|provably|can|may|must|should|no|every|each|that|who|which|to|of|if|then|there|it|false|possible|and|or|at|least|most|more|less|than|exactly)(?![a-z0-9_-]))[a-z][a-z0-9_]*(-[a-z0-9_]+)*/', 'PROPER_NAME': '/(?!(?:A|An|One|The|Is|No|Every|Each|If|It|There|Does|Which|How)(?![a-zA-Z0-9_-]))[A-Z][a-z][a-zA-Z0-9_]*(-[A-Z][a-z][a-zA-Z0-9_]*)*/', 'INDEF_DET': '/(a|an|one|1|A|An|One)(?![a-zA-Z0-9_-])/', 'UNIV_DET': '/(every|each|Every|Each)(?![a-zA-Z0-9_-])/', 'NO_DET': '/(no|No)(?![a-zA-Z0-9_-])/', 'MODAL_WORD': '/(can|may|must|should)(?![a-zA-Z0-9_-])/', 'GQ_WORD': '/(at least|at most|more than|less than|exactly)(?![a-zA-Z0-9_-])/', 'REL_PRON': '/(that|who|which)(?![a-zA-Z0-9_-])/'}

def repair(grammar: str) -> str:
    for name, regex in TERMINALS.items():
        grammar = re.sub(f'^{name}: .*$', f'{name}: {regex}', grammar, flags=re.M)
    return grammar

def main():
    ap = argparse.ArgumentParser(description='Genera grammar_asp.lark da ace_asp.yaml con CNLWizard e ripristina i terminali lessicali con lookahead, che il generatore non preserva nelle syntax /regex/.')
    ap.add_argument('cnlwizard', help='path alla cartella di CNLWizard')
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(Path(args.cnlwizard) / 'src' / 'main.py'), '-g', str(ROOT / 'ace_asp.yaml'), tmp], check=True)
        grammar = (Path(tmp) / 'grammar_asp.lark').read_text()
        (ROOT / 'grammar_asp.lark').write_text(repair(grammar))
        generated_py = Path(tmp) / 'py_asp.py'
        if not (ROOT / 'py_asp.py').exists():
            shutil.copy(generated_py, ROOT / 'py_asp.py')
    print('grammar_asp.lark rigenerata e riparata.')
if __name__ == '__main__':
    main()
