from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from .terms import Var, Const, Term, normalize_name
from .ir import StatementIR, QueryIR
from .errors import ArityMismatch, ReservedWord, MultipleQueries, UnboundVariable

# Insieme delle function word
# Questo è lo stesso insieme delle parole escluse dalla regex WORD nella grammatica
# ma qui vengono usate come ulteriore controllo a livello semantico
RESERVED = {'a', 'an', 'one', 'the', 'is', 'be', 'does', 'not', 'provably', 'can', 'may', 'must', 'should', 'no', 'every', 'each', 'that', 'who', 'which', 'to', 'of', 'if', 'then', 'there', 'it', 'false', 'possible', 'and', 'or', 'at', 'least', 'most', 'more', 'less', 'than', 'exactly'}

# Tipi di concetti
class ConceptKind(Enum):
    NOUN = auto()
    VERB = auto()
    ADJECTIVE = auto()
    FUNCTION = auto()

# Dichiarazione di un concetto
# Un concetto è qui definito come una parola (name) con arità e tipo
@dataclass
class ConceptDecl:
    name: str
    arity: int
    kind: ConceptKind

# ConceptRegistry è la memoria dei concetti incontrati
class ConceptRegistry:

    def __init__(self):
        self._concepts: dict[str, ConceptDecl] = {} # Mappa un nome alla relativa dichiarazione del concetto
        self._verb_alias: dict[str, str] = {} # Mappa forme verbali alla loro forma canonica

    # Gestisce la flessione dei verbi, riconducendoli alla forma canonica
    # Questo è importantissimo, perché "John *waits*" e "Every man does not *wait*"
    # denotano lo stesso concetto, e quindi devono essere trattati allo stesso modo
    def _canonical_verb(self, name: str) -> str:
        # Se il verbo è già stato incontrato, lo restituisce direttamente
        if name in self._concepts or name in self._verb_alias:
            return self._verb_alias.get(name, name)

        # Serve per verbi composti come "assigned_to"
        # Tutto ciò che segue si applica solo alla testa ("assigned")
        head, sep, rest = name.partition('_')
        candidates = []
        # Aggiunge/toglie s/es alla fine della testa, e li salva come candidati
        for h in (head + 's', head + 'es', head[:-1] if head.endswith('s') else None, head[:-2] if head.endswith('es') else None):
            if h:
                candidates.append(h + sep + rest)
        # Tra tutti i candidati, se uno è già un concetto lo restituisce
        for c in candidates:
            if c in self._concepts:
                self._verb_alias[name] = c # Salva l'alias
                return c
        # Nuovo concetto
        return name

    # Metodo importantissimo, viene chiamaot ogni volta che una parola viene incontrata
    def declare(self, surface: str, arity: int, kind: ConceptKind, sentence: str | None=None) -> str:
        name = normalize_name(surface) # Forma normale
        # Rifiuta le parole riservate
        if name in RESERVED:
            raise ReservedWord(surface, sentence)
        # Forma canonica
        if kind == ConceptKind.VERB:
            name = self._canonical_verb(name)

        # Se il concetto era già noto, verifica che l'arità sia coerente
        # In caso contrario lancia un errore
        prev = self._concepts.get(name)
        if prev is not None:
            if prev.arity != arity:
                raise ArityMismatch(name, prev.arity, arity, sentence)
            return name

        # Dichiara il nuovo concetto, e restituisce il nome in formato ASP
        self._concepts[name] = ConceptDecl(name, arity, kind)
        return name

    def all(self) -> dict[str, ConceptDecl]:
        return dict(self._concepts)

# Genera e traccia le viariabili di una singola frase
class VarManager:

    def __init__(self):
        self.reset()

    # Chiamato all'inizio di ogni frase per resettare il counter e le user_vars
    def reset(self):
        self._counter = 0
        self.user_vars: set[str] = set()

    # Nuova variabile, serve per gli indefiniti senza variabile esplicita
    # ad esempio "a dog" invece di "a dog X"
    def fresh(self) -> Var:
        self._counter += 1
        return Var(f'V{self._counter}')

    # Registra le variabili scritte dall'utente ("a dog X")
    def register_user(self, name: str) -> Var:
        self.user_vars.add(name)
        return Var(name)

# Rappresenta lo stato globale della traduzione
# Tiene traccia dei concetti, delle variabili della frase corrente,
# delle costanti di Skolem (persistenti tra frasi).
# Accumula anche gli StatementIR prodotti fino a quel punto, l'eventuale query (massimo una!)
# e la current_sentence
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

    # Resetta VarManager e cambia la sentence attuale
    def new_sentence(self, text: str | None=None):
        self.vars.reset()
        self.current_sentence = text

    # Aggiunge uno statement
    def add(self, stmt: StatementIR):
        self.program.append(stmt)

    # Imposta la query del programma
    # Se era già stato fatto, lancia un errore (massimo una query)
    def set_query(self, q: QueryIR):
        if self.query is not None:
            raise MultipleQueries(self.current_sentence)
        self.query = q

    # Restituisce una nuova costante di Skolem
    def fresh_skolem(self) -> Const:
        self._skolem_counter += 1
        return Const(f'sk{self._skolem_counter}')

    # Associa una variabile utente a una costante di Skolem fresca fresca
    def bind_skolem(self, var_name: str) -> Const:
        c = self.fresh_skolem()
        self.skolems[var_name] = c
        return c

    # Restituisce lo skolem se la variabile era già stata associata, altrimenti
    # la registra come variabile utente
    def resolve_variable(self, name: str) -> Term:
        if name in self.skolems:
            return self.skolems[name]
        return self.vars.register_user(name)

    # Restituisce tutti gli statement
    def statements(self) -> list[StatementIR]:
        out = list(self.program)
        if self.query is not None:
            out.append(self.query)
        return out

# Unica istanza globale
CTX = TranslationContext()

# Questo viene chiamato solo al termine della compilazione
# per evitare che una seconda compilazione erediti i concetti e gli statement di quella attuale
def reset_context():
    CTX.reset()
