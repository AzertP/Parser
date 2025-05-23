import final_parser.GLL as gll
import simplefuzzer as fuzzer
import earleyparser as ep

def test0():
    def remove_whitespace(json_str):
            return [char for char in json_str if char not in " \t\n\r"]

    grammar = {
        "<json>": [["<object>"], ["<array>"]],

        "<object>": [["{", "<members>", "}"], ["{", "}"]],
        "<members>": [["<pair>"], ["<pair>", ",", "<members>"]],
        "<pair>": [["<string>", ":", "<value>"]],

        "<array>": [["[", "<elements>", "]"], ["[", "]"]],
        "<elements>": [["<value>"], ["<value>", ",", "<elements>"]],

        "<value>": [
            ["<string>"],
            ["<number>"],
            ["<object>"],
            ["<array>"],
            ["true"],
            ["false"],
            ["null"]
        ],

        "<string>": [["\"", "<characters>", "\""]],
        "<characters>": [["<character>", "<characters>"], []],  # ε (empty string)
        
        "<character>": [["%s" % chr(i)] for i in range(32, 127) if i not in [34, 92]],  # Excluding '"' (34) and '\' (92)

        "<number>": [["<integer>", "<fraction>", "<exponent>"]],
        "<integer>": [["-", "<digit>", "<digits>"], ["<digit>", "<digits>"]],
        "<fraction>": [[".", "<digit>", "<digits>"], []],  # ε (optional fraction)
        "<exponent>": [["e", "<sign>", "<digit>", "<digits>"], ["E", "<sign>", "<digit>", "<digits>"], []],  # ε (optional exponent)
        "<sign>": [["+"], ["-"], []],  # ε (optional sign)

        "<digits>": [["<digit>", "<digits>"], []],  # ε (empty or sequence of digits)
        "<digit>": [["%s" % str(i)] for i in range(10)]  # Generates ["0"], ["1"], ..., ["9"]
    }
    start = "<json>"

    json_test1 = """
    {
        "name": "Alice",
        "age": 25,
        "address": {
            "street": "123 Main St",
            "city": "Wonderland",
            "zip": "12345"
        }
    }
    """
    test_str = ("".join(remove_whitespace(json_test1)))
    print(test_str)
    gll_parser = gll.compile_grammar(grammar)
    gll_result = gll_parser.parse_on(test_str, start)[0]
    
    r = fuzzer.tree_to_string(gll_result)
    ep.display_tree(gll_result)
    print(r)
        
test0()