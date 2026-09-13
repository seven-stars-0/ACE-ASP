import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from CNLWizard.cnl_wizard_compiler import CnlWizardCompiler

# Disattiviamo le signature e le sostituzioni di variabili automatiche perché le gestiamo noi
CnlWizardCompiler.config['signatures'] = False
CnlWizardCompiler.config['var_substitution'] = False

from ace_asp_lib import Var, Const, ArithExpr, SUBJ, render_program, Polarity, Literal, Builtin, NPResult, VPResult, OrVP, Predication, Quant, QuantKind, Modality, flatten, dnf_and, dnf_or, CTX, reset_context, ConceptKind, UnsupportedInContext, build
_VARIABLE_RE = re.compile('^[A-Z][0-9]*$')

# Converte un token grezzo nel token appropriato (int, variabile, stringa)
def _term_of_token(tok: str):
    if tok.isdigit() or (tok.startswith('-') and tok[1:].isdigit()):
        return int(tok)
    if _VARIABLE_RE.match(tok):
        return CTX.resolve_variable(tok)
    return Const.of(tok)

def common_noun(word):
    return word

def verb(word):
    return word

def adjective(word):
    return word

def indefinite_determiner(tok):
    return tok

def universal_determiner(tok):
    return tok

def no_determiner(tok):
    return tok

def gq_word(tok):
    return tok

def relative_pronoun(tok):
    return tok

def modal_word(tok):
    return tok

def negation_marker(tok):
    return True

# word = "at least", n = 2
def generalised_quantifier(word, n):
    return Quant(QuantKind.GQ, gq_word=word, gq_n=int(n))

# Aggettivi e concatenazione di essi
# Anche il caso singolo restituisce una lista per rendere il codice più generale
def adjective_conjunction(adj):
    return [adj]
def adjective_conjunction_concat(*args):
    return flatten(args)

# --- Clausole relative ---
# Le clausole relative servono a creare restrittori per il soggetto/oggetto "... a customer *that owns a card*"
# Il caso con OR o con verbo modale non è supportato
# 1. "... that owns a card or a toy" renderebbe i restrittivi dell'oggetto disgiunti e quindi
#    creare due statement diversi, cosa che il modello a restrictors non permette
# 2. "... that must wait" genererebbe uno statement, non un restrittore, quindi non avrebbe il
#    signigicato semantico da me scelto
def relative_clause_atom(pronoun, vp):
    if isinstance(vp, OrVP):
        raise UnsupportedInContext("'or' dentro una relativa non e' supportato: usa due frasi o un condizionale", CTX.current_sentence)
    if vp.modality is not None:
        raise UnsupportedInContext("un verbo modale non puo' stare in una relativa", CTX.current_sentence)
    return vp

# Singola clausola e concatenazione di esse
def relative_clause(atom):
    return [atom]
def relative_clause_concat(*args):
    return flatten(args)
# ------

# COSTRUZIONE DEI SINTAGMI NOMINALI
def _make_common_np(quant, adjs, noun, var_tok, relatives) -> NPResult:
    # Termine dell'NP
    term = CTX.vars.register_user(var_tok) if var_tok else CTX.vars.fresh()
    # Definisce il predicato del nome, in formato "noun(V1)"
    noun_pred = CTX.registry.declare(noun, 1, ConceptKind.NOUN, CTX.current_sentence)
    restr = [Literal(noun_pred, (term,))]
    # Crea restrittori basandosi su eventuali aggettivi, come predicati con arità 1
    for adj in adjs or []:
        adj_pred = CTX.registry.declare(adj, 1, ConceptKind.ADJECTIVE, CTX.current_sentence)
        restr.append(Literal(adj_pred, (term,)))
    # Aggiunge i restrittori dalle clausole relative
    for rel_vp in relatives or []:
        elems, gq_preds = rel_vp.apply(term) # Applica il soggetto alla relativa
        if gq_preds:
            raise UnsupportedInContext("un quantificatore generalizzato non puo' stare in una relativa", CTX.current_sentence)
        restr.extend(elems)
    
    return NPResult(term=term, restrictors=restr, quant=quant, head_noun=noun)

