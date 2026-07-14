from __future__ import annotations
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from .terms import Term, Var, SUBJ
from .ir import Literal, Builtin, BodyElem, Polarity

class QuantKind(Enum):
    CONST = auto()
    EXIST = auto()
    UNIV = auto()
    NONE = auto()
    GQ = auto()
GQ_VIOLATION_CMP = {'at least': '<', 'at most': '>', 'more than': '<=', 'less than': '>=', 'exactly': '!='}

@dataclass(frozen=True)
class Quant:
    kind: QuantKind
    gq_word: str | None = None
    gq_n: int | None = None

@dataclass
class NPResult:
    term: Term
    restrictors: list[BodyElem] = field(default_factory=list)
    quant: Quant = Quant(QuantKind.CONST)
    head_noun: str | None = None

    def is_ground(self) -> bool:
        return self.quant.kind == QuantKind.CONST and (not self.restrictors)

class Modality(Enum):
    CAN = auto()
    MUST = auto()
    SHOULD = auto()

@dataclass
class Predication:
    literal: Literal
    obj_nps: list[NPResult] = field(default_factory=list)

    def substituted(self, mapping) -> 'Predication':
        return Predication(self.literal.substituted(mapping), self.obj_nps)

@dataclass
class VPResult:
    preds: list[Predication] = field(default_factory=list)
    builtins: list[Builtin] = field(default_factory=list)
    modality: Modality | None = None
    modal_negated: bool = False

    def with_polarity(self, p: Polarity) -> 'VPResult':
        return VPResult([Predication(pr.literal.with_polarity(p), pr.obj_nps) for pr in self.preds], list(self.builtins), self.modality, self.modal_negated)

    def merged(self, other: 'VPResult') -> 'VPResult':
        if self.modality or other.modality:
            from .errors import UnsupportedInContext
            raise UnsupportedInContext('coordinazione di VP modali non supportata')
        return VPResult(self.preds + other.preds, self.builtins + other.builtins)

    def apply(self, subject: Term) -> tuple[list[BodyElem], list[tuple]]:
        mapping = {SUBJ: subject}
        out: list[BodyElem] = []
        gq_preds: list[tuple] = []
        for pr in self.preds:
            prs = pr.substituted(mapping)
            gq_objs = [np for np in prs.obj_nps if np.quant.kind == QuantKind.GQ]
            if gq_objs:
                if len(gq_objs) > 1:
                    from .errors import UnsupportedInContext
                    raise UnsupportedInContext("piu' quantificatori generalizzati nella stessa predicazione")
                extra = []
                for np in prs.obj_nps:
                    if np.quant.kind != QuantKind.GQ:
                        extra.extend(np.restrictors)
                gq_preds.append((prs.literal, gq_objs[0], extra))
            else:
                out.append(prs.literal)
                for np in prs.obj_nps:
                    out.extend(np.restrictors)
        out.extend((b.substituted(mapping) for b in self.builtins))
        return (out, gq_preds)

def flatten(args) -> list:
    out = []
    for a in args:
        if a is None:
            continue
        if isinstance(a, list):
            out.extend(flatten(a))
        else:
            out.append(a)
    return out
GQ_BODY_CMP = {'at least': '>=', 'at most': '<=', 'more than': '>', 'less than': '<', 'exactly': '='}

class OrVP(list):
    pass
Conj = list
DNF = list

def dnf_and(a: DNF, b: DNF) -> DNF:
    return [ca + cb for ca in a for cb in b]

def dnf_or(a: DNF, b: DNF) -> DNF:
    return a + b
