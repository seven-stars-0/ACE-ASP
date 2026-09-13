from __future__ import annotations
from .terms import Term, Var, Const, ArithExpr, SUBJ, vars_of_term, substitute
from .ir import Literal, Builtin, CountAggregate, RuleIR, ChoiceIR, WeakIR, QueryIR, Polarity, BodyElem
from .results import NPResult, VPResult, OrVP, Quant, QuantKind, Modality, GQ_VIOLATION_CMP, GQ_BODY_CMP, DNF, Conj, dnf_and
from .context import CTX
from .errors import UnsupportedInContext, UnboundVariable
from . import safety

# Se davvero leggerete questo pezzo di codice, preparatevi a soffrire
# Io farò del mio meglio a spiegarlo, ma è molto complicato e brutto da vedere

# Verifica che un insieme di elementi siano tutti Literal
# Serve per parti che non supportano altri tipi di BodyElem
# "what" è il contesto, per dare errori più leggibili. Vedete prossima funzione per capire meglio
def _only_literals(elems, what: str) -> tuple[Literal, ...]:
    for e in elems:
        if not isinstance(e, Literal):
            raise UnsupportedInContext(f'solo predicazioni semplici sono ammesse in {what}', CTX.current_sentence)
    return tuple(elems)

# Costruisce un CountAggregate da un GQ. Prende la tripla creata in VPResult.apply
# e usa il giusto CMP in base al contesto (positive)
def _gq_aggregate(lit: Literal, gq_np: NPResult, extra: list, positive: bool) -> CountAggregate:
    table = GQ_BODY_CMP if positive else GQ_VIOLATION_CMP
    # Verifica ci siano solo Literal
    cond = _only_literals([lit] + list(gq_np.restrictors) + list(extra), 'un quantificatore generalizzato')

    return CountAggregate(terms=(gq_np.term,), condition=cond, cmp=table[gq_np.quant.gq_word], guard=gq_np.quant.gq_n)

# Rifiuta i modali dove non hjanno senso (premesse, conclusioni, query)
def _no_modality(vp, where: str):
    if isinstance(vp, VPResult) and vp.modality is not None:
        raise UnsupportedInContext(f'i verbi modali non sono ammessi in {where}', CTX.current_sentence)

# Trasforma una coppia NP+VP che compare in una premessa in una DNF
# Serve a costruire i corpi ottenuti da uno statement ACE-ASP
def clause_to_dnf(np: NPResult, vp) -> DNF:
    # Se la VP è una disgiunzione, chiama se stessa su ciascun ramo e unisce i risultati   
    if isinstance(vp, OrVP):
        out: DNF = []
        for branch in vp:
            out.extend(clause_to_dnf(np, branch))
        return out
    
    _no_modality(vp, 'una premessa')

    if np.quant.kind in (QuantKind.UNIV, QuantKind.NONE):
        raise UnsupportedInContext("'every'/'no' non sono ammessi in una premessa: riformula il quantificatore a livello di frase (if ... then / No ...)", CTX.current_sentence)
    # Caso soggetto con quantificatore generalizzato
    # Costruisce ConuntAggregato con confronto diretto e lo restituisce come unica congiunzione
    if np.quant.kind == QuantKind.GQ:
        elems, gq_preds = vp.apply(np.term)
        if gq_preds:
            raise UnsupportedInContext("quantificatori generalizzati sia sul soggetto sia sull'oggetto", CTX.current_sentence)
        cond = _only_literals(list(np.restrictors) + elems, 'un quantificatore generalizzato')
        agg = CountAggregate(terms=(np.term,), condition=cond, cmp=GQ_BODY_CMP[np.quant.gq_word], guard=np.quant.gq_n)
        return [[agg]]

    # Caso normale con QuantKind.EXIST o CONST
    # Prende i restrictor del soggetto, satura il soggetto, crea eventuali aggregati
    # e restituisce l'unica congiunzione
    conj: Conj = list(np.restrictors)
    elems, gq_preds = vp.apply(np.term)
    conj.extend(elems)
    for lit, gq_np, extra in gq_preds:
        conj.append(_gq_aggregate(lit, gq_np, extra, positive=True))
    return [conj]

