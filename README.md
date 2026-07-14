# ACE-ASP

Un sottoinsieme di ACE 6.7 con semantica ASP, implementato con CNLWizard.

    ACE-ASP/
    ├── ace_asp.yaml            specifica CNLWizard della grammatica
    ├── grammar_asp.lark        grammatica lark (generata, vedi sotto)
    ├── py_asp.py               funzioni dell'AST (colla verso ace_asp_lib)
    ├── ace_asp_lib/            libreria semantica
    │   ├── terms.py            termini (Var, Const, ArithExpr, SUBJ)
    │   ├── ir.py               IR degli statement ASP + rendering clingo
    │   ├── results.py          NPResult, VPResult, OrVP, DNF (bottom-up)
    │   ├── context.py          stato tra frasi (CTX, registri, skolem)
    │   ├── safety.py           validazione di safety sulla IR
    │   ├── build.py            assemblaggio frase -> statement
    │   └── errors.py           eccezioni con messaggi in ling. naturale
    ├── scripts/generate.py     rigenerazione della grammatica
    ├── tests/                  test (grammatica, libreria, end-to-end)
    └── examples/               testi ACE-ASP di esempio

## Requisiti

    pip install lark clingo pytest
    git clone https://github.com/dodaro/CNLWizard

## Rigenerare la grammatica

CNLWizard non preserva i quantificatori `?` (lookahead) all'interno delle
syntax `/regex/`: lo script di build rigenera la grammatica e ripristina i
terminali lessicali:

    python3 scripts/generate.py <path-a-CNLWizard>

## Compilare un testo ACE-ASP

    PYTHONPATH=<path-a-CNLWizard>/src python3 - <<'PY'
    from CNLWizard.cnl_wizard_compiler import CnlWizardCompiler
    print(CnlWizardCompiler().compile('grammar_asp.lark', 'py_asp.py',
                                      'examples/demo.aceasp'))
    PY

Nota: py_asp.py disattiva il pre-processore di CNLWizard (signatures e
var_substitution) tramite il meccanismo di configurazione del tool, perche'
ACE-ASP definisce le entita' direttamente nel linguaggio e le frasi
interrogative terminano con `?`.

## Test

    PYTHONPATH=<path-a-CNLWizard>/src python3 -m pytest tests/ -q
    python3 tests/test_parse.py
