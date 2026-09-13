from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union
from .terms import Term, Var, render_term, vars_of_term, substitute

# Tutte le combinazioni delle due negazioni
class Polarity(Enum):
    POS = auto() # Positive
    SNEG = auto() # Strong Negation
    NAF = auto() # Negation as failure
    NAF_SNEG = auto() # Negation as failure della Strong negation

# Letterale, composto da predicato, i suoi argomenti (opzionali), e la sua polarità
@dataclass(frozen=True)
class Literal:
    pred: str
    args: tuple[Term, ...] = ()
    polarity: Polarity = Polarity.POS

    # Restituisce una copia con polarità p
    def with_polarity(self, p: Polarity) -> 'Literal':
        return Literal(self.pred, self.args, p)

    # Restituisce una copia con gli argomenti sostituiti (per la saturazione del soggetto)
    def substituted(self, mapping) -> 'Literal':
        return Literal(self.pred, tuple((substitute(a, mapping) for a in self.args)), self.polarity)

    # Restituisce l'insieme di tutti i nomi delle variabili negli argomenti
    def vars(self) -> set[str]:
        return set().union(*(vars_of_term(a) for a in self.args)) if self.args else set()

    # Produce la stringa ASP corrispondente, con argomenti (se ne ha) e con la giusta polarità
    def render(self) -> str:
        atom = self.pred if not self.args else f'{self.pred}({','.join((render_term(a) for a in self.args))})'
        return {Polarity.POS: atom, Polarity.SNEG: f'-{atom}', Polarity.NAF: f'not {atom}', Polarity.NAF_SNEG: f'not -{atom}'}[self.polarity]

# Rappresenta un confronto o uguaglianza tra due termini
# Permette cose come "X >= 18" oppure "X = Y + 1" nel corpo di una regola
@dataclass(frozen=True)
class Builtin:
    op: str
    left: Term
    right: Term

    # Analoghi a Literal
    def substituted(self, mapping) -> 'Builtin':
        return Builtin(self.op, substitute(self.left, mapping), substitute(self.right, mapping))

    def vars(self) -> set[str]:
        return vars_of_term(self.left) | vars_of_term(self.right)

    def render(self) -> str:
        return f'{render_term(self.left)} {self.op} {render_term(self.right)}'

# Aggregato #count
# I terms sono le variabili contate, condition è la congiunzione di letterali che le vincolano
# Due modalità: con cmp e guard otteniamo ad esempio "#count{...} > 1"
# mentre con result abbiamo un assegnazione "N = #count{...}"
@dataclass(frozen=True)
class CountAggregate:
    terms: tuple[Term, ...]
    condition: tuple[Literal, ...]
    cmp: str | None = None
    guard: Term | None = None
    result: Var | None = None

    # Restituisce SOLO le variabili della guard
    def vars(self) -> set[str]:
        out = set()
        if self.guard is not None:
            out |= vars_of_term(self.guard)
        return out

    # Non fa nulla, poiché le sue variabili sono locali
    def substituted(self, mapping):
        return self

    def render(self) -> str:
        inner = f'#count{{ {','.join((render_term(t) for t in self.terms))} : {', '.join((l.render() for l in self.condition))} }}'
        if self.result is not None:
            return f'{self.result.name} = {inner}'
        return f'{inner} {self.cmp} {render_term(self.guard)}'

# Elementi del corpo di una regola
BodyElem = Union[Literal, Builtin, CountAggregate]

# Regola normale/disgiuntiva
# Contiene una lista di Literal in testa (se più di uno, disgiunti) e i BodyElem del corpo
@dataclass
class RuleIR:
    head: list[Literal] = field(default_factory=list)
    body: list[BodyElem] = field(default_factory=list)

    # Produce la regola corrispondente in formato ASP
    def render(self) -> str:
        h = ' | '.join((l.render() for l in self.head))
        b = ', '.join((e.render() for e in self.body))
        # Se non c'è il corpo, è un fatto
        if not self.body:
            return f'{h}.'
        # Se non c'è la testa, è un vincolo
        if not self.head:
            return f':- {b}.'
        # Se ci sono entrambi, è una regola
        return f'{h} :- {b}.'

# Choice rule
# element è il Literal scelto
# condition è il dominio della scelta
# body è il corpo della regola
# lower e upper sono gli eventuali bound di cardinalità
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
        # Aggiunge i bound se presenti
        if self.lower is not None:
            core = f'{self.lower} {core}'
        if self.upper is not None:
            core = f'{core} {self.upper}'
        # Restituisce core con il corpo (se presente)
        if self.body:
            return f'{core} :- {', '.join((e.render() for e in self.body))}.'
        return f'{core}.'

# Vincolo debole
# body è il corpo, cui postponiamo [weight@level, terms]
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

# Incapsula una query, contiene una lista di RuleIR che definiscono ans, e l'arità di ans
@dataclass
class QueryIR:
    rules: list[RuleIR]
    arity: int

    def render(self) -> str:
        lines = [r.render() for r in self.rules]
        lines.append(f'#show ans/{self.arity}.')
        return '\n'.join(lines)

# Uno statement è l'unione dei quattro tipi
StatementIR = Union[RuleIR, ChoiceIR, WeakIR, QueryIR]

# Fa il render di tutti gli StatementIR, separandoli con \n, producendo
# quindi l'intero programma ASP
def render_program(statements: list[StatementIR]) -> str:
    return '\n'.join((s.render() for s in statements)) + '\n'
