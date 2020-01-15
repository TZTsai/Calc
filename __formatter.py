from __builtins import *
from sympy import latex
from re import sub as translate

def matrix(mat):
    mat = [[format(x) for x in row] for row in mat]
    space = max([max([len(s) for s in row]) for row in mat])
    just_space = lambda s: s.ljust(space)
    row_str = lambda row, start, end: \
        f"{start} {' '.join(map(just_space, row))}{end}\n"
    col_num = len(mat[0])
    s = row_str(['']*col_num, '┏', '┓')
    for row in mat: s += row_str(row, '┃', '┃')
    s += row_str(['']*col_num, '┗', '┛')
    return s

# latex_matrix = lambda mat: '\\begin{bmatrix}' + ' \\\\ '.join([
#     ' & '.join(map(format,row)) for row in mat]) + '\\end{bmatrix}'

# latex_table = lambda mat: r'\begin{table}[h!]\n\centering' + \
#     f"\n\\begin{{tabular}}{{{'|c'*len(mat[0])+'|'}}}\n\\hline\n" + \
#     ' \\\\ \\hline\n'.join([' & '.join(map(format,row)) for row in mat]) + \
#     ' \\\\ \\hline\n\\end{tabular}\n\\end{table}'

def format(val):
    def format_float(x):
        prec = config.prec
        return float(f'%.{prec}g' % x)
    def pos_scinum_str(x):
        supscripts = '⁰¹²³⁴⁵⁶⁷⁸⁹'
        e = floor(log10(x))
        b = format_float(x/10**e)
        supscript_pos = lambda n: ''.join([supscripts[int(i)] for i in str(n)])
        supscript = lambda n: '⁻' + supscript_pos(-n) if e < 0 else supscript_pos(n)
        return f"{b}×10{supscript(e)}"
    def is_matrix(x):
        return is_iterable(x) and len(x) > 1 and is_iterable(x[0]) and \
            all(is_iterable(it) and len(it) == len(x[0]) for it in x[1:])
    if config.latex:
        return latex(Matrix(val) if is_matrix(val) else val)
    if is_number(val):
        if isinstance(val, Rational):
            if type(val) == Fraction:
                val.limit_denominator(10**config.prec)
            return str(val)
        elif type(val) == complex:
            re, im = format_float(val.real), format_float(val.imag)
            return f"{re} {'-' if im<0 else '+'} {abs(im)}i"
        elif abs(val) == inf:
            return '∞'
        elif abs(val) <= 0.001 or abs(val) >= 10000:
            if val == 0: return '0'
            elif val > 0: return pos_scinum_str(val)
            else: return '-'+pos_scinum_str(-val)
        else: return str(format_float(val))
    elif is_iterable(val):
        if is_matrix(val):
            return matrix(val)
        else:
            return '['+', '.join(map(lambda v: ('\n' if is_matrix(v) 
                else '') + format(v), val))+']'
    else:
        def repl_star(match):
            s = match.string
            starpos, endpos = match.span('varpar')
            return s[:starpos] + s[starpos+1:endpos] + '... ' + s[endpos:]
        mapping = {r'\*\*': '^', r'^function .*(?P<varpar>\*\w)\:': repl_star, r'\*': '\u00b7'}
        s = str(val)
        for k in mapping:
            s = translate(k, mapping[k], s)
        return s


config = lambda: None
# config.matrix = matrix
config.prec = 4
config.latex = False