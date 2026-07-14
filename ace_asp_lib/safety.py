from __future__ import annotations
from .ir import RuleIR, ChoiceIR, WeakIR, Literal, Builtin, CountAggregate, Polarity
from .errors import UnsafeVariable

def _binding_vars(body) -> set[str]:
    from .terms import Var, vars_of_term
    bound: set[str] = set()
    for e in body:
        if isinstance(e, Literal) and e.polarity in (Polarity.POS, Polarity.SNEG):
            bound |= e.vars()
        elif isinstance(e, CountAggregate) and e.result is not None:
            bound.add(e.result.name)
    changed = True
    while changed:
        changed = False
        for e in body:
            if isinstance(e, Builtin) and e.op == '=':
                for a, b in ((e.left, e.right), (e.right, e.left)):
                    if isinstance(a, Var) and a.name not in bound and (vars_of_term(b) <= bound):
                        bound.add(a.name)
                        changed = True
    return bound

def _needing_vars(body) -> set[str]:
    need: set[str] = set()
    for e in body:
        if isinstance(e, Literal) and e.polarity in (Polarity.NAF, Polarity.NAF_SNEG):
            need |= e.vars()
        elif isinstance(e, Builtin):
            need |= e.vars()
        elif isinstance(e, CountAggregate):
            need |= e.vars()
    return need

def check_rule(rule: RuleIR, sentence: str | None=None) -> None:
    bound = _binding_vars(rule.body)
    head_vars = set().union(*(l.vars() for l in rule.head)) if rule.head else set()
    unsafe = (head_vars | _needing_vars(rule.body)) - bound
    if unsafe:
        where = 'un fatto' if not rule.body else 'un constraint' if not rule.head else 'una regola'
        raise UnsafeVariable(unsafe, where, sentence)

def check_choice(choice: ChoiceIR, sentence: str | None=None) -> None:
    bound = _binding_vars(choice.body) | _binding_vars(choice.condition)
    unsafe = (choice.element.vars() | _needing_vars(choice.body)) - bound
    if unsafe:
        raise UnsafeVariable(unsafe, 'una choice rule', sentence)

def check_weak(weak: WeakIR, sentence: str | None=None) -> None:
    bound = _binding_vars(weak.body)
    need = _needing_vars(weak.body)
    for t in weak.terms:
        from .terms import vars_of_term
        need |= vars_of_term(t)
    unsafe = need - bound
    if unsafe:
        raise UnsafeVariable(unsafe, 'un weak constraint', sentence)

def check(stmt, sentence: str | None=None) -> None:
    if isinstance(stmt, RuleIR):
        check_rule(stmt, sentence)
    elif isinstance(stmt, ChoiceIR):
        check_choice(stmt, sentence)
    elif isinstance(stmt, WeakIR):
        check_weak(stmt, sentence)