# Traduce la conclusione creando la testa della regola ASP
# Restituisce una lista di disgiunti
def head_clause_to_disjuncts(np: NPResult, vp) -> list[list[Literal]]:
    # Stessa logica della funzione precedente
    if isinstance(vp, OrVP):
        out = []
        for branch in vp:
            out.extend(head_clause_to_disjuncts(np, branch))
        return out
    
    _no_modality(vp, 'una conclusione')

    # Il soggetto deve essere una CONST (variabile o nome proprio) senza restrictors
    if np.quant.kind != QuantKind.CONST or np.restrictors:
        raise UnsupportedInContext("la conclusione puo' riferirsi solo a variabili gia' introdotte nella premessa o a nomi propri (niente esistenziali in testa)", CTX.current_sentence)
    # Anche i builtin non hanno senso in testa
    if vp.builtins:
        raise UnsupportedInContext("un confronto o un'uguaglianza non puo' stare nella conclusione", CTX.current_sentence)

    literals: list[Literal] = []
    # Itera le predicazioni di VP saturate con il soggetto, verificando ch
    for pr in [p.substituted({SUBJ: np.term}) for p in vp.preds]:
        # Non possiamo mettere la NAF in testa
        if pr.literal.polarity not in (Polarity.POS, Polarity.SNEG):
            raise UnsupportedInContext("la negazione per fallimento ('provably') non puo' stare nella conclusione", CTX.current_sentence)

        # Non ci possono essere quantificatori o restrittori in testa
        for obj in pr.obj_nps:
            if obj.quant.kind == QuantKind.GQ:
                raise UnsupportedInContext("un quantificatore generalizzato non puo' stare nella conclusione", CTX.current_sentence)
            if obj.restrictors:
                raise UnsupportedInContext("l'oggetto nella conclusione deve essere un nome proprio o una variabile legata nella premessa (niente esistenziali in testa)", CTX.current_sentence)
        literals.append(pr.literal)
    return [literals]

# Costruisce le regole "If ... then ..."
def add_conditional(body_dnf: DNF, head_disjuncts: list[list[Literal]]):
    # CREAZIONE TESTA
    # Se ci sono più disgiunti in testa, ciascuno deve essere un singolo letterale
    if len(head_disjuncts) > 1:
        if any((len(d) != 1 for d in head_disjuncts)):
            raise UnsupportedInContext("nella conclusione una disgiunzione di congiunzioni (A and B) or C non e' esprimibile come singola regola", CTX.current_sentence)
        heads_per_rule = [[d[0] for d in head_disjuncts]]
    # Se c'è una sola congiunzione, crea una testa per ciascun letterale
    # Questo è il caso "... then X is red and X is green", che produce due regole
    # "red(X) :- ..." e "green(X) :- ..."
    else:
        heads_per_rule = [[lit] for lit in head_disjuncts[0]]

    # CREAZIONE CORPO
    # Per ogni congiunzione e per ogni testa, crea una RuleIR e la aggiunge al contesto
    for conj in body_dnf:
        for head in heads_per_rule:
            r = RuleIR(head=head, body=list(conj))
            safety.check(r, CTX.current_sentence)
            CTX.add(r)

# Costruisce i vincoli forti, per ciascuna congiunzione crea un vincolo a parte
def add_constraints(body_dnf: DNF):
    for conj in body_dnf:
        r = RuleIR(body=list(conj))
        safety.check(r, CTX.current_sentence)
        CTX.add(r)

# Elimina le uguaglianze "variabile = valore ground", sostituendo direttamente
# Questo serve nei casi in cui abbiamo "X = 23", e sostituiamo ad ogni occorrenza di X il valore 23 direttamente
def _unify_equalities(elems: list[BodyElem]) -> list[BodyElem]:
    mapping: dict[Var, Term] = {} # Dizionario che contiene tutte le uguaglianze da mappare
    rest: list[BodyElem] = []

    # Scorre tutti gli elementi, se trova Builtin con il simbolo =
    # con a sinistra una variabile e a destra un termine senza variabili (ground), salva il mapping
    for e in elems:
        if isinstance(e, Builtin) and e.op == '=' and isinstance(e.left, Var) and (not vars_of_term(e.right)):
            mapping[e.left] = e.right
        else:
            # Tutto ciò che non è un Builtin viene salvato a parte, e poi sostituiremo lì
            rest.append(e)

    # Risolve le catene di sostituzioni, del tipo "X = Y, Y = 3", itera finché
    # non raggiungiamo "X = 3" direttamente
    # NOTA IMPORTANTE: questo è codice morto, non fa niente
    # Lo lascio qui per eventuali espansioni future, ma adesso ho un po' paura di rompere tutto
    changed = True
    while changed:
        changed = False
        for k, v in mapping.items():
            nv = substitute(v, mapping)
            if nv != v:
                mapping[k] = nv
                changed = True
    return [e.substituted(mapping) for e in rest]

