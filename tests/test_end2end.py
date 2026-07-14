import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import pytest
pytest.importorskip('CNLWizard')
import clingo
from CNLWizard.cnl_wizard_compiler import CnlWizardCompiler
from ace_asp_lib import AceAspError, UnsafeVariable, ArityMismatch, UnsupportedInContext, reset_context
GRAMMAR = os.path.join(ROOT, 'grammar_asp.lark')
PY = os.path.join(ROOT, 'py_asp.py')

def compile_text(text: str) -> str:
    reset_context()
    tmp = os.path.join(HERE, '_tmp.aceasp')
    with open(tmp, 'w') as f:
        f.write(text)
    try:
        return CnlWizardCompiler().compile(GRAMMAR, PY, tmp)
    finally:
        os.remove(tmp)

def solve(prog: str):
    ctl = clingo.Control(['0'])
    ctl.add('base', [], prog)
    ctl.ground([('base', [])])
    models = []
    ctl.solve(on_model=lambda m: models.append(sorted(map(str, m.symbols(shown=True)))))
    return models

def test_facts_and_skolem():
    prog = compile_text('John waits. There is a person X. X is tall.')
    assert 'waits(john).' in prog and 'person(sk1).' in prog and ('tall(sk1).' in prog)
    assert solve(prog)

def test_classic_naf_rule():
    prog = compile_text('Mary is a person. If a person P is not provably guilty then P is innocent.')
    assert 'innocent(P) :- person(P), not guilty(P).' in prog
    [m] = solve(prog)
    assert 'innocent(mary)' in m

def test_functional_genitive():
    prog = compile_text('John is a person. The age of John is 32. If the age of a person P is Y and Y >= 18 then P is an adult.')
    [m] = solve(prog)
    assert 'adult(john)' in m

def test_graph_coloring_equiv():
    prog = compile_text('Node1 is a node. Node2 is a node. Node3 is a node. Node1 is connected-to Node2. Node2 is connected-to Node3. Node1 is connected-to Node3. Every node is red or is green or is blue. It is false that a node X is connected-to a node Y and X is red and Y is red. It is false that a node X is connected-to a node Y and X is green and Y is green. It is false that a node X is connected-to a node Y and X is blue and Y is blue.')
    hand = solve('node(node1). node(node2). node(node3). connected_to(node1,node2). connected_to(node2,node3). connected_to(node1,node3). red(X) | green(X) | blue(X) :- node(X). :- connected_to(X,Y), red(X), red(Y). :- connected_to(X,Y), green(X), green(Y). :- connected_to(X,Y), blue(X), blue(Y).')
    proj = lambda ms: sorted((tuple(sorted((a for a in m if a.split('(')[0] in ('red', 'green', 'blue')))) for m in ms))
    assert proj(solve(prog)) == proj(hand) and len(hand) == 6

def test_choice_aggregate_weak():
    prog = compile_text('There is an employee E1. There is a team T1. There is a team T2. Every employee can be assigned-to a team. Every employee is assigned-to exactly 1 team.')
    models = solve(prog)
    assert len(models) == 2

def test_modal_must():
    prog = compile_text('There is an employee E1. There is a team T1. Every employee can be assigned-to a team. Every employee must be assigned-to a team.')
    models = solve(prog)
    assert len(models) == 1 and any(('assigned_to' in a for a in models[0]))

def test_should_weak():
    prog = compile_text('Every server should not be overloaded.')
    assert ':~ server(V1), overloaded(V1). [1@1,V1]' in prog

def test_coordination_precedence():
    prog = compile_text('If a screen X blinks or X waits, and Mary enters a card then Mary is happy.')
    assert prog.count('happy(mary) :-') == 2

def test_queries():
    assert solve(compile_text('John is a man. Bob is a man. John waits. Every man that waits is happy. Which man is happy?')) == [['ans(john)']]
    assert solve(compile_text('John is a man. Bob is a man. John waits. Bob waits. How many man waits?')) == [['ans(2)']]
    assert solve(compile_text('John waits. Does John wait?')) == [['ans']]

def test_error_unsafe_variable():
    with pytest.raises(UnsafeVariable):
        compile_text('If X is not provably guilty then X is innocent.')

def test_error_arity_mismatch():
    with pytest.raises(ArityMismatch):
        compile_text('John enters a card. Mary enters.')

def test_error_existential_in_head():
    with pytest.raises(UnsupportedInContext):
        compile_text('If a man X waits then X owns a dog.')

def test_error_every_owns_existential():
    with pytest.raises(UnsupportedInContext):
        compile_text('Every man owns a dog.')
