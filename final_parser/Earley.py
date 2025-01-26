# ---
# published: true
# title: Earley Parser
# layout: post
# comments: true
# tags: parsing, context-free
# categories: post
# ---
# TLDR; This tutorial is a complete implementation of Earley Parser in Python
# with Leo's optimizations. The Python interpreter is embedded so that you can
# work through the implementation steps.
# 
# The *Earley* parsing algorithm was invented by Jay Earley [^earley1970an] in 1970. It
# can be used to parse strings that conform to a context-free grammar. The
# algorithm uses a chart for parsing -- that is, it is implemented as a dynamic
# program relying on solving simpler sub-problems.
# 
# Earley parsers are very appealing for a practitioner because they can use any
# context-free grammar for parsing a string, and from the parse forest generated,
# one can recover all (even an infinite number) of parse trees that correspond to
# the given grammar. Unfortunately, this style of parsing pays for generality by
# being slightly expensive. It takes $$O(n^3)$$ time to parse in the worst case.
# However, if the grammar is unambiguous, it can parse in $$O(n^2)$$ time, and
# all [LR(k)](https://en.wikipedia.org/wiki/LR_parser) grammars in linear time[^leo1991a] -- $$ O(n) $$.
# 
# **This implementation of Earley parser correctly handles the epsilon case as
# given by Aycock et al.[^aycock2002practical]** Further, **the `LeoParser` class
# incorporates Leo's optimizations[^leo1991a]**.
# 
# Another detailed explanation of Earley parsing is by
# [Loup Vaillant](https://loup-vaillant.fr/tutorials/earley-parsing/).
# Further, a fast industrial strength Earley parser implementation is
# [Marpa](https://jeffreykegler.github.io/Marpa-web-site/).
# 
# This post is written as runnable Python source. You can download the
# notebook directly [here](https://github.com/rahulgopinath/rahulgopinath.github.io/blob/master/notebooks/2021-02-06-earley-parsing.py),
# It the file is downloaded as `earleyparser.py`, it can be imported into your
# projects using `import earleyparser`.
#
# ## Synopsis
#
# ```python
# import earleyparser as P
# my_grammar = {'<start>': [['1', '<A>'],
#                           ['2']
#                          ],
#               '<A>'    : [['a']]}
# my_parser = P.EarleyParser(my_grammar)
# for tree in my_parser.parse_on(text='1a', start_symbol='<start>'):
#     print(P.format_parsetree(tree))
# ```

# ## Definitions
# 
# For this post, we use the following terms:
# 
# * The _alphabet_ is the set all of symbols in the input language. For example,
#   in this post, we use all ASCII characters as alphabet.
# * A _terminal_ is a single alphabet symbol. Note that this is slightly different
#   from usual definitions (done here for ease of parsing). (Usually a terminal is
#   a contiguous sequence of symbols from the alphabet. However, both kinds of
#   grammars have a one to one correspondence, and can be converted easily.)
# 
#   For example, `x` is a terminal symbol.
# 
# * A _nonterminal_ is a symbol outside the alphabet whose expansion is _defined_
#   in the grammar using _rules_ for expansion.
# 
#   For example, `<term>` is a nonterminal in the below grammar.
# 
# * A _rule_ is a finite sequence of _terms_ (two types of terms: terminals and
#   nonterminals) that describe an expansion of a given terminal.
# 
#   For example, `[<term>+<expr>]` is one of the expansion rules of the nonterminal `<expr>`.
# 
# * A _definition_ is a set of _rules_ that describe the expansion of a given nonterminal.
# 
#   For example, `[[<digit>,<digits>],[<digit>]]` is the definition of the nonterminal `<digits>`
# 
# * A _context-free grammar_ is  composed of a set of nonterminals and 
#   corresponding definitions that define the structure of the nonterminal.
# 
#   The grammar given below is an example context-free grammar.
# 
# * A terminal _derives_ a string if the string contains only the symbols in the
#   terminal. A nonterminal derives a string if the corresponding definition
#   derives the string. A definition derives the  string if one of the rules in
#   the definition derives the string. A rule derives a string if the sequence
#   of terms that make up the rule can derive the string, deriving one substring 
#   after another contiguously (also called parsing).
# 
# * A *derivation tree* is an ordered tree that describes how an input string is
#   derived by the given start symbol. Also called a *parse tree*.
# * A derivation tree can be collapsed into its string equivalent. Such a string
#   can be parsed again by the nonterminal at the root node of the derivation
#   tree such that at least one of the resulting derivation trees would be the
#   same as the one we started with.
# 
# As before, we use the [fuzzingbook](https://www.fuzzingbook.org) grammar style.
# Here is an example grammar for arithmetic expressions, starting at `<start>`.
# A terminal symbol has exactly one character
# (Note that we disallow empty string (`''`) as a terminal symbol).
# Secondly, as per traditional implementations,
# there can only be one expansion rule for the `<start>` symbol. We work around
# this restriction by simply constructing as many charts as there are expansion
# rules, and returning all parse trees.

