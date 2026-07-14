from lark import Lark
g = open('grammar_asp.lark').read()
parser = Lark(g)
sentences = ['John waits.', 'Mary is a rich customer.', 'John gives a card to Mary.', 'John fills-in a form.', 'John is fond-of Mary.', 'The age of John is 32.', 'There is a person X.', 'X is tall.', 'Every man is a human.', 'If a man X owns a dog Y then X likes Y.', 'If a person X is not provably guilty then X is innocent.', 'If the age of a person X is Y and Y >= 18 then X is an adult.', 'Every node is red or is green or is blue.', 'Every stone does not move.', 'No dog is a cat.', 'It is false that John waits and that Mary sleeps.', 'It is not possible that a student X is lazy and X is successful.', 'Every employee is assigned-to exactly 1 team.', 'Every employee can be assigned-to a team.', 'Every server should not be overloaded.', 'If a screen X blinks or X waits, and Mary enters a card then Mary is happy.', 'Every customer that is rich and that owns a card is important.', 'Every man waits. Which man waits?', 'John waits. Does John wait?', 'How many man waits?']
fails = 0
for s in sentences:
    try:
        parser.parse(s)
        print(f'OK    {s}')
    except Exception as e:
        fails += 1
        msg = str(e).splitlines()[0][:90]
        print(f'FAIL  {s}\n      {msg}')
print(f'\n{len(sentences) - fails}/{len(sentences)} ok')
