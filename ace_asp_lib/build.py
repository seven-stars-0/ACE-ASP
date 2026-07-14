from __future__ import annotations
from .terms import Term, Var, Const, ArithExpr, SUBJ, vars_of_term, substitute
from .ir import Literal, Builtin, CountAggregate, RuleIR, ChoiceIR, WeakIR, QueryIR, Polarity, BodyElem
from .results import NPResult, VPResult, OrVP, Quant, QuantKind, Modality, GQ_VIOLATION_CMP, GQ_BODY_CMP, DNF, Conj, dnf_and
from .context import CTX
from .errors import UnsupportedInContext, UnboundVariable
from . import safety

def _only_literals(elems, what: str) -> tuple[Literal, ...]:
    for e in elems:
        if not isinstance(e, Literal):
            raise UnsupportedInContext(f'solo predicazioni semplici sono ammesse in {what}', CTX.current_sentence)
    return tuple(elems)

def _gq_aggregate(lit: Literal, gq_np: NPResult, extra: list, positive: bool) -> CountAggregate:
    table = GQ_BODY_CMP if positive else GQ_VIOLATION_CMP
    cond = _only_literals([lit] + list(gq_np.restrictors) + list(extra), 'un quantificatore generalizzato')
    return CountAggregate(terms=(gq_np.term,), condition=cond, cmp=table[gq_np.quant.gq_word], guard=gq_np.quant.gq_n)

def _no_modality(vp, where: str):
    if isinstance(vp, VPResult) and vp.modality is not None:
        raise UnsupportedInContext(f'i verbi modali non sono ammessi in {where}', CTX.current_sentence)

def clause_to_dnf(np: NPResult, vp) -> DNF:
    if isinstance(vp, OrVP):
        out: DNF = []
        for branch in vp:
            out.extend(clause_to_dnf(np, branch))
        return out
    _no_modality(vp, 'una premessa')
    if np.quant.kind in (QuantKind.UNIV, QuantKind.NONE):
        raise UnsupportedInContext("'every'/'no' non sono ammessi in una premessa: riformula il quantificatore a livello di frase (if ... then / No ...)", CTX.current_sentence)
    if np.quant.kind == QuantKind.GQ:
        elems, gq_preds = vp.apply(np.term)
        if gq_preds:
            raise UnsupportedInContext("quantificatori generalizzati sia sul soggetto sia sull'oggetto", CTX.current_sentence)
        cond = _only_literals(list(np.restrictors) + elems, 'un quantificatore generalizzato')
        agg = CountAggregate(terms=(np.term,), condition=cond, cmp=GQ_BODY_CMP[np.quant.gq_word], guard=np.quant.gq_n)
        return [[agg]]
    conj: Conj = list(np.restrictors)
    elems, gq_preds = vp.apply(np.term)
    conj.extend(elems)
    for lit, gq_np, extra in gq_preds:
        conj.append(_gq_aggregate(lit, gq_np, extra, positive=True))
    return [conj]

def head_clause_to_disjuncts(np: NPResult, vp) -> list[list[Literal]]:
    if isinstance(vp, OrVP):
        out = []
        for branch in vp:
            out.extend(head_clause_to_disjuncts(np, branch))
        return out
    _no_modality(vp, 'una conclusione')
    if np.quant.kind != QuantKind.CONST or np.restrictors:
        raise UnsupportedInContext("la conclusione puo' riferirsi solo a variabili gia' introdotte nella premessa o a nomi propri (niente esistenziali in testa)", CTX.current_sentence)
    if vp.builtins:
        raise UnsupportedInContext("un confronto o un'uguaglianza non puo' stare nella conclusione", CTX.current_sentence)
    literals: list[Literal] = []
    for pr in [p.substituted({SUBJ: np.term}) for p in vp.preds]:
        if pr.literal.polarity not in (Polarity.POS, Polarity.SNEG):
            raise UnsupportedInContext("la negazione per fallimento ('provably') non puo' stare nella conclusione", CTX.current_sentence)
        for obj in pr.obj_nps:
            if obj.quant.kind == QuantKind.GQ:
                raise UnsupportedInContext("un quantificatore generalizzato non puo' stare nella conclusione", CTX.current_sentence)
            if obj.restrictors:
                raise UnsupportedInContext("l'oggetto nella conclusione deve essere un nome proprio o una variabile legata nella premessa (niente esistenziali in testa)", CTX.current_sentence)
        literals.append(pr.literal)
    return [literals]

def add_conditional(body_dnf: DNF, head_disjuncts: list[list[Literal]]):
    if len(head_disjuncts) > 1:
        if any((len(d) != 1 for d in head_disjuncts)):
            raise UnsupportedInContext("nella conclusione una disgiunzione di congiunzioni (A and B) or C non e' esprimibile come singola regola", CTX.current_sentence)
        heads_per_rule = [[d[0] for d in head_disjuncts]]
    else:
        heads_per_rule = [[lit] for lit in head_disjuncts[0]]
    for conj in body_dnf:
        for head in heads_per_rule:
            r = RuleIR(head=head, body=list(conj))
            safety.check(r, CTX.current_sentence)
            CTX.add(r)