grammar = {
    '<start>': [['<expr>']],
    '<expr>': [
        ['<term>', '+', '<expr>'],
        ['<term>', '-', '<expr>'],
        ['<term>']],
    '<term>': [
        ['<fact>', '*', '<term>'],
        ['<fact>', '/', '<term>'],
        ['<fact>']],
    '<fact>': [
        ['<digits>'],
        ['(','<expr>',')']],
    '<digits>': [
        ['<digit>','<digits>'],
        ['<digit>']],
    '<digit>': [["%s" % str(i)] for i in range(10)],
}
START = '<start>'

# Here is another grammar that targets the same language. Unlike the first
# grammar, this grammar produces ambiguous parse results.

a_grammar = {
    '<start>': [['<expr>']],
    '<expr>': [
        ['<expr>', '+', '<expr>'],
        ['<expr>', '-', '<expr>'],
        ['<expr>', '*', '<expr>'],
        ['<expr>', '/', '<expr>'],
        ['(', '<expr>', ')'],
        ['<integer>']],
    '<integer>': [
        ['<digits>']],
    '<digits>': [
        ['<digit>','<digits>'],
        ['<digit>']],
    '<digit>': [["%s" % str(i)] for i in range(10)],
}

# ## Summary
# 
# An Earley parser executes the following steps for parsing:
# 
# Use `<start>` as the entry into parsing. At this point, we want to parse the
# given string by the nonterminal `<start>`. The _definition_ of `<start>`
# contains the possible expansion rule that can match the given string. Each
# expansion rule can be thought of as a *parsing path*, with contiguous
# substrings of the given input string matched by the particular terms in the
# rule.
# 
# * When given a nonterminal to match the string, the essential idea is to
#   get the rules in the definition, and add them to the current set of
#   parsing paths to try with the given string. Within the parsing path, we have
#   a parsed index which denotes the progress of parsing that particular path
#   (i.e the point till which the string until now has been recognized by that
#   path, and any parents of this path). When a rule is newly added, this parsed
#   index is set to zero.
# 
# * We next look at our set of possible parsing paths, and check if any of these
#   paths start with a nonterminal. If one is found, then for that parsing path to
#   be completed with the given string, that nonterminal has to be recognized
#   first. So, we add the expansion rules corresponding to that nonterminal to the
#   list of possible parsing paths. We do this recursively.
# 
# * Now, examine the current letter in the input. Then select all parsing paths
#   that have that particular letter at the parsed index. These expressions can
#   now advance one step to the next index. We add such parsing paths to the
#   set of parsing paths to try for the next character.
# 
# * While doing this, any parsing paths have finished parsing, fetch its
#   corresponding nonterminal and advance all parsing paths that have that
#   nonterminal at the parsing index.
# 
# * Continue recursively until the parsing path corresponding to `<start>` has
#   finished.
# 
# 
# The chart parser depends on a chart (a table) for parsing. The columns
# correspond to the characters in the input string. Each column represents a set
# of *states*, and corresponds to the legal rules to follow from that point on.
# 
# Say we start with the following grammar:

sample_grammar = {
    '<start>': [['<A>','<B>']],
    '<A>': [['a', '<B>', 'c'], ['a', '<A>']],
    '<B>': [['b', '<C>'], ['<D>']],
    '<C>': [['c']],
    '<D>': [['d']]
}

# Earley parser produces a table of possible parse paths at each letter index of
# the table. Given an input `adcd`, we seed the column `0`  with:
# 
# ```
#    <start>: | <A> <B>
# ```
# 
# where the `|` represents the parsing index (also called the dot). This indicates
# that we are at the starting, and the next step is to identify `<A>`. After this
# rule is processed, the column would contain two more states
# 
# ```
#    <A>: | a <B> <c>
#    <A>: | a <A>
# ```
# which represents two parsing paths to complete `<A>`.
# 
# After processing of column `0` (corresponds to the start of the parse), we
# would find the following in column `1` (which corresponds to the end of parse for literal `a`)
# 
# ```
#    <A>: a | <B> c
#    <A>: a | <A>
#    <B>: | b <C>
#    <B>: | <D>
#    <A>: | a <B> c
#    <A>: | a <A>
#    <D>: | d
# ```
# 
# Similarly, the next column (column `2` corresponding to `d`) would contain the following.
# 
# ```
#    <D>: | d
#    <B>: <D> |
#    <A>: a <B> | c
# ```
# 
# Next, column `3` corresponding to `c` would contain:
# ```
#    <A>: a <B> c |
#    <start>: <A> | <B>
#    <B>: | <b> <C>
#    <B>: | <D>
#    <D>: | d
# ```
# 
# Finally, column `4` (`d`) would contain this at the end of processing.
# ```
#    <D>: d |
#    <B>: <D> |
#    <start>: <A> <B> |
# ```
# 
# This is how the table or the chart -- from where the parsing gets its name: chart parsing -- gets filled.
# 
# ## The Column Data Structure
# 
# The column contains a set of states. Each column corresponds
# to a character (or a token if tokens are used).
# Note that the states in a column corresponds to the parsing expression that will
# occur once that character has been read. That is, the first column will
# correspond to the parsing expression when no characters have been read.
# 
# The column allows for adding states, and checks to prevent duplication of
# states. Why do we need to prevent duplication? The problem is left recursion.
# We need to detect and curtail left recursion, which is indicated by non-unique
# states.