# --- LE SETTE FORME DI SINTAGMA NOMINALE ---
# Costante ("Malachy")
def proper_name_np(tok):
    return NPResult(term=Const.of(tok), quant=Quant(QuantKind.CONST))

# Variabile (la risolve con skolem, se già utilizzata)
def variable_np(tok):
    return NPResult(term=CTX.resolve_variable(tok), quant=Quant(QuantKind.CONST))

# Esistenziale ("a dog")
def indefinite_np(det, adjs, noun, var_tok, relatives):
    return _make_common_np(Quant(QuantKind.EXIST), adjs, noun, var_tok, relatives)

# Universale ("every dog")
def universal_np(det, adjs, noun, var_tok, relatives):
    return _make_common_np(Quant(QuantKind.UNIV), adjs, noun, var_tok, relatives)

# Negaizone ("no dog")
def no_np(det, adjs, noun, var_tok, relatives):
    return _make_common_np(Quant(QuantKind.NONE), adjs, noun, var_tok, relatives)

# Quantificatore generalizzato ("at least")
def gq_np(quant, noun, var_tok, relatives):
    return _make_common_np(quant, None, noun, var_tok, relatives)
# ------

def genitive_argument(x):
    if isinstance(x, NPResult):
        return x
    return NPResult(term=_term_of_token(x), quant=Quant(QuantKind.CONST))

# Genitivo funzionale ("the age of Malachy")
def functional_genitive_np(noun, owner: NPResult):
    # Variabile per il valore
    value = CTX.vars.fresh()
    # Dichiara il concetto, di tipo FUNCTION con arità 2
    pred = CTX.registry.declare(noun, 2, ConceptKind.FUNCTION, CTX.current_sentence)
    # Dichiara i restrittori dell'NP finale
    restr = list(owner.restrictors)
    restr.append(Literal(pred, (owner.term, value)))
    # Restituisce NP con term=value
    # Infatti, nella frase "the age of Malachy", il soggetto è "age"
    return NPResult(term=value, restrictors=restr, quant=Quant(QuantKind.EXIST), head_noun=noun)

def noun_phrase(np):
    return np

# --- VERBI (IN|DI)? TRANSITIVI
# In questa fase il soggetto non è ancora noto, infatti usiamo sempre SUBJ come placeholder

# I verbi intransitivi "waits" generano predicati di arità 1
def intransitive_verb_phrase(verb_word):
    pred = CTX.registry.declare(verb_word, 1, ConceptKind.VERB, CTX.current_sentence)
    return VPResult(preds=[Predication(Literal(pred, (SUBJ,)))])

# I verbi transitivi "owns a dog" avranno arità 2
def transitive_verb_phrase(verb_word, obj: NPResult):
    pred = CTX.registry.declare(verb_word, 2, ConceptKind.VERB, CTX.current_sentence)
    return VPResult(preds=[Predication(Literal(pred, (SUBJ, obj.term)), [obj])])

# I verbi ditransitivi "gives a card to Mary" avranno arità 3
def ditransitive_verb_phrase(verb_word, obj: NPResult, iobj: NPResult):
    pred = CTX.registry.declare(verb_word, 3, ConceptKind.VERB, CTX.current_sentence)
    return VPResult(preds=[Predication(Literal(pred, (SUBJ, obj.term, iobj.term)), [obj, iobj])])
# ------

def verb_complements(vp):
    return vp

def vp_infinitive(vp):
    return vp

def inf_verb_complements(vp):
    return vp

def inf_copula(cc):
    return cc