# Skolemizza gli esistenziali
# Viene chiamata solo sui fatti
def _skolemize(elems: list[BodyElem]) -> list[BodyElem]:
    mapping: dict[Var, Term] = {}
    for e in elems:
        # Itera su tutte le variabili degli elementi (tranne i CountAggregate)
        for name in e.vars() if not isinstance(e, CountAggregate) else set():
            v = Var(name)
            if v not in mapping:
                # Se la variabile è dichiarata dall'utente ("a person X")
                # allora fa il binding per permettere di riferirsi ad essa anche in futuro
                if name in CTX.vars.user_vars:
                    mapping[v] = CTX.bind_skolem(name)
                # Altrimenti ("a person") crea uno skolem senza binding 
                else:
                    mapping[v] = CTX.fresh_skolem()

    return [e.substituted(mapping) for e in elems]

# Trasforma una lista di elementi già skolemizzati in fatti
def _add_facts(elems: list[BodyElem]):
    elems = _unify_equalities(elems)
    for e in elems:
        # Casi impossibili da trattare come fatti
        if isinstance(e, CountAggregate):
            raise UnsupportedInContext("un conteggio non puo' essere asserito come fatto", CTX.current_sentence)
        if isinstance(e, Builtin):
            raise UnsupportedInContext(f"il confronto '{e.render()}' non puo' essere asserito come fatto", CTX.current_sentence)
        if e.polarity in (Polarity.NAF, Polarity.NAF_SNEG):
            raise UnsupportedInContext("'provably' non ha senso in un'asserzione: usa un condizionale (If ... then ...)", CTX.current_sentence)
        # Se dopo la skolemizzazione ci sono ancora variabili
        # queste sarebbero unbounded
        if e.vars():
            raise UnboundVariable(sorted(e.vars())[0], CTX.current_sentence)

        CTX.add(RuleIR(head=[e]))

def _modal_statement(np: NPResult, vp: VPResult):
    # Il soggetto deve essere universale o costante
    if np.quant.kind not in (QuantKind.UNIV, QuantKind.CONST):
        raise UnsupportedInContext("un modale richiede un soggetto universale ('every ...') o un nome proprio", CTX.current_sentence)
    # Il VP deve avere una sola predicazione senza builtin
    if len(vp.preds) != 1 or vp.builtins:
        raise UnsupportedInContext('un modale ammette una sola predicazione semplice', CTX.current_sentence)

    # Ammettiamo solo Literal 
    domain = _only_literals(np.restrictors, 'il soggetto di un modale')

    # Satura il soggetto e verifica che il VP non sia negato
    pr = vp.preds[0].substituted({SUBJ: np.term})
    lit = pr.literal
    if lit.polarity != Polarity.POS:
        raise UnsupportedInContext("modale e negazione del verbo insieme non sono supportati (usa 'can not' / 'should not')", CTX.current_sentence)

    # Separa un eventuale oggetto con GQ dai restrictor degli altri oggetti
    obj_restr: list[Literal] = []
    gq_obj: NPResult | None = None
    for obj in pr.obj_nps:
        if obj.quant.kind == QuantKind.GQ:
            gq_obj = obj
        else:
            obj_restr.extend(_only_literals(obj.restrictors, "l'oggetto di un modale"))

    # Calcola le variabili del soggetto (per i weak constraint)
    subj_vars = tuple((Var(v) for v in sorted(vars_of_term(np.term))))
    # Calcola il corpo, usato dai casi negati
    forbidden_body = list(domain) + [lit] + list(obj_restr) + (list(gq_obj.restrictors) if gq_obj else [])

    # Caso CAN
    if vp.modality == Modality.CAN:
        # Se negato diventa un vincolo
        if vp.modal_negated:
            stmt = RuleIR(body=forbidden_body)
        # Se positivo diventa una choice rule
        else:
            lower = upper = None
            cond = list(obj_restr)
            # Se c'è un GQ, questo diventa il bound della choice rule
            if gq_obj is not None:
                cond += _only_literals(gq_obj.restrictors, 'un modale')
                w, n = (gq_obj.quant.gq_word, gq_obj.quant.gq_n)
                if w == 'at least':
                    lower = n
                elif w == 'at most':
                    upper = n
                elif w == 'exactly':
                    lower = upper = n
                elif w == 'more than':
                    lower = n + 1
                elif w == 'less than':
                    upper = n - 1
            # Si traduce in "lower {lit : cond} upper :- body"
            stmt = ChoiceIR(element=lit, condition=cond, body=list(domain), lower=lower, upper=upper)
    # Caso MUST
    elif vp.modality == Modality.MUST:
        if vp.modal_negated:
            stmt = RuleIR(body=forbidden_body)
        else:
            stmt = RuleIR(body=list(domain) + _violation(lit, pr, obj_restr))
    # Caso SHOULD
    elif vp.modality == Modality.SHOULD:
        body = forbidden_body if vp.modal_negated else list(domain) + _violation(lit, pr, obj_restr)
        stmt = WeakIR(body=body, terms=subj_vars)
    else:
        raise UnsupportedInContext("modalita' sconosciuta")
    
    safety.check(stmt, CTX.current_sentence)
    CTX.add(stmt)