class Column:
    def __init__(self, index, letter):
        self.index, self.letter = index, letter
        self.states, self._unique = [], {}

    def __str__(self):
        return "%s chart[%d]\n%s" % (self.letter, self.index, "\n".join(
            str(state) for state in self.states if state.finished()))

    def to_repr(self):
        return "%s chart[%d]\n%s" % (self.letter, self.index, "\n".join(
            str(state) for state in self.states))

    def add(self, state):
        if state in self._unique:
            return self._unique[state]
        self._unique[state] = state
        self.states.append(state)
        state.e_col = self
        return self._unique[state]

# ## The State Data Structure
# 
# A state represents a parsing path (which corresponds to the nonterminal, and the
# expansion rule that is being followed) with the current parsed index. 
# Each state contains the following:
# 
# * name: The nonterminal that this rule represents.
# * expr: The rule that is being followed
# * dot:  The point till which parsing has happened in the rule.
# * s_col: The starting point for this rule.
# * e_col: The ending point for this rule.

class State:
    def __init__(self, name, expr, dot, s_col, e_col=None):
        self.name, self.expr, self.dot = name, expr, dot
        self.s_col, self.e_col = s_col, e_col

    def finished(self):
        return self.dot >= len(self.expr)

    def at_dot(self):
        return self.expr[self.dot] if self.dot < len(self.expr) else None

    def __str__(self):
        def idx(var):
            return var.index if var else -1

        return show_dot(self.name, self.expr, self.dot)

    def copy(self):
        return State(self.name, self.expr, self.dot, self.s_col, self.e_col)

    def _t(self):
        return (self.name, self.expr, self.dot, self.s_col.index)

    def __hash__(self):
        return hash(self._t())

    def __eq__(self, other):
        return self._t() == other._t()

    def advance(self):
        return State(self.name, self.expr, self.dot + 1, self.s_col)

def show_dot(sym, rule, pos, dotstr='|', extents=''):
    extents = str(extents)
    return sym + '::= ' + ' '.join([
           str(p)
           for p in [*rule[0:pos], dotstr, *rule[pos:]]]) + extents

# The convenience methods `finished()`, `advance()` and `at_dot()` should be
# self explanatory. For example,


class Parser:
    def recognize_on(self, text, start_symbol):
        raise NotImplemented()

    def parse_on(self, text, start_symbol):
        raise NotImplemented()

# We now initialize the Earley parser, which is a parser.

class EarleyParser(Parser):
    def __init__(self, grammar, log = False, parse_exceptions = True, **kwargs):
        self._grammar = grammar
        self.epsilon = nullable(grammar)
        self.log = log
        self.parse_exceptions = parse_exceptions

# ### Nonterminals Deriving Empty Strings
# 
# Earley parser handles *nullable* nonterminals separately. A nullable
# nonterminal is a nonterminal that can derive an empty string. That is
# at least one of the expansion rules must derive an empty string. An
# expansion rule derives an empty string if *all* of the tokens can
# derive the empty string. This means no terminal symbols (assuming we
# do not have zero width terminal symbols), and all nonterminal symbols
# can derive empty string.
# 
# In this implementation, we first initialize the list of first level
# nullable nonterminals that contain an empty expansion. That is, they
# directly derive the empty string.
# Next, we remove any expansion rule that contains a token as these
# expansion rules will not result in empty strings. Next, we start with
# our current list of nullable nonterminals, take one at a time, and
# remove them from the current expansion rules. If any expansion rule
# becomes empty, the corresponding nonterminal is added to the nullable
# nonterminal list. This continues until all nullable nonterminals
# are processed.

def is_nt(k):
    return (k[0], k[-1]) == ('<', '>')

def rem_terminals(g):
    g_cur = {}
    for k in g:
        alts = []
        for alt in g[k]:
            ts = [t for t in alt if not is_nt(t)]
            if not ts:
                alts.append(alt)
        if alts:
            g_cur[k] = alts
    return g_cur

def nullable(g):
    nullable_keys = {k for k in g if [] in g[k]}

    unprocessed  = list(nullable_keys)

    g_cur = rem_terminals(g)
    while unprocessed:
        nxt, *unprocessed = unprocessed
        g_nxt = {}
        for k in g_cur:
            g_alts = []
            for alt in g_cur[k]:
                alt_ = [t for t in alt if t != nxt]
                if not alt_:
                    nullable_keys.add(k)
                    unprocessed.append(k)
                    break
                else:
                    g_alts.append(alt_)
            if g_alts:
                g_nxt[k] = g_alts
        g_cur = g_nxt

    return nullable_keys




class EarleyParser(EarleyParser):
    def chart_parse(self, tokens, start, alts):
        chart = [self.create_column(i, tok)
                    for i, tok in enumerate([None, *tokens])]
        for alt in alts:
            chart[0].add(self.create_state(start, tuple(alt), 0, chart[0]))
        return self.fill_chart(chart)

    def create_column(self, i, tok): return Column(i, tok)

    def create_state(self, sym, alt, num, col): return State(sym, alt, num, col)