def add_constraints(body_dnf: DNF):
    for conj in body_dnf:
        r = RuleIR(body=list(conj))
        safety.check(r, CTX.current_sentence)
        CTX.add(r)

def _unify_equalities(elems: list[BodyElem]) -> list[BodyElem]:
    mapping: dict[Var, Term] = {}
    rest: list[BodyElem] = []
    for e in elems:
        if isinstance(e, Builtin) and e.op == '=' and isinstance(e.left, Var) and (not vars_of_term(e.right)):
            mapping[e.left] = e.right
        else:
            rest.append(e)
    changed = True
    while changed:
        changed = False
        for k, v in mapping.items():
            nv = substitute(v, mapping)
            if nv != v:
                mapping[k] = nv
                changed = True
    return [e.substituted(mapping) for e in rest]

def _skolemize(elems: list[BodyElem]) -> list[BodyElem]:
    mapping: dict[Var, Term] = {}
    for e in elems:
        for name in e.vars() if not isinstance(e, CountAggregate) else set():
            v = Var(name)
            if v not in mapping:
                if name in CTX.vars.user_vars:
                    mapping[v] = CTX.bind_skolem(name)
                else:
                    mapping[v] = CTX.fresh_skolem()
    return [e.substituted(mapping) for e in elems]

def _add_facts(elems: list[BodyElem]):
    elems = _unify_equalities(elems)
    for e in elems:
        if isinstance(e, CountAggregate):
            raise UnsupportedInContext("un conteggio non puo' essere asserito come fatto", CTX.current_sentence)
        if isinstance(e, Builtin):
            raise UnsupportedInContext(f"il confronto '{e.render()}' non puo' essere asserito come fatto", CTX.current_sentence)
        if e.polarity in (Polarity.NAF, Polarity.NAF_SNEG):
            raise UnsupportedInContext("'provably' non ha senso in un'asserzione: usa un condizionale (If ... then ...)", CTX.current_sentence)
        if e.vars():
            raise UnboundVariable(sorted(e.vars())[0], CTX.current_sentence)
        CTX.add(RuleIR(head=[e]))

def _modal_statement(np: NPResult, vp: VPResult):
    if np.quant.kind not in (QuantKind.UNIV, QuantKind.CONST):
        raise UnsupportedInContext("un modale richiede un soggetto universale ('every ...') o un nome proprio", CTX.current_sentence)
    if len(vp.preds) != 1 or vp.builtins:
        raise UnsupportedInContext('un modale ammette una sola predicazione semplice', CTX.current_sentence)
    domain = _only_literals(np.restrictors, 'il soggetto di un modale')
    pr = vp.preds[0].substituted({SUBJ: np.term})
    lit = pr.literal
    if lit.polarity != Polarity.POS:
        raise UnsupportedInContext("modale e negazione del verbo insieme non sono supportati (usa 'can not' / 'should not')", CTX.current_sentence)
    obj_restr: list[Literal] = []
    gq_obj: NPResult | None = None
    for obj in pr.obj_nps:
        if obj.quant.kind == QuantKind.GQ:
            gq_obj = obj
        else:
            obj_restr.extend(_only_literals(obj.restrictors, "l'oggetto di un modale"))
    subj_vars = tuple((Var(v) for v in sorted(vars_of_term(np.term))))
    forbidden_body = list(domain) + [lit] + list(obj_restr) + (list(gq_obj.restrictors) if gq_obj else [])
    if vp.modality == Modality.CAN:
        if vp.modal_negated:
            stmt = RuleIR(body=forbidden_body)
        else:
            lower = upper = None
            cond = list(obj_restr)
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
            stmt = ChoiceIR(element=lit, condition=cond, body=list(domain), lower=lower, upper=upper)
    elif vp.modality == Modality.MUST:
        if vp.modal_negated:
            stmt = RuleIR(body=forbidden_body)
        else:
            stmt = RuleIR(body=list(domain) + _violation(lit, pr, obj_restr))
    elif vp.modality == Modality.SHOULD:
        body = forbidden_body if vp.modal_negated else list(domain) + _violation(lit, pr, obj_restr)
        stmt = WeakIR(body=body, terms=subj_vars)
    else:
        raise UnsupportedInContext("modalita' sconosciuta")
    safety.check(stmt, CTX.current_sentence)
    CTX.add(stmt)

def _violation(lit: Literal, pr, obj_restr) -> list[BodyElem]:
    exist_vars = [obj.term for obj in pr.obj_nps if obj.quant.kind == QuantKind.EXIST]
    if exist_vars:
        cond = _only_literals([lit] + list(obj_restr), 'un obbligo')
        return [CountAggregate(terms=tuple(exist_vars), condition=cond, cmp='=', guard=0)]
    return [lit.with_polarity(Polarity.NAF)] + list(obj_restr)

