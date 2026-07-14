class AceAspError(Exception):

    def __init__(self, message: str, sentence: str | None=None):
        self.sentence = sentence
        if sentence:
            message = f'{message}\n  nella frase: "{sentence}"'
        super().__init__(message)

class UnsafeVariable(AceAspError):

    def __init__(self, variables, context: str, sentence=None):
        vs = ', '.join(sorted(variables))
        super().__init__(f"variabile/i {vs} non safe in {context}: ogni variabile deve essere introdotta da un nome comune (es. 'a person {sorted(variables)[0]}') in un letterale positivo della premessa", sentence)

class ArityMismatch(AceAspError):

    def __init__(self, name, old_arity, new_arity, sentence=None):
        super().__init__(f"il concetto '{name}' era stato usato con arita' {old_arity} e ora compare con arita' {new_arity}: in ACE-ASP ogni parola denota un unico predicato", sentence)

class ReservedWord(AceAspError):

    def __init__(self, word, sentence=None):
        super().__init__(f"'{word}' e' una function word di ACE-ASP e non puo' essere usata come nome, verbo o aggettivo", sentence)

class UnsupportedInContext(AceAspError):
    pass

class MultipleQueries(AceAspError):

    def __init__(self, sentence=None):
        super().__init__("e' ammessa al piu' una frase interrogativa, in coda al testo", sentence)

class UnboundVariable(AceAspError):

    def __init__(self, name, sentence=None):
        super().__init__(f"la variabile {name} e' usata ma non e' mai stata introdotta in apposizione a un nome comune", sentence)