class EarleyParser(EarleyParser):
    def predict(self, col, sym, state):
        for alt in self._grammar[sym]:
            col.add(self.create_state(sym, tuple(alt), 0, col))
        if sym in self.epsilon:
            col.add(state.advance())


 
class EarleyParser(EarleyParser):
    def scan(self, col, state, letter):
        if letter == col.letter:
            col.add(state.advance())

# Here is our continuing example.



# As you can see, the `state[1]` in `chart[0]` that was waiting for `a` has
# advanced one letter after consuming `a`, and has been added to `chart[1]`.

# #### Complete
# 
# The `complete()` method is called if a particular state has finished the rule
# during execution. It first extracts the start column of the finished state, then
# for all states in the start column that is not finished, find the states that
# were parsing this current state (that is, we can go back to continue to parse
# those rules now). Next, shift them by one position, and add them to the current
# column.
# 
# For example, say the state we have is:
# ```
#    <A>: a | <B> c
#    <B>: b c |
# ```
# The state `<B> b c |` is complete, and we need to advance any state that
# has `<B>` at the dot to one index forward, which is `<A>: a <B> | c`
# 
# How do we determine the parent states? During predict, we added the predicted
# child states to the same column as that of the inspected state. So, the states
# will be found in the starting column of the current state, with the same symbol
# at_dot as that of the name of the completed state.
# 
# We advance all such parents (producing new states) and add the new states to the
# current column.

class EarleyParser(EarleyParser):
    def complete(self, col, state):
        parent_states = [st for st in state.s_col.states
                 if st.at_dot() == state.name]
        for st in parent_states:
            col.add(st.advance())

# You can see that the two states are waiting on `<A>` and `<B>`
# respectively at `at_dot()`.
# Hence, we run predict again to add the corresponding rules of `<A>` and `<B>`
# to the current column.


# As you can see, we have a list of states that are waiting
# for `b`, `a` and `d`.

# Our next letter is:

# We scan to populate `column 2`.

# As we expected, only `<D>` could advance to the next column (`chart[2]`)
# after reading `d`

# Finally, we use complete, so that we can advance the parents of the `<D>` state above.


# As you can see, that led to `<B>` being complete, and since `<B>` is
# complete, `<A>` also becomes complete.

# ### Filling The Chart
# 
# In the below algorithm, whenever the `at_dot()` is at a nonterminal
# symbol, the expansion rules of that nonterminal are added to the current
# rule (`predict()`) since each rule represents one valid parsing path. If on the
# other hand, `at_dot()` indicates processing finished for that nonterminal, we
# lookup the parent symbols and advance their parsing state (`complete()`). If we
# find that we are at a terminal symbol, we simply check if the current state can
# advance to parsing the next character (`scan()`). 

class EarleyParser(EarleyParser):
    def fill_chart(self, chart):
        for i, col in enumerate(chart):
            for state in col.states:
                if state.finished():
                    self.complete(col, state)
                else:
                    sym = state.at_dot()
                    if sym in self._grammar:
                        self.predict(col, sym, state)
                    else:
                        if i + 1 >= len(chart):
                            continue
                        self.scan(chart[i + 1], state, sym)
            if self.log: print(col.to_repr(), '\n')
        return chart

# ## Derivation trees
# 
# We use the following procedures to translate the parse forest to individual
# trees.

# ### parse_prefix

class EarleyParser(EarleyParser):
    def parse_prefix(self, text, start_symbol):
        alts = [tuple(alt) for alt in self._grammar[start_symbol]]
        self.table = self.chart_parse(text, start_symbol, alts)
        for col in reversed(self.table):
            states = [st for st in col.states
                if st.name == start_symbol
                   and st.expr in alts
                   and st.s_col.index == 0
            ]
            if states:
                return col.index, states
        return -1, []

# Here is an example of using it.

# ### parse_on
# 
# Our `parse_on()` method is slightly different from usual Earley implementations
# in that we accept any nonterminal symbol, not just nonterminal symbols with a
# single expansion rule. We accomplish this by computing a different chart for
# each expansion.

class EarleyParser(EarleyParser):
    def parse_on(self, text, start_symbol):
        starts = self.recognize_on(text, start_symbol)
        forest = self.parse_forest(self.table, starts)
        for tree in self.extract_trees(forest):
            yield tree

    def recognize_on(self, text, start_symbol):
        cursor, states = self.parse_prefix(text, start_symbol)
        starts = [s for s in states if s.finished()]

        if self.parse_exceptions:
            if cursor < len(text) or not starts:
                raise SyntaxError("at " + repr(text[cursor:]))
        return starts

# ### parse_paths
# 
# 
# The parse_paths() method tries to unify the given expression in `named_expr` with
# the parsed string. For that, it extracts the last symbol in `named_expr` and
# checks if it is a terminal symbol. If it is, then it checks the chart at `til` to
# see if the letter corresponding to the position matches the terminal symbol.
# If it does, extend our start index by the length of the symbol.
# 
# If the symbol was a nonterminal symbol, then we retrieve the parsed states
# at the current end column index (`til`) that correspond to the nonterminal
# symbol, and collect the start index. These are the end column indexes for
# the remaining expression.
# 
# Given our list of start indexes, we obtain the parse paths from the remaining
# expression. If we can obtain any, then we return the parse paths. If not, we
# return an empty list.