def add_simple_sentence(np: NPResult, vp):
    if isinstance(vp, OrVP):
        if np.quant.kind != QuantKind.UNIV:
            raise UnsupportedInContext("una disgiunzione top-level richiede un soggetto universale ('Every node is red or is green.') oppure un condizionale", CTX.current_sentence)
        disjuncts = head_clause_to_disjuncts(NPResult(np.term, [], Quant(QuantKind.CONST)), vp)
        if any((len(d) != 1 for d in disjuncts)):
            raise UnsupportedInContext("(A and B) or C non e' esprimibile in una testa disgiuntiva", CTX.current_sentence)
        r = RuleIR(head=[d[0] for d in disjuncts], body=list(np.restrictors))
        safety.check(r, CTX.current_sentence)
        CTX.add(r)
        return
    if vp.modality is not None:
        _modal_statement(np, vp)
        return
    if np.quant.kind == QuantKind.UNIV:
        elems, gq_preds = vp.apply(np.term)
        head_lits, body_extra = ([], [])
        for e in elems:
            if isinstance(e, Literal) and e.polarity in (Polarity.POS, Polarity.SNEG):
                head_lits.append(e)
            else:
                raise UnsupportedInContext("in 'Every N VP' la VP deve essere affermativa o con negazione forte; per condizioni piu' ricche usa If ... then ...", CTX.current_sentence)
        if head_lits:
            for pr in vp.preds:
                for obj in pr.obj_nps:
                    if obj.quant.kind == QuantKind.EXIST and obj.restrictors:
                        raise UnsupportedInContext("'Every X <verbo> a Y' introduce un esistenziale in testa: usa 'can' (choice) o riformula", CTX.current_sentence)
            for h in head_lits:
                r = RuleIR(head=[h], body=list(np.restrictors))
                safety.check(r, CTX.current_sentence)
                CTX.add(r)
        for lit, gq_np, extra in gq_preds:
            agg = _gq_aggregate(lit, gq_np, extra, positive=False)
            r = RuleIR(body=list(np.restrictors) + [agg])
            safety.check(r, CTX.current_sentence)
            CTX.add(r)
        return
    if np.quant.kind == QuantKind.NONE:
        for conj in clause_to_dnf(NPResult(np.term, list(np.restrictors), Quant(QuantKind.EXIST), np.head_noun), vp):
            r = RuleIR(body=conj)
            safety.check(r, CTX.current_sentence)
            CTX.add(r)
        return
    if np.quant.kind == QuantKind.GQ:
        elems, gq_preds = vp.apply(np.term)
        if gq_preds:
            raise UnsupportedInContext("GQ sia sul soggetto sia sull'oggetto", CTX.current_sentence)
        cond = _only_literals(list(np.restrictors) + elems, 'un quantificatore generalizzato')
        agg = CountAggregate(terms=(np.term,), condition=cond, cmp=GQ_VIOLATION_CMP[np.quant.gq_word], guard=np.quant.gq_n)
        r = RuleIR(body=[agg])
        safety.check(r, CTX.current_sentence)
        CTX.add(r)
        return
    elems, gq_preds = vp.apply(np.term)
    facts = _unify_equalities(list(np.restrictors) + elems)
    _add_facts(_skolemize(facts))
    for lit, gq_np, extra in gq_preds:
        agg = _gq_aggregate(lit.substituted({v: CTX.skolems.get(v.name, v) for v in {Var(n) for n in lit.vars()}}), gq_np, extra, positive=False)
        r = RuleIR(body=[agg])
        safety.check(r, CTX.current_sentence)
        CTX.add(r)

def add_there_is(np: NPResult):
    _add_facts(_skolemize(list(np.restrictors)))

def set_yes_no_query(np: NPResult, negated: bool, vp: VPResult):
    _no_modality(vp, 'una query')
    if negated:
        vp = vp.with_polarity(Polarity.SNEG)
        vp = VPResult(vp.preds, [Builtin('!=' if b.op == '=' else b.op, b.left, b.right) for b in vp.builtins])
    [conj] = clause_to_dnf(np, vp)
    r = RuleIR(head=[Literal('ans')], body=conj)
    safety.check(r, CTX.current_sentence)
    CTX.set_query(QueryIR(rules=[r], arity=0))

def set_which_query(noun_pred: str, var_name: str | None, vp):
    X = CTX.vars.register_user(var_name) if var_name else CTX.vars.fresh()
    np = NPResult(X, [Literal(noun_pred, (X,))], Quant(QuantKind.EXIST))
    rules = []
    for conj in clause_to_dnf(np, vp):
        r = RuleIR(head=[Literal('ans', (X,))], body=conj)
        safety.check(r, CTX.current_sentence)
        rules.append(r)
    CTX.set_query(QueryIR(rules=rules, arity=1))

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
