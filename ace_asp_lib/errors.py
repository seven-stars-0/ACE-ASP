# Questo file racchiude tutte le eccezioni 

# La base di tutte le eccezioni
class AceAspError(Exception):

    # Include il messaggio di errore (specifico per ogni sottoclasse) e, se presente,
    # mostra la sentence da cui è stato generato
    def __init__(self, message: str, sentence: str | None=None):
        self.sentence = sentence
        if sentence:
            message = f'{message}\n  nella frase: "{sentence}"'
        super().__init__(message)

# Sollevata dal checker di safety, elenca le variabili non-safe e suggerisce una correzione
class UnsafeVariable(AceAspError):

    def __init__(self, variables, context: str, sentence=None):
        vs = ', '.join(sorted(variables))
        super().__init__(f"variabile/i {vs} non safe in {context}: ogni variabile deve essere introdotta da un nome comune (es. 'a person {sorted(variables)[0]}') in un letterale positivo della premessa", sentence)

# Sollevata dal registro dei concetti quando una parola compari con arità diverse
class ArityMismatch(AceAspError):

    def __init__(self, name, old_arity, new_arity, sentence=None):
        super().__init__(f"il concetto '{name}' era stato usato con arita' {old_arity} e ora compare con arita' {new_arity}: in ACE-ASP ogni parola denota un unico predicato", sentence)

# Sollevata quando si tenta di usare una function word come contenuto lessicale
class ReservedWord(AceAspError):

    def __init__(self, word, sentence=None):
        super().__init__(f"'{word}' e' una function word di ACE-ASP e non puo' essere usata come nome, verbo o aggettivo", sentence)

# Serve alla potatura delle costruzioni: alcune frasi sono sintatticamente valide ma semanticamente
# non gestite
class UnsupportedInContext(AceAspError):
    pass

# Una sola query per programma
class MultipleQueries(AceAspError):

    def __init__(self, sentence=None):
        super().__init__("e' ammessa al piu' una frase interrogativa, in coda al testo", sentence)

# Variabili usate ma mai introdotte da una there_is_sentence
class UnboundVariable(AceAspError):

    def __init__(self, name, sentence=None):
        super().__init__(f"la variabile {name} e' usata ma non e' mai stata introdotta in apposizione a un nome comune", sentence)