class EarleyParser(EarleyParser):
    def parse_paths(self, named_expr, chart, frm, til):
        def paths(state, start, k, e):
            if not e:
                return [[(state, k)]] if start == frm else []
            else:
                return [[(state, k)] + r
                        for r in self.parse_paths(e, chart, frm, start)]

        *expr, var = named_expr
        starts = None
        if var not in self._grammar:
            starts = ([(var, til - len(var),
                        't')] if til > 0 and chart[til].letter == var else [])
        else:
            starts = [(s, s.s_col.index, 'n') for s in chart[til].states
                      if s.finished() and s.name == var]

        return [p for s, start, k in starts for p in paths(s, start, k, expr)]


# That is, the parse path for `<start>` given the input `adcd` included
# recognizing the expression `<A><B>`. This was recognized by the two states:
# `<A>` from input(0) to input(2) which further involved recognizing the rule
# `a<B>c`, and the next state `<B>` from input(3) which involved recognizing the
# rule `<D>`.
# 
# ### parse_forest
# 
# The `parse_forest()` method takes the states which represents completed
# parses, and determines the possible ways that its expressions corresponded to
# the parsed expression. As we noted, it is here that we take care of multiple
# expansion rules for start symbol. (The `_parse_forest()` accepts a single
# state, and is the main driver that corresponds to traditional implementation,)
# For example, say we are parsing `1+2+3`, and the
# state has `[<expr>,+,<expr>]` in `expr`. It could have been parsed as either
# `[{<expr>:1+2},+,{<expr>:3}]` or `[{<expr>:1},+,{<expr>:2+3}]`.

class EarleyParser(EarleyParser):
    def forest(self, s, kind, chart):
        return self.parse_forest(chart, [s]) if kind == 'n' else (s, [])

    def _parse_forest(self, chart, state):
        pathexprs = self.parse_paths(state.expr, chart, state.s_col.index,
                                     state.e_col.index) if state.expr else []
        return (state.name, [[(v, k, chart) for v, k in reversed(pathexpr)]
                            for pathexpr in pathexprs])

    def parse_forest(self, chart, states):
        names = list({s.name for s in states})
        assert len(names) == 1
        forest = [self._parse_forest(chart, state) for state in states]
        return (names[0], [e for name, expr in forest for e in expr])

# ### extract_trees
# 
# We show how to extract a single tree first, and then generalize it to
# all trees.

class EarleyParser(EarleyParser):
    def extract_a_tree(self, forest_node):
        name, paths = forest_node
        if not paths:
            return (name, [])
        return (name, [self.extract_a_tree(self.forest(*p)) for p in paths[0]])

    def extract_trees(self, forest):
        yield self.extract_a_tree(forest)

# We need a way to display parse trees.


class O:
    def __init__(self, **keys): self.__dict__.update(keys)

OPTIONS   = O(V='│', H='─', L='└', J = '├')

def format_node(node):
    key = node[0]
    if key and (key[0], key[-1]) ==  ('<', '>'): return key
    return repr(key)

def get_children(node):
    return node[1]

def display_tree(node, format_node=format_node, get_children=get_children,
                 options=OPTIONS):
    print(format_node(node))
    for line in format_tree(node, format_node, get_children, options):
        print(line)

def format_tree(node, format_node, get_children, options, prefix=''):
    children = get_children(node)
    if not children: return
    *children, last_child = children
    for child in children:
        next_prefix = prefix + options.V + '   '
        yield from format_child(child, next_prefix, format_node, get_children,
                                options, prefix, False)
    last_prefix = prefix + '    '
    yield from format_child(last_child, last_prefix, format_node, get_children,
                            options, prefix, True)

def format_child(child, next_prefix, format_node, get_children, options, 
                 prefix, last):
    sep = (options.L if last else options.J)
    yield prefix + sep + options.H + ' ' + format_node(child)
    yield from format_tree(child, format_node, get_children, options, next_prefix)

format_parsetree = display_tree

# Displaying the tree

# ## Ambiguous Parsing
# 
# Ambiguous grammars can produce multiple derivation trees for some given string.
# In the above example, the `a_grammar` can parse `1+2+4` in as either `[1+2]+4` or `1+[2+4]`.
# 
# That is, we need to extract all derivation trees.
# We enhance our `extract_trees()` as below.
# 

import itertools as I

class EarleyParser(EarleyParser):
    def extract_trees(self, forest_node):
        name, paths = forest_node
        if not paths:
            yield (name, [])
        results = []
        for path in paths:
            ptrees = [self.extract_trees(self.forest(*p)) for p in path]
            for p in I.product(*ptrees):
                yield (name, p)
# ### Example
# 
# Using the same example,

# ## Almost Infinite Parse Trees
# 
# There is a problem with our `extract_trees()` method. The issue is that it is
# too eager. The parse forest can have an infinite number of trees, and at this
# time we effectively try to extract all at the same time. So, in case of
# such grammars our `extract_trees()` will fail. Here are two example grammars.