# Questo serve per calcolare il corpo dei vincoli non negati
# Nei vincoli negati "Every server must NOT be overloaded", basta il forbidden_body della funzione precedente
# Se invece dicessimo "Every server must be overloaded", la sua violazione è un server che NON è overloaded
def _violation(lit: Literal, pr, obj_restr) -> list[BodyElem]:
    exist_vars = [obj.term for obj in pr.obj_nps if obj.quant.kind == QuantKind.EXIST]
    # Caso esistenziale ("... must encode a protein")
    # In questo caso la violazione avviene tramite conteggio eguagliato a 0
    if exist_vars:
        cond = _only_literals([lit] + list(obj_restr), 'un obbligo')
        return [CountAggregate(terms=tuple(exist_vars), condition=cond, cmp='=', guard=0)]
    # Negli altri casi basta usare la NAF nel letterale dell'oggetto
    return [lit.with_polarity(Polarity.NAF)] + list(obj_restr)

# Gestisce tutte le frasi "soggetto + predicato", scegliendo lo statement appropriato in base
# al quantificatore del soggetto
def add_simple_sentence(np: NPResult, vp):
    # Caso VP disgiunta ("... is red or green")
    if isinstance(vp, OrVP):
        # Richiede un quantificatore universale
        if np.quant.kind != QuantKind.UNIV:
            raise UnsupportedInContext("una disgiunzione top-level richiede un soggetto universale ('Every node is red or is green.') oppure un condizionale", CTX.current_sentence)
        # Calcoliamo tutte le disgiunzioni
        disjuncts = head_clause_to_disjuncts(NPResult(np.term, [], Quant(QuantKind.CONST)), vp)
        if any((len(d) != 1 for d in disjuncts)):
            raise UnsupportedInContext("(A and B) or C non e' esprimibile in una testa disgiuntiva", CTX.current_sentence)
        # Crea la regola
        r = RuleIR(head=[d[0] for d in disjuncts], body=list(np.restrictors))
        safety.check(r, CTX.current_sentence)
        CTX.add(r)
        return

    # Caso modale
    if vp.modality is not None:
        _modal_statement(np, vp)
        return

    # Caso soggetto universale
    if np.quant.kind == QuantKind.UNIV:
        # Applica il soggetto al VP
        elems, gq_preds = vp.apply(np.term)
        head_lits, body_extra = ([], [])
        # Si accettano solo elementi senza NAF
        for e in elems:
            if isinstance(e, Literal) and e.polarity in (Polarity.POS, Polarity.SNEG):
                head_lits.append(e)
            else:
                raise UnsupportedInContext("in 'Every N VP' la VP deve essere affermativa o con negazione forte; per condizioni piu' ricche usa If ... then ...", CTX.current_sentence)

        if head_lits:
            # Qui viene vietato il caso "Every gene encodes a protein", che richiederebbe una
            # funzione di Skolem, che porterebbe potenzialmente a problemi nella terminazione nel grounding
            for pr in vp.preds:
                for obj in pr.obj_nps:
                    if obj.quant.kind == QuantKind.EXIST and obj.restrictors:
                        raise UnsupportedInContext("'Every X <verbo> a Y' introduce un esistenziale in testa: usa 'can + must' o riformula", CTX.current_sentence)
            # Per ogni letterale, creiamo una regola
            for h in head_lits:
                r = RuleIR(head=[h], body=list(np.restrictors))
                safety.check(r, CTX.current_sentence)
                CTX.add(r)
        # Per ogni GQ creiamo un vincolo
        # Questo è il caso di frasi come "Every employee is assigned-to exactly 1 team"
        for lit, gq_np, extra in gq_preds:
            agg = _gq_aggregate(lit, gq_np, extra, positive=False) # Notare il positive=False
            r = RuleIR(body=list(np.restrictors) + [agg])
            safety.check(r, CTX.current_sentence)
            CTX.add(r)
        return

    # Casi del tipo "No dog is a cat"
    # Questi si traducono in vincoli della forma "dog(X), cat(X)"
    if np.quant.kind == QuantKind.NONE:
        # Forziamo l'esistenziale al nuovo NP, in modo da ottenere "dog(X)"
        for conj in clause_to_dnf(NPResult(np.term, list(np.restrictors), Quant(QuantKind.EXIST), np.head_noun), vp):
            r = RuleIR(body=conj)
            safety.check(r, CTX.current_sentence)
            CTX.add(r)
        return

    # Casi del tipo "At least 2 nodes are red"
    if np.quant.kind == QuantKind.GQ:
        elems, gq_preds = vp.apply(np.term)
        # Il caso "At least 2 nodes are at most 3 colors" non ha senso
        if gq_preds:
            raise UnsupportedInContext("GQ sia sul soggetto sia sull'oggetto", CTX.current_sentence)

        # Creiamo un vincolo che vieta l'occorrenza contraria
        cond = _only_literals(list(np.restrictors) + elems, 'un quantificatore generalizzato')
        agg = CountAggregate(terms=(np.term,), condition=cond, cmp=GQ_VIOLATION_CMP[np.quant.gq_word], guard=np.quant.gq_n)
        r = RuleIR(body=[agg])
        safety.check(r, CTX.current_sentence)
        CTX.add(r)
        return

    # Caso EXIST o CONST
    # Questo riguarda l'asserzione di fatti su entità concrete
    elems, gq_preds = vp.apply(np.term)
    facts = _unify_equalities(list(np.restrictors) + elems)
    _add_facts(_skolemize(facts))
    # Per frasi del tipo "John owns at least 2 dogs", crea un vincolo che vieta il caso contrario
    for lit, gq_np, extra in gq_preds:
        # Sostituisce le variabili con le costanti di skolem
        agg = _gq_aggregate(lit.substituted({v: CTX.skolems.get(v.name, v) for v in {Var(n) for n in lit.vars()}}), gq_np, extra, positive=False)
        r = RuleIR(body=[agg])
        safety.check(r, CTX.current_sentence)
        CTX.add(r)

