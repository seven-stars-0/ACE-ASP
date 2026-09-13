from __future__ import annotations
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from .terms import Term, Var, SUBJ
from .ir import Literal, Builtin, BodyElem, Polarity

# Tipi di quantificatore che un NP può avere
class QuantKind(Enum):
    CONST = auto() # Costanti e variabili
    EXIST = auto() # Esistenziale
    UNIV = auto() # Universale
    NONE = auto() # Negato
    GQ = auto() # Quantificatore generalizzato

# Dizionario dei confronti NEGATI
GQ_VIOLATION_CMP = {'at least': '<', 'at most': '>', 'more than': '<=', 'less than': '>=', 'exactly': '!='}

# Incapsula il tipo di quantificatore e, per i GQ, la parola e il numeor, ad esempio "at least 2"
@dataclass(frozen=True)
class Quant:
    kind: QuantKind
    gq_word: str | None = None
    gq_n: int | None = None

# Risultato della valutazione di un sintagma nominale
@dataclass
class NPResult:
    term: Term # Termine che denota il NP
    restrictors: list[BodyElem] = field(default_factory=list) # Lista di condizioni che caratterizzano il termine ("a *rich* customer")
    quant: Quant = Quant(QuantKind.CONST)
    head_noun: str | None = None

    def is_ground(self) -> bool:
        return self.quant.kind == QuantKind.CONST and (not self.restrictors)

# Le modalità dei verbi
class Modality(Enum):
    CAN = auto()
    MUST = auto()
    SHOULD = auto()

# Predicato a cui manca il soggetto
# Un esempio chiarificatore: nella frase "... owns a fat dog", non conosciamo ancora il soggetto
# il Literal sarà owns(_SUBJ, V1), mentre l'NPResult dell'oggetto avrà come restrittori [dog(V1), fat(V1)]
# Nelle frasi con verbi ditransitivi possono esserci più oggetti: "... gives a fancy card to young Mary" ha come due oggetti "card" e "Mary",
# entrambi caratterizzati dai propri restrictors "fancy" e "young"
#
# Ovviamente dobbiamo conservare tutti i restrittori del soggetto a parte, in modo da aggiungerli al corpo della regola
# quando la produrremo; inoltre, fare così rende la traduzione più elegante, ma questa è la mia opinione
@dataclass
class Predication:
    literal: Literal # Il predicato in sè, con _SUBJ
    obj_nps: list[NPResult] = field(default_factory=list) # Contiene gli NPResult degli oggetti della frase, noti

    # Restituisce una predicazione ma senza segnaposto
    def substituted(self, mapping) -> 'Predication':
        return Predication(self.literal.substituted(mapping), self.obj_nps)

# Risultato della valutazione di un sintagma verbale
# Contiene tutte le Predication (con SUBJ da rimpiazzare), i Builtin, e i campi relativi alla modalità
@dataclass
class VPResult:
    preds: list[Predication] = field(default_factory=list)
    builtins: list[Builtin] = field(default_factory=list)
    modality: Modality | None = None
    modal_negated: bool = False

    # Applica una polarità a tutte le predicazioni
    def with_polarity(self, p: Polarity) -> 'VPResult':
        return VPResult([Predication(pr.literal.with_polarity(p), pr.obj_nps) for pr in self.preds], list(self.builtins), self.modality, self.modal_negated)

    # Unisce due VP coordinate con "and", tranne se una dele due è modale
    # Questo perché non avrebbe senso fare merge se nel caso "can wait and must sleep"
    # non si possono unire choice rules con vincoli forti
    def merged(self, other: 'VPResult') -> 'VPResult':
        if self.modality or other.modality:
            from .errors import UnsupportedInContext
            raise UnsupportedInContext('coordinazione di VP modali non supportata')
        return VPResult(self.preds + other.preds, self.builtins + other.builtins)

    # Metodo della saturazione del soggetto
    def apply(self, subject: Term) -> tuple[list[BodyElem], list[tuple]]:
        mapping = {SUBJ: subject} # Mapping

        # Dividiamo i BodyElem normali dai predicati con QG perché questi ultimi
        # diventeranno CountAggregate, che in base al contesto (premessa o vincolo)
        # hanno traduzioni diverse (confronto diretto o negato, rispettivamente)
        # Questo è noto solo ai chiamanti del metodo, e quindi la responsabilità spetta
        # a loro
        # Qui restituiamo semplicemente una tripla per ogni QG, con tutte le informazioni per costruirli
        out: list[BodyElem] = []
        gq_preds: list[tuple] = []

        for pr in self.preds:
            # Satura con il soggetto
            prs = pr.substituted(mapping)
            # Prende tutti i NP degli oggetti con quantificatori generalizzati 
            gq_objs = [np for np in prs.obj_nps if np.quant.kind == QuantKind.GQ]

            if gq_objs:
                # Se ce ne sono più di uno, da errore (non sono gestibili)
                if len(gq_objs) > 1:
                    from .errors import UnsupportedInContext
                    raise UnsupportedInContext("piu' quantificatori generalizzati nella stessa predicazione")
                # Raccogliamo tutti gli oggetti del predicato (tranne il QG)
                extra = []
                for np in prs.obj_nps:
                    if np.quant.kind != QuantKind.GQ:
                        extra.extend(np.restrictors)
                gq_preds.append((prs.literal, gq_objs[0], extra))

            # Aggiunge il letterale saturo e i suoi restrittori
            else:
                out.append(prs.literal)
                for np in prs.obj_nps:
                    out.extend(np.restrictors)

        # Satura i builtin                    
        out.extend((b.substituted(mapping) for b in self.builtins))
        return (out, gq_preds)

# Appiattisce una lista annidata in una lista, scartando i None
# Serve perché le regole di coordinazione ("and") producono liste annidate
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

# Tabella dei confronti diretti, che si oppone a GQ_VIOLATION_CMP
GQ_BODY_CMP = {'at least': '>=', 'at most': '<=', 'more than': '>', 'less than': '<', 'exactly': '='}

# Serve solo come marcatore di tipo, afferma che una VP è una disgiunzione di alternative
class OrVP(list):
    pass

# Alias per congiunzioni e forma normale disgiuntiva
Conj = list # lista di elementi
DNF = list # lista di congiunzioni (quindi lista di liste)
# Questa serve per frasi tipo "If X blinks and jumps or sleeps ...", la cui traduzione in ASP
# è produrre due regole con la stessa testa ma corpo diverso, una con [blinks(X), jumps(X)] e l'altra con [sleeps(X)]
# Quindi la DNF avrà come elementi la lista di elementi di regole diverse, ma con la stessa testa

# Algebra sulle disgiunzioni
def dnf_and(a: DNF, b: DNF) -> DNF:
    return [ca + cb for ca in a for cb in b]

def dnf_or(a: DNF, b: DNF) -> DNF:
    return a + b