# The problem is that, our implementation of `extract_trees()` is eager.
# That is, it attempts to extract all inner parse trees before it can construct
# the outer parse tree. When there is a self reference, this results in recursion.
# Here is a simple extractor that avoids this problem. The idea here is that we
# randomly and lazily choose a node to expand, which avoids the infinite
# recursion.

import random

class SimpleExtractor:
    def __init__(self, parser, text, start_symbol):
        self.parser = parser
        cursor, states = parser.parse_prefix(text, start_symbol)
        starts = [s for s in states if s.finished()]
        if cursor < len(text) or not starts:
            raise SyntaxError("at " + repr(cursor))
        self.my_forest = parser.parse_forest(parser.table, starts)

    def extract_a_node(self, forest_node):
        name, paths = forest_node
        if not paths:
            return ((name, 0, 1), []), (name, [])
        cur_path, i, l = self.choose_path(paths)
        child_nodes = []
        pos_nodes = []
        for s, kind, chart in cur_path:
            f = self.parser.forest(s, kind, chart)
            postree, ntree = self.extract_a_node(f)
            child_nodes.append(ntree)
            pos_nodes.append(postree)

        return ((name, i, l), pos_nodes), (name, child_nodes)

    def choose_path(self, arr):
        l = len(arr)
        i = random.randrange(l)
        return arr[i], i, l

    def extract_a_tree(self):
        pos_tree, parse_tree = self.extract_a_node(self.my_forest)
        return parse_tree

# At this point, we also need a simple way to collapse the derivation tree to the original string

def tree_to_str(tree):
    expanded = []
    to_expand = [tree]
    while to_expand:
        (key, children, *rest), *to_expand = to_expand
        if is_nt(key):
            to_expand = list(children) + list(to_expand)
        else:
            assert not children
            expanded.append(key)
    return ''.join(expanded)


# However, `SimpleExtractor` has a problem. The issue is that since we rely on
# randomness for exploration, it gives no guarantees on the uniqueness of the
# returned trees. Hence, we need a way to keep track of the explored paths.
# our next class `EnahncedExtractor` can do that. In `EnhancedExtractor`,
# different exploration paths form a tree of nodes.
# 
# First we define a data-structure to keep track of explorations. 
# * `_chosen` contains the current choice
# * `next` holds the next choice done using `_chosen`
# * `total` holds he total number of choices for this node.

class ChoiceNode:
    def __init__(self, parent, total):
        self._p, self._chosen = parent, 0
        self._total, self.next = total, None

    def chosen(self):
        assert not self.finished()
        return self._chosen

    def __str__(self):
        return '%d(%s/%s %s)' % (self._i, str(self._chosen),
                                 str(self._total), str(self.next))
    def __repr__(self):
        return repr((self._i, self._chosen, self._total))

    def increment(self):
        # as soon as we increment, next becomes invalid
        self.next = None
        self._chosen += 1
        if self.finished():
            if self._p is None:
                return None
            return self._p.increment()
        return self

    def finished(self):
        return self._chosen >= self._total

# Initialization of the data-structure in the constructor.

class EnhancedExtractor(SimpleExtractor):
    def __init__(self, parser, text, start_symbol):
        super().__init__(parser, text, start_symbol)
        self.choices = choices = ChoiceNode(None, 1)

# Given an array and a choice node, `choose_path()` returns the element
# in array corresponding to the next choice node if it exists, or produces
# a new choice nodes, and returns that element.

class EnhancedExtractor(EnhancedExtractor):
    def choose_path(self, arr, choices):
        arr_len = len(arr)
        if choices.next is not None:
            if choices.next.finished():
                return None, None, None, choices.next
        else:
            choices.next = ChoiceNode(choices, arr_len)
        next_choice = choices.next.chosen()
        choices = choices.next
        return arr[next_choice], next_choice, arr_len, choices

# While extracting, we have a choice. Should we allow infinite forests,
# or should we have a finite number of trees with no direct recursion?
# A direct recursion is when there exists a parent node with the same
# nonterminal that parsed the same span. We choose here not to extract
# such trees. They can be added back after parsing.
# 
# This is a recursive procedure that inspects a node, extracts the path
# required to complete that node. A single path (corresponding to a nonterminal)
# may again be composed of a sequence of smaller paths. Such paths are again
# extracted using another call to extract_a_node() recursively.
# 
# What happens when we hit on one of the node recursions we want to avoid?
# In that case, we return the current choice node, which bubbles up to
# `extract_a_tree()`. That procedure increments the last choice, which in
# turn increments up the parents until we reach a choice node that still has
# options to explore.
# 
# What if we hit the end of choices for a particular choice node
# (i.e, we have exhausted paths that can be taken from a node)? In this case also,
# we return the current choice node, which bubbles up to `extract_a_tree()`.
# That procedure increments the last choice, which bubbles up to the next choice
# that has some unexplored paths.