# Frase "There is a person [X]"
def add_there_is(np: NPResult):
    _add_facts(_skolemize(list(np.restrictors)))

# "Does John wait?", "Is John a man?"
def set_yes_no_query(np: NPResult, negated: bool, vp: VPResult):
    # Modali nelle query non hanno senso
    _no_modality(vp, 'una query')
    # Se negata, applica la SNEG alle predicazioni e inverte i builtin
    if negated:
        vp = vp.with_polarity(Polarity.SNEG)
        vp = VPResult(vp.preds, [Builtin('!=' if b.op == '=' else b.op, b.left, b.right) for b in vp.builtins])
    # Costruisce la DNF del corpo e crea una regola ans :- corpo
    [conj] = clause_to_dnf(np, vp)
    r = RuleIR(head=[Literal('ans')], body=conj)
    safety.check(r, CTX.current_sentence)
    CTX.set_query(QueryIR(rules=[r], arity=0))

# "Which man is happy?"
def set_which_query(noun_pred: str, var_name: str | None, vp):
    # Crea una variabile (utente se specificata, altrimenti nuova)
    X = CTX.vars.register_user(var_name) if var_name else CTX.vars.fresh()
    # Costruisce l'NP risultante (esistenziale)
    np = NPResult(X, [Literal(noun_pred, (X,))], Quant(QuantKind.EXIST))

    # Per ogni congiunzione crea una regola ans(X) :- corpo
    rules = []
    for conj in clause_to_dnf(np, vp):
        r = RuleIR(head=[Literal('ans', (X,))], body=conj)
        safety.check(r, CTX.current_sentence)
        rules.append(r)
    CTX.set_query(QueryIR(rules=rules, arity=1)) # Arità 1

# "How many man waits?"
# Crea un CountAggregate come unico BodyElem della regola, con guard=N
# e testa ans(N)
def set_how_many_query(noun_pred: str, var_name: str | None, vp):
    _no_modality(vp, 'una query')

    X = CTX.vars.register_user(var_name) if var_name else CTX.vars.fresh()
    np = NPResult(X, [Literal(noun_pred, (X,))], Quant(QuantKind.EXIST))

    [conj] = clause_to_dnf(np, vp)
    cond = _only_literals(conj, 'una query how-many')

    N = Var('HOWMANY')
    agg = CountAggregate(terms=(X,), condition=cond, result=N)
    r = RuleIR(head=[Literal('ans', (N,))], body=[agg])
    safety.check(r, CTX.current_sentence)

    CTX.set_query(QueryIR(rules=[r], arity=1))
