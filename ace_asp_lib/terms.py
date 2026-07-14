from __future__ import annotations
from dataclasses import dataclass
from typing import Union

def normalize_name(name: str) -> str:
    return name.strip().lower().replace('-', '_')

@dataclass(frozen=True)
class Var:
    name: str

@dataclass(frozen=True)
class Const:
    name: str

    @staticmethod
    def of(surface: str) -> 'Const':
        return Const(normalize_name(surface))

@dataclass(frozen=True)
class ArithExpr:
    op: str
    left: 'Term'
    right: 'Term'
Term = Union[Var, Const, int, ArithExpr]
SUBJ = Var('_SUBJ')

def render_term(t: Term) -> str:
    if isinstance(t, Var):
        return t.name
    if isinstance(t, Const):
        return t.name
    if isinstance(t, int):
        return str(t)
    if isinstance(t, ArithExpr):
        return f'({render_term(t.left)}{t.op}{render_term(t.right)})'
    raise TypeError(f'termine sconosciuto: {t!r}')

def vars_of_term(t: Term) -> set[str]:
    if isinstance(t, Var):
        return {t.name}
    if isinstance(t, ArithExpr):
        return vars_of_term(t.left) | vars_of_term(t.right)
    return set()

def substitute(t: Term, mapping: dict[Var, Term]) -> Term:
    if isinstance(t, Var):
        return mapping.get(t, t)
    if isinstance(t, ArithExpr):
        return ArithExpr(t.op, substitute(t.left, mapping), substitute(t.right, mapping))
    return t