class EnhancedExtractor(EnhancedExtractor):
    def extract_a_node(self, forest_node, seen, choices):
        name, paths = forest_node
        if not paths:
            return (name, []), choices

        cur_path, _i, _l, new_choices = self.choose_path(paths, choices)
        if cur_path is None:
            return None, new_choices
        child_nodes = []
        for s, kind, chart in cur_path:
            if kind == 't':
                child_nodes.append((s, []))
                continue
            nid = (s.name, s.s_col.index, s.e_col.index)
            if nid in seen:
                return None, new_choices
            f = self.parser.forest(s, kind, chart)
            ntree, newer_choices = self.extract_a_node(f, seen | {nid}, new_choices)
            if ntree is None:
                return None, newer_choices
            child_nodes.append(ntree)
            new_choices = newer_choices
        return (name, child_nodes), new_choices

# The `extract_a_tree()` is a depth first extractor of a single tree. It tries to
# extract a tree, and if the extraction returns None, it means that a particular
# choice was exhausted, or we hit on a recursion. In that case, we increment the
# choice, and explore a new path.

class EnhancedExtractor(EnhancedExtractor):
    def extract_a_tree(self):
        while not self.choices.finished():
            parse_tree, choices = self.extract_a_node(self.my_forest,
                                                      set(), self.choices)
            choices.increment()
            if parse_tree is not None:
                return parse_tree
        return None


# As can be seen from the parsing log for each letter, the number of states with
# representation `<A>: a <A> | (i, j)` increases at each stage, and these are
# simply a left over from the previous letter. They do not contribute anything
# more to the parse other than to simply complete these entries. However, they
# take up space, and require resources for inspection, contributing a factor of $$n$$ in analysis.
# 
# Joop Leo[^leo1991a] found that this inefficiency can be avoided by detecting
# right recursion. The idea is that before starting the completion step, check
# whether the current item has a deterministic reduction path. If such a path
# exists, add a copy of the topmost element of the deterministic reduction path
# to the current column, and return. If not, perform the original completion step.


# **Definition:** An item is said to be on the deterministic reduction path above
# $$[A \rightarrow \gamma.,i]$$ if it is $$[B \rightarrow \alpha A.,k]$$ with
# $$[B \rightarrow \alpha.A,k]$$ being the only item in $$I_i$$ with the
# dot in front of $$A$$, or if it is on the deterministic reduction path above
# $$[B \rightarrow \alpha A.,k]$$. An item on such a path is called topmost one
# if there is no item on the deterministic reduction path above it[^leo1991a].
# 
# Finding a deterministic reduction path is as follows:
# 
# Given a complete state, represented by `<A> : seq_1 | (s, e)` where `s` is the
# starting column for this rule, and `e` the current column, there is a
# deterministic reduction path above it if two constraints are satisfied.
# 
# 1. There exist a single item in the form `<B> : seq_2 | <A> (k, s)` in column `s`.
# 2. That should be the single item in s with dot in front of `<A>1
# 
# The resulting item is of the form `<B> : seq_2 <A> | (k, e)`, which is simply
# item from (1) advanced, and is considered above `<A>:.. (s, e)` in the
# deterministic reduction path. The `seq_1` and `seq_2` are arbitrary symbol sequences.
# 
# This forms the following chain of links, with `<A>:.. (s_1, e)` being the child
# of `<B>:.. (s_2, e)` etc.
# 
# Here is one way to visualize the chain:
# 
# ```
# <C> : seq_3 <B> | (s_3, e)  
#              |  constraints satisfied by <C> : seq_3 | <B> (s_3, s_2)
#             <B> : seq_2 <A> | (s_2, e)  
#                          | constraints satisfied by <B> : seq_2 | <A> (s_2, s_1)
#                         <A> : seq_1 | (s_1, e)
# ```
# 
# Essentially, what we want to do is to identify potential deterministic right
# recursion candidates, perform completion on them, and *throw away* the result.
# We do this until we reach the top. See Grune et al.[^grune2008parsing] for further information.
# 
# Note that the completions are in the same column (e), with each candidates with constraints satisfied in further and further earlier columns (as shown below):
# 
# ```
# <C> : seq_3 | <B> (s_3, s_2)  -->              <C> : seq_3 <B> | (s_3, e)
#                |
#               <B> : seq_2 | <A> (s_2, s_1) --> <B> : seq_2 <A> | (s_2, e)  
#                              |
#                             <A> : seq_1 |                        (s_1, e)
# ```
# Following this chain, the topmost item is the item `<C>:.. (s_3, e)` that does
# not have a parent. The topmost item needs to be saved is called a transitive
# item by Leo, and it is associated with the non-terminal symbol that started the
# lookup. The transitive item needs to be added to each column we inspect.
# 
# Here is the skeleton for the parser `LeoParser`.
# 
# We first save our original complete

class EarleyParser(EarleyParser):
    def earley_complete(self, col, state):
        parent_states = [st for st in state.s_col.states
                 if st.at_dot() == state.name]
        for st in parent_states:
            col.add(st.advance())

# 
class LeoParser(EarleyParser):
    def complete(self, col, state):
        return self.leo_complete(col, state)

    def leo_complete(self, col, state):
        detred = self.deterministic_reduction(state)
        if detred:
            col.add(detred.copy())
        else:
            self.earley_complete(col, state)

    def deterministic_reduction(self, state):
        raise NotImplemented()

