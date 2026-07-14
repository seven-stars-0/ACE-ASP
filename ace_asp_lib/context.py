from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from .terms import Var, Const, Term, normalize_name
from .ir import StatementIR, QueryIR
from .errors import ArityMismatch, ReservedWord, MultipleQueries, UnboundVariable
RESERVED = {'a', 'an', 'one', 'the', 'is', 'be', 'does', 'not', 'provably', 'can', 'may', 'must', 'should', 'no', 'every', 'each', 'that', 'who', 'which', 'to', 'of', 'if', 'then', 'there', 'it', 'false', 'possible', 'and', 'or', 'at', 'least', 'most', 'more', 'less', 'than', 'exactly'}

class ConceptKind(Enum):
    NOUN = auto()
    VERB = auto()
    ADJECTIVE = auto()
    FUNCTION = auto()

@dataclass
class ConceptDecl:
    name: str
    arity: int
    kind: ConceptKind

class ConceptRegistry:

    def __init__(self):
        self._concepts: dict[str, ConceptDecl] = {}
        self._verb_alias: dict[str, str] = {}

    def _canonical_verb(self, name: str) -> str:
        if name in self._concepts or name in self._verb_alias:
            return self._verb_alias.get(name, name)
        head, sep, rest = name.partition('_')
        candidates = []
        for h in (head + 's', head + 'es', head[:-1] if head.endswith('s') else None, head[:-2] if head.endswith('es') else None):
            if h:
                candidates.append(h + sep + rest)
        for c in candidates:
            if c in self._concepts:
                self._verb_alias[name] = c
                return c
        return name

    def declare(self, surface: str, arity: int, kind: ConceptKind, sentence: str | None=None) -> str:
        name = normalize_name(surface)
        if name in RESERVED:
            raise ReservedWord(surface, sentence)
        if kind == ConceptKind.VERB:
            name = self._canonical_verb(name)
        prev = self._concepts.get(name)
        if prev is not None:
            if prev.arity != arity:
                raise ArityMismatch(name, prev.arity, arity, sentence)
            return name
        self._concepts[name] = ConceptDecl(name, arity, kind)
        return name

    def all(self) -> dict[str, ConceptDecl]:
        return dict(self._concepts)

class VarManager:

    def __init__(self):
        self.reset()

    def reset(self):
        self._counter = 0
        self.user_vars: set[str] = set()

    def fresh(self) -> Var:
        self._counter += 1
        return Var(f'V{self._counter}')

    def register_user(self, name: str) -> Var:
        self.user_vars.add(name)
        return Var(name)

class TranslationContext:

    def __init__(self):
        self.reset()

    def reset(self):
        self.registry = ConceptRegistry()
        self.vars = VarManager()
        self.skolems: dict[str, Const] = {}
        self._skolem_counter = 0
        self.program: list[StatementIR] = []
        self.query: QueryIR | None = None
        self.current_sentence: str | None = None

    def new_sentence(self, text: str | None=None):
        self.vars.reset()
        self.current_sentence = text

    def add(self, stmt: StatementIR):
        self.program.append(stmt)

    def set_query(self, q: QueryIR):
        if self.query is not None:
            raise MultipleQueries(self.current_sentence)
        self.query = q

    def fresh_skolem(self) -> Const:
        self._skolem_counter += 1
        return Const(f'sk{self._skolem_counter}')

    def bind_skolem(self, var_name: str) -> Const:
        c = self.fresh_skolem()
        self.skolems[var_name] = c
        return c

    def resolve_variable(self, name: str) -> Term:
        if name in self.skolems:
            return self.skolems[name]
        return self.vars.register_user(name)

    def statements(self) -> list[StatementIR]:
        out = list(self.program)
        if self.query is not None:
            out.append(self.query)
        return out
CTX = TranslationContext()

def reset_context():
    CTX.reset()