# Gestisce il caso "... is NP"
def predicative_np(np: NPResult):
    # ":.. is 22" oppure "is X", genera un Builtin "SUBJ = const"
    if np.quant.kind == QuantKind.CONST and (not np.restrictors):
        return VPResult(builtins=[Builtin('=', SUBJ, np.term)])
    # Casi vietati
    if np.quant.kind != QuantKind.EXIST:
        raise UnsupportedInContext("dopo la copula sono ammessi solo 'a N ...', nomi propri o variabili", CTX.current_sentence)

    # Caso esistenziale ("... is a rich customer")
    # Trasforma i restrittori dell'NP in predicazioni sul soggetto (VP)
    
    # Qui facciamo un mapping "alla storta", ossia sostituiamo term con SUBJ
    mapping = {np.term: SUBJ} if isinstance(np.term, Var) else {}
    preds, builtins = ([], [])
    for e in np.restrictors:
        e = e.substituted(mapping)
        if isinstance(e, Literal):
            preds.append(Predication(e))
        elif isinstance(e, Builtin):
            builtins.append(e)
        else:
            raise UnsupportedInContext('costrutto troppo complesso dopo la copula', CTX.current_sentence)
    return VPResult(preds=preds, builtins=builtins)

# "... is fond-of Mary", aggettivo binario
def transitive_adjective_complement(adj, obj: NPResult):
    pred = CTX.registry.declare(adj, 2, ConceptKind.ADJECTIVE, CTX.current_sentence)
    return VPResult(preds=[Predication(Literal(pred, (SUBJ, obj.term)), [obj])])

# "... is rich and famous", per ogni aggettivo una predicazione unaria
def adjective_complement(adjs):
    preds = []
    for adj in adjs:
        pred = CTX.registry.declare(adj, 1, ConceptKind.ADJECTIVE, CTX.current_sentence)
        preds.append(Predication(Literal(pred, (SUBJ,))))
    return VPResult(preds=preds)

# "... is 22", preceduti da un genitivo funzionale ("The age of Malachy is 22")
def predicative_expression(expr):
    return VPResult(builtins=[Builtin('=', SUBJ, expr)])

def copula_complement(cc):
    return cc

def copula_vp(cc):
    return cc

# Nega la condizione originale
# Trasforma "=" in "!="
def _flip_builtins(vp: VPResult) -> VPResult:
    return VPResult(vp.preds, [Builtin('!=' if b.op == '=' else b.op, b.left, b.right) for b in vp.builtins], vp.modality, vp.modal_negated)

# Applica la SNEG e inverte i builtin
def copula_negation(cc: VPResult):
    return _flip_builtins(cc.with_polarity(Polarity.SNEG))

# Applica la NAF
def copula_naf(cc: VPResult):
    # "... is not provably 32" non ha senso
    if cc.builtins:
        raise UnsupportedInContext("'is not provably' non e' applicabile a un'uguaglianza", CTX.current_sentence)
    return cc.with_polarity(Polarity.NAF)

# Questi due fanno la stessa cosa delle due funzioni precedenti
def vp_negation(vp: VPResult):
    return vp.with_polarity(Polarity.SNEG)
def vp_naf(vp: VPResult):
    return vp.with_polarity(Polarity.NAF)

# --- VERBI MODALI ---
_MODALITY = {'can': Modality.CAN, 'may': Modality.CAN, 'must': Modality.MUST, 'should': Modality.SHOULD}
# Crea un VP con la modalità giusta, impedendo modali annidati
def modal_vp(word, negated, vp: VPResult): # La VP è infinitiva
    if vp.modality is not None:
        raise UnsupportedInContext('modali annidati', CTX.current_sentence)
    return VPResult(vp.preds, vp.builtins, modality=_MODALITY[word], modal_negated=bool(negated))
# ------

def verb_vp(vp):
    return vp

def vp_simple(vp):
    return vp

def vp_conjunction(vp):
    return vp

# Caso "VP and VP", vengono fusi con VP.merged rifiutando la mescolanza con "OR"
def vp_conjunction_concat(*args):
    parts = flatten(args)
    merged = parts[0]
    for p in parts[1:]:
        if isinstance(merged, OrVP) or isinstance(p, OrVP):
            raise UnsupportedInContext("'and' e 'or' mescolati nella stessa VP: usa ', and'", CTX.current_sentence)
        merged = merged.merged(p)
    return merged

def verb_phrase(vp):
    return vp

# Caso "VP or VP", costruisce un OrVP
def verb_phrase_concat(*args):
    out = OrVP()
    for p in args:
        out.extend(p if isinstance(p, OrVP) else [p])
    return out

