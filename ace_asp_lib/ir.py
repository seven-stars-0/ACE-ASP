from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union
from .terms import Term, Var, render_term, vars_of_term, substitute

class Polarity(Enum):
    POS = auto()
    SNEG = auto()
    NAF = auto()
    NAF_SNEG = auto()

@dataclass(frozen=True)
class Literal:
    pred: str
    args: tuple[Term, ...] = ()
    polarity: Polarity = Polarity.POS

    def with_polarity(self, p: Polarity) -> 'Literal':
        return Literal(self.pred, self.args, p)

    def substituted(self, mapping) -> 'Literal':
        return Literal(self.pred, tuple((substitute(a, mapping) for a in self.args)), self.polarity)

    def vars(self) -> set[str]:
        return set().union(*(vars_of_term(a) for a in self.args)) if self.args else set()

    def render(self) -> str:
        atom = self.pred if not self.args else f'{self.pred}({','.join((render_term(a) for a in self.args))})'
        return {Polarity.POS: atom, Polarity.SNEG: f'-{atom}', Polarity.NAF: f'not {atom}', Polarity.NAF_SNEG: f'not -{atom}'}[self.polarity]

@dataclass(frozen=True)
class Builtin:
    op: str
    left: Term
    right: Term

    def substituted(self, mapping) -> 'Builtin':
        return Builtin(self.op, substitute(self.left, mapping), substitute(self.right, mapping))

    def vars(self) -> set[str]:
        return vars_of_term(self.left) | vars_of_term(self.right)

    def render(self) -> str:
        return f'{render_term(self.left)} {self.op} {render_term(self.right)}'

@dataclass(frozen=True)
class CountAggregate:
    terms: tuple[Term, ...]
    condition: tuple[Literal, ...]
    cmp: str | None = None
    guard: Term | None = None
    result: Var | None = None

    def vars(self) -> set[str]:
        out = set()
        if self.guard is not None:
            out |= vars_of_term(self.guard)
        return out

    def substituted(self, mapping):
        return self

    def render(self) -> str:
        inner = f'#count{{ {','.join((render_term(t) for t in self.terms))} : {', '.join((l.render() for l in self.condition))} }}'
        if self.result is not None:
            return f'{self.result.name} = {inner}'
        return f'{inner} {self.cmp} {render_term(self.guard)}'
BodyElem = Union[Literal, Builtin, CountAggregate]

@dataclass
class RuleIR:
    head: list[Literal] = field(default_factory=list)
    body: list[BodyElem] = field(default_factory=list)

    def render(self) -> str:
        h = ' | '.join((l.render() for l in self.head))
        b = ', '.join((e.render() for e in self.body))
        if not self.body:
            return f'{h}.'
        if not self.head:
            return f':- {b}.'
        return f'{h} :- {b}.'

@dataclass
class ChoiceIR:
    element: Literal
    condition: list[Literal] = field(default_factory=list)
    body: list[BodyElem] = field(default_factory=list)
    lower: int | None = None
    upper: int | None = None

    def render(self) -> str:
        cond = f' : {', '.join((l.render() for l in self.condition))}' if self.condition else ''
        core = f'{{ {self.element.render()}{cond} }}'
        if self.lower is not None:
            core = f'{self.lower} {core}'
        if self.upper is not None:
            core = f'{core} {self.upper}'
        if self.body:
            return f'{core} :- {', '.join((e.render() for e in self.body))}.'
        return f'{core}.'

@dataclass
class WeakIR:
    body: list[BodyElem]
    weight: int = 1
    level: int = 1
    terms: tuple[Term, ...] = ()

    def render(self) -> str:
        b = ', '.join((e.render() for e in self.body))
        ts = ''.join((f',{render_term(t)}' for t in self.terms))
        return f':~ {b}. [{self.weight}@{self.level}{ts}]'

@dataclass
class QueryIR:
    rules: list[RuleIR]
    arity: int

    def render(self) -> str:
        lines = [r.render() for r in self.rules]
        lines.append(f'#show ans/{self.arity}.')
        return '\n'.join(lines)
StatementIR = Union[RuleIR, ChoiceIR, WeakIR, QueryIR]

def render_program(statements: list[StatementIR]) -> str:
    return '\n'.join((s.render() for s in statements)) + '\n'
