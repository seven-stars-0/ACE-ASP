from __future__ import annotations
from .ir import RuleIR, ChoiceIR, WeakIR, Literal, Builtin, CountAggregate, Polarity
from .errors import UnsafeVariable

# Ogni statement, prima di essere aggiunto in CTX, passa per safety.check
# Questo modulo serve per verificare la safery delle regole prodotte

# Calcola quali variabili nel corpo di una regola sono safe
def _binding_vars(body) -> set[str]:
    from .terms import Var, vars_of_term
    bound: set[str] = set()
    for e in body:
        # Variabili POS e SNEG sono safe
        if isinstance(e, Literal) and e.polarity in (Polarity.POS, Polarity.SNEG):
            bound |= e.vars()
        # Se il CountAggregate ha un result (#count {} = N), allora N è safe
        elif isinstance(e, CountAggregate) and e.result is not None:
            bound.add(e.result.name)

    # Analizza i Builtin di eguaglianza
    # Il modo in cui il ciclo si ripete serve a trovare il punto fisso
    changed = True
    while changed:
        changed = False
        for e in body:
            if isinstance(e, Builtin) and e.op == '=':
                for a, b in ((e.left, e.right), (e.right, e.left)):
                    # Builtin del tipo "X = espressione", se tutte le variabili in "espressione" sono safe
                    # allora anche X è safe
                    if isinstance(a, Var) and a.name not in bound and (vars_of_term(b) <= bound):
                        bound.add(a.name)
                        changed = True
    return bound

# Calcola le variabili che devono necessariamente essere safe
def _needing_vars(body) -> set[str]:
    need: set[str] = set()
    for e in body:
        # Caso variabili con NAF
        if isinstance(e, Literal) and e.polarity in (Polarity.NAF, Polarity.NAF_SNEG):
            need |= e.vars()
        # Caso variabili in Builtin
        elif isinstance(e, Builtin):
            need |= e.vars()
        # Caso variabili guard dei COuntAggregate
        elif isinstance(e, CountAggregate):
            need |= e.vars()
    return need

# Calcola la safety di una regola
# Le variabili che devono essere legate sono quelle in testa e quelle calcolate da _needing_vars
# Confrontiamo l'unione dei due insiemi con bound e se ci sono variabili non legate, la regola è unsafe
def check_rule(rule: RuleIR, sentence: str | None=None) -> None:
    bound = _binding_vars(rule.body) # Variabili safe

    head_vars = set().union(*(l.vars() for l in rule.head)) if rule.head else set()
    unsafe = (head_vars | _needing_vars(rule.body)) - bound
    if unsafe:
        where = 'un fatto' if not rule.body else 'un constraint' if not rule.head else 'una regola'
        raise UnsafeVariable(unsafe, where, sentence)

# Caclola la safety di una choice rule
def check_choice(choice: ChoiceIR, sentence: str | None=None) -> None:
    # Le variabili legate sono quelle nel corpo e nella condizione della choice rule
    bound = _binding_vars(choice.body) | _binding_vars(choice.condition)
    # Le variabili che necessitano bounding sono quelle nell'elemento della scelta e quelle di _needing_vars
    unsafe = (choice.element.vars() | _needing_vars(choice.body)) - bound
    if unsafe:
        raise UnsafeVariable(unsafe, 'una choice rule', sentence)

# Calcola la safety di un weak constraint
# Le variabili che necessitano di bounding sono quelle di _needing_vars e i
# terms di [weight@level, terms]
def check_weak(weak: WeakIR, sentence: str | None=None) -> None:
    bound = _binding_vars(weak.body)
    need = _needing_vars(weak.body)
    for t in weak.terms:
        from .terms import vars_of_term
        need |= vars_of_term(t)
    unsafe = need - bound
    if unsafe:
        raise UnsafeVariable(unsafe, 'un weak constraint', sentence)

# Metodo di dispatch, l'unico chiamato da build.py prima di CTX.add
def check(stmt, sentence: str | None=None) -> None:
    if isinstance(stmt, RuleIR):
        check_rule(stmt, sentence)
    elif isinstance(stmt, ChoiceIR):
        check_choice(stmt, sentence)
    elif isinstance(stmt, WeakIR):
        check_weak(stmt, sentence)