# --- FUNZIONI DELLE ESPRESSIONI ---
_BOOL_OPS = {'=': '=', '\\=': '!=', '>': '>', '>=': '>=', '<': '<', '=<': '<='}
def boolean_formula_operator(tok):
    return _BOOL_OPS[tok]

def boolean_formula(left, op, right):
    return Builtin(op, left, right)

def arithmetic_expression_operator(tok):
    return tok

def arithmetic_expression(left, op, right):
    return ArithExpr(op, left, right)

def expression(x):
    return x

def expression_atom(tok):
    return _term_of_token(tok)

def ground_expression(x):
    return int(x) if isinstance(x, str) else x
# ------


# --- DNF del corpo ---
# Etichetta una coppia NP + VP
def simple_clause(np: NPResult, vp):
    return ('clause', np, vp)

# Qui avviene la traduzione verso DNF
def body_literal(x):
    # Un builtin è una DNF banale
    if isinstance(x, Builtin):
        return [[x]]
    _, np, vp = x
    # DNF nel caso "serio"
    return build.clause_to_dnf(np, vp)

def body_conjunction(dnf):
    return dnf

# Algebra AND della DNF
# Questa fa il prodotto cartesiano delle congiunzioni
def body_conjunction_concat(*args):
    out = args[0]
    for p in args[1:]:
        out = dnf_and(out, p)
    return out

def body_or_group(dnf):
    return dnf

# Algebra OR delle DNF
# Semplicemente unisce le varie DNF
def body_or_group_concat(*args):
    out = args[0]
    for p in args[1:]:
        out = dnf_or(out, p)
    return out

def body_and_group(dnf):
    return dnf

def body_and_group_concat(*args):
    return body_conjunction_concat(*args)

def sentence_body(dnf):
    return dnf

def sentence_body_concat(*args):
    return body_or_group_concat(*args)

def negated_sentence_body(dnf):
    return dnf

def negated_sentence_body_concat(*args):
    return body_conjunction_concat(*args)
# ------

# --- PRODUZIONE DI STATEMENT ---
# Queste sono le funzioni che chiamano effettivamente le funzioni di build.py 
# per produrre IR, chiamando quella appropriata

def head_clause(np, vp):
    return build.head_clause_to_disjuncts(np, vp)

def sentence_head(disjuncts):
    return disjuncts

def sentence_head_concat(*args):
    out = []
    for d in args:
        out.extend(d)
    return out

def simple_sentence(np, vp):
    build.add_simple_sentence(np, vp)
    return True

def there_is_sentence(np):
    build.add_there_is(np)
    return True

def conditional_sentence(body_dnf, head_disjuncts):
    build.add_conditional(body_dnf, head_disjuncts)
    return True

def sentence_negation(body_dnf):
    build.add_constraints(body_dnf)
    return True

def impossibility_sentence(body_dnf):
    build.add_constraints(body_dnf)
    return True
# ------

# Questa è chiamata DOPO che la frase è stata valutata
def declarative_sentence(result):
    CTX.new_sentence() # Resetta tutte le variabili locali
    return result

# --- QUERY ---
# Ciascuna chiama la funzione appropriata in build.py che costruisce 
def yes_no_query(np, negated, vp):
    build.set_yes_no_query(np, bool(negated), vp)
    return True

def which_query(noun, var_tok, vp):
    pred = CTX.registry.declare(noun, 1, ConceptKind.NOUN, CTX.current_sentence)
    build.set_which_query(pred, var_tok, vp)
    return True

def how_many_query(noun, var_tok, vp):
    pred = CTX.registry.declare(noun, 1, ConceptKind.NOUN, CTX.current_sentence)
    build.set_how_many_query(pred, var_tok, vp)
    return True

def interrogative_sentence(result):
    CTX.new_sentence()
    return result
# ------

# L'ultima funzione chiamata in assoluto, alla radice dell'AST
# Arrivati qui, tutti gli statement sono nel contesto, quindi fa il render
# e restituisce il programma ASP
def start(*args):
    program = render_program(CTX.statements())
    # Resetta il contesto (variabili locali e skolem) per prepararsi ad un eventuale secondo testo
    reset_context()
    return program
