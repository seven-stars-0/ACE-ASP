from __future__ import annotations
from dataclasses import dataclass
from typing import Union

# Un TERMINE è ciò che può comparire come argomento di un predicato
# In ACE-ASP sono quattro: variabili, costanti, interi, espressioni aritmetiche

# Funzione che normalizza ogni parola nella forma canonica di ASP
# tutto minuscolo, e sostituisce '-' con '_'
def normalize_name(name: str) -> str:
    return name.strip().lower().replace('-', '_')

# Le classi sono immutabili, importante perché finiscono come chiavi di dizionari
@dataclass(frozen=True)
class Var:
    name: str

@dataclass(frozen=True)
class Const:
    name: str

    @staticmethod
    # Costruttore per i PROPER_NAME, che cominciano con la maiuscola
    def of(surface: str) -> 'Const':
        return Const(normalize_name(surface))

# Permette argomenti del tipo "X + 1" oppure "X - Y"
@dataclass(frozen=True)
class ArithExpr:
    op: str
    left: 'Term'
    right: 'Term'

# Un Term è l'unione di questi quattro tipi
Term = Union[Var, Const, int, ArithExpr]

# Variabile segnaposto per il soggetto, che verrà saturata in futuro
# E' una variabile che comincia con _, per evitare venga confusa con le variabili inserite
# dall'utente, che non possono cominciare con _
SUBJ = Var('_SUBJ')

# Converte un termine nel suo testo ASP in base al tipo
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

# Raccoglie i nomi delle variabili in un termine
# Viene usato nel determinare la safety di una regola
def vars_of_term(t: Term) -> set[str]:
    if isinstance(t, Var):
        return {t.name}
    # Unione ricorsiva dei termini di cui è composta l'espressione aritmetica
    if isinstance(t, ArithExpr):
        return vars_of_term(t.left) | vars_of_term(t.right)
    return set()

# La chiave della saturazione del soggetto, {SUBJ: soggetto_reale}
def substitute(t: Term, mapping: dict[Var, Term]) -> Term:
    if isinstance(t, Var):
        return mapping.get(t, t)
    # Sostituzione ricorsiva
    if isinstance(t, ArithExpr):
        return ArithExpr(t.op, substitute(t.left, mapping), substitute(t.right, mapping))
    return t
