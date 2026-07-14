import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import clingo
from ace_asp_lib import Var, Const, SUBJ, Polarity, Literal, Builtin, CountAggregate, RuleIR, ChoiceIR, WeakIR, QueryIR, render_program, NPResult, VPResult, Predication, Quant, QuantKind, Modality, flatten, CTX, reset_context, ConceptKind, check, UnsafeVariable, ArityMismatch, ReservedWord, MultipleQueries

def solve(prog: str):
    ctl = clingo.Control(['0'])
    ctl.add('base', [], prog)
    ctl.ground([('base', [])])
    models = []
    ctl.solve(on_model=lambda m: models.append(sorted(map(str, m.symbols(shown=True)))))
    return models

def setup_function(_):
    reset_context()

def test_fact_rule_constraint():
    X = Var('X')
    prog = render_program([RuleIR(head=[Literal('person', (Const.of('John'),))]), RuleIR(head=[Literal('guilty', (Const.of('Mary'),))]), RuleIR(head=[Literal('person', (Const.of('Mary'),))]), RuleIR(head=[Literal('innocent', (X,))], body=[Literal('person', (X,)), Literal('guilty', (X,), Polarity.NAF)]), RuleIR(body=[Literal('innocent', (X,)), Literal('guilty', (X,))])])
    [model] = solve(prog)
    assert 'innocent(john)' in model and 'innocent(mary)' not in model

def test_strong_negation():
    X = Var('X')
    prog = render_program([RuleIR(head=[Literal('stone', (Const('s1'),))]), RuleIR(head=[Literal('moves', (X,), Polarity.SNEG)], body=[Literal('stone', (X,))])])
    [model] = solve(prog)
    assert '-moves(s1)' in model

def test_disjunctive_head_and_choice():
    X, T = (Var('X'), Var('T'))
    prog = render_program([RuleIR(head=[Literal('node', (Const('n1'),))]), RuleIR(head=[Literal('red', (X,)), Literal('green', (X,))], body=[Literal('node', (X,))]), RuleIR(head=[Literal('employee', (Const('e1'),))]), RuleIR(head=[Literal('team', (Const('t1'),))]), ChoiceIR(element=Literal('assigned_to', (X, T)), condition=[Literal('team', (T,))], body=[Literal('employee', (X,))])])
    models = solve(prog)
    assert len(models) == 4

def test_gq_aggregate_constraint():
    E, T = (Var('E'), Var('T'))
    prog = render_program([RuleIR(head=[Literal('employee', (Const('e1'),))]), RuleIR(head=[Literal('team', (Const('t1'),))]), RuleIR(head=[Literal('team', (Const('t2'),))]), ChoiceIR(element=Literal('assigned_to', (E, T)), condition=[Literal('team', (T,))], body=[Literal('employee', (E,))]), RuleIR(body=[Literal('employee', (E,)), CountAggregate(terms=(T,), condition=(Literal('assigned_to', (E, T)),), cmp='!=', guard=1)])])
    models = solve(prog)
    assert len(models) == 2

def test_weak_constraint():
    S = Var('S')
    prog = render_program([RuleIR(head=[Literal('server', (Const('s1'),))]), ChoiceIR(element=Literal('overloaded', (S,)), body=[Literal('server', (S,))]), WeakIR(body=[Literal('server', (S,)), Literal('overloaded', (S,))], terms=(S,))])
    ctl = clingo.Control(['0'])
    ctl.add('base', [], prog)
    ctl.ground([('base', [])])
    costs = []
    ctl.solve(on_model=lambda m: costs.append(tuple(m.cost)))
    assert (0,) in costs or () in costs

def test_query_rendering():
    X = Var('X')
    q = QueryIR(rules=[RuleIR(head=[Literal('ans', (X,))], body=[Literal('man', (X,)), Literal('waits', (X,))])], arity=1)
    prog = render_program([RuleIR(head=[Literal('man', (Const('john'),))]), RuleIR(head=[Literal('waits', (Const('john'),))]), q])
    [model] = solve(prog)
    assert model == ['ans(john)']

def test_builtin_and_arith():
    from ace_asp_lib import ArithExpr
    X, Y = (Var('X'), Var('Y'))
    prog = render_program([RuleIR(head=[Literal('age', (Const('john'), 32))]), RuleIR(head=[Literal('person', (Const('john'),))]), RuleIR(head=[Literal('adult', (X,))], body=[Literal('person', (X,)), Literal('age', (X, Y)), Builtin('>=', Y, 18)])])
    [model] = solve(prog)
    assert 'adult(john)' in model

def test_unsafe_naf_rejected():
    X = Var('X')
    r = RuleIR(head=[Literal('innocent', (X,))], body=[Literal('guilty', (X,), Polarity.NAF)])
    with pytest.raises(UnsafeVariable):
        check(r)

def test_sneg_binds():
    X = Var('X')
    r = RuleIR(head=[Literal('innocent', (X,))], body=[Literal('guilty', (X,), Polarity.SNEG)])
    check(r)

def test_unsafe_head_rejected():
    X, Y = (Var('X'), Var('Y'))
    r = RuleIR(head=[Literal('likes', (X, Y))], body=[Literal('person', (X,))])
    with pytest.raises(UnsafeVariable):
        check(r)

def test_aggregate_result_binds():
    N, X = (Var('N'), Var('X'))
    q = RuleIR(head=[Literal('ans', (N,))], body=[CountAggregate(terms=(X,), condition=(Literal('man', (X,)),), result=N)])
    check(q)

def test_vp_apply_saturation():
    Y = Var('Y')
    obj = NPResult(term=Y, restrictors=[Literal('dog', (Y,))], quant=Quant(QuantKind.EXIST), head_noun='dog')
    vp = VPResult(preds=[Predication(Literal('owns', (SUBJ, Y)), [obj])])
    body, gq = vp.apply(Var('X'))
    assert Literal('owns', (Var('X'), Y)) in body
    assert Literal('dog', (Y,)) in body and (not gq)

def test_vp_apply_gq_object_bubbles_up():
    E = Var('E')
    obj = NPResult(term=E, restrictors=[Literal('employee', (E,))], quant=Quant(QuantKind.GQ, 'at least', 2))
    vp = VPResult(preds=[Predication(Literal('has', (SUBJ, E)), [obj])])
    body, gq = vp.apply(Var('T'))
    [(lit, gnp, extra)] = gq
    assert lit == Literal('has', (Var('T'), E)) and gnp is obj and (extra == [])
    assert body == []

def test_flatten():
    assert flatten([[1, [2, None]], 3, None]) == [1, 2, 3]

def test_registry_arity_and_verb_unification():
    n1 = CTX.registry.declare('enters', 2, ConceptKind.VERB)
    n2 = CTX.registry.declare('enter', 2, ConceptKind.VERB)
    assert n1 == n2 == 'enters'
    with pytest.raises(ArityMismatch):
        CTX.registry.declare('enters', 1, ConceptKind.VERB)
    with pytest.raises(ReservedWord):
        CTX.registry.declare('every', 1, ConceptKind.NOUN)
    n3 = CTX.registry.declare('fill-in', 2, ConceptKind.VERB)
    n4 = CTX.registry.declare('fills-in', 2, ConceptKind.VERB)
    assert n3 == n4 == 'fill_in'

def test_skolem_across_sentences():
    c = CTX.bind_skolem('X')
    assert CTX.resolve_variable('X') == c
    assert CTX.resolve_variable('Y') == Var('Y')

def test_single_query():
    q = QueryIR(rules=[], arity=0)
    CTX.set_query(q)
    with pytest.raises(MultipleQueries):
        CTX.set_query(q)