# First, we update our `Column` class with the ability to add transitive items.
# Note that, while Leo asks the transitive to be added to the set $$I_k$$ there is
# no actual requirement for the transitive states to be added to the states list.
# The transitive items are only intended for memoization and not for the
# `fill_chart()` method. Hence, we track them separately.

class Column(Column):
    def __init__(self, index, letter):
        self.index, self.letter = index, letter
        self.states, self._unique, self.transitives = [], {}, {}

    def add_transitive(self, key, state):
        assert key not in self.transitives
        self.transitives[key] = state
        return self.transitives[key]

# Remember the picture we drew of the deterministic path?
# 
# ```
#     <C> : seq_3 <B> | (s_3, e)
#                  |  constraints satisfied by <C> : seq_3 | <B> (s_3, s_2)
#                 <B> : seq_2 <A> | (s_2, e)
#                              | constraints satisfied by <B> : seq_2 | <A> (s_2, s_1)
#                             <A> : seq_1 | (s_1, e)
# ```
# 
# We define a function `uniq_postdot()` that given the item `<A> := seq_1 | (s_1, e)`,
# returns a `<B> : seq_2 | <A> (s_2, s_1)` that satisfies the constraints
# mentioned in the above picture.

class LeoParser(LeoParser):
    def uniq_postdot(self, st_A):
        col_s1 = st_A.s_col
        parent_states = [
            s for s in col_s1.states if s.expr and s.at_dot() == st_A.name
        ]
        if len(parent_states) > 1:
            return None
        matching_st_B = [s for s in parent_states if s.dot == len(s.expr) - 1]
        return matching_st_B[0] if matching_st_B else None

# 

# We next define the function `get_top()` that is the core of deterministic
# reduction which gets the topmost state above the current state `(A)`.

class LeoParser(LeoParser):
    def get_top(self, state_A):
        st_B_inc = self.uniq_postdot(state_A)
        if not st_B_inc:
            return None

        t_name = st_B_inc.name
        if t_name in st_B_inc.e_col.transitives:
            return st_B_inc.e_col.transitives[t_name]

        st_B = st_B_inc.advance()

        top = self.get_top(st_B) or st_B
        return st_B_inc.e_col.add_transitive(t_name, top)

# Once we have the machinery in place, `deterministic_reduction()` itself is
# simply a wrapper to call `get_top()`

class LeoParser(LeoParser):
    def deterministic_reduction(self, state):
        return self.get_top(state)

# 


# We have fixed the complexity bounds. However, because we are saving only the topmost item of a right recursion, we need to fix our parser to be aware of our fix while extracting parse trees.
# 
# We first change the definition of `add_transitive()` so that results of deterministic reduction can be identified later.

class Column(Column):
    def add_transitive(self, key, state):
        assert key not in self.transitives
        self.transitives[key] = self.create_tstate(state)
        return self.transitives[key]

    def create_tstate(self, state):
        return TState(state.name, state.expr, state.dot, state.s_col, state.e_col)


# We also need a `back()` method to create the constraints.

class State(State):
    def back(self):
        return TState(self.name, self.expr, self.dot - 1, self.s_col, self.e_col)

# We update `copy()` to make `TState` items instead.

class TState(State):
    def copy(self):
        return TState(self.name, self.expr, self.dot, self.s_col, self.e_col)

# We now modify the `LeoParser` to keep track of the chain of constrains that we mentioned earlier.

class LeoParser(LeoParser):
    def __init__(self, grammar, **kwargs):
        super().__init__(grammar, **kwargs)
        self._postdots = {}

# Next, we update the `uniq_postdot()` so that it tracks the chain of links.

class LeoParser(LeoParser):
    def uniq_postdot(self, st_A):
        col_s1 = st_A.s_col
        parent_states = [
            s for s in col_s1.states if s.expr and s.at_dot() == st_A.name
        ]
        if len(parent_states) > 1:
            return None
        matching_st_B = [s for s in parent_states if s.dot == len(s.expr) - 1]
        if matching_st_B:
            self._postdots[matching_st_B[0]._t()] = st_A
            return matching_st_B[0]
        return None

# We next define a method `expand_tstate()` that, when given a `TState`, generates
# all the intermediate links that we threw away earlier for a given end column.

class LeoParser(LeoParser):
    def expand_tstate(self, state, e):
        if state._t() not in self._postdots:
            return
        c_C = self._postdots[state._t()]
        e.add(c_C.advance())
        self.expand_tstate(c_C.back(), e)

# We define a `rearrange()` method to generate a reversed table where each column contains states that start at that column.

class LeoParser(LeoParser):
    def rearrange(self, table):
        f_table = [self.create_column(c.index, c.letter) for c in table]
        for col in table:
            for s in col.states:
                f_table[s.s_col.index].states.append(s)
        return f_table


class LeoParser(LeoParser):
    def parse_on(self, text, start_symbol):
        starts = self.recognize_on(text, start_symbol)
        self.r_table = self.rearrange(self.table)
        forest = self.parse_forest(self.table, starts)
        for tree in self.extract_trees(forest):
            yield tree



class LeoParser(LeoParser):
    def parse_forest(self, chart, states):
        for state in states:
            if isinstance(state, TState):
                self.expand_tstate(state.back(), state.e_col)

        return super().parse_forest(chart, states)

