print('enter eval.py')
from parse import calc_parse, is_name, is_tree, tag, drop_tag
from builtin import binary_ops, unary_l_ops, unary_r_ops, builtins, special_names
from funcs import Symbol, is_list
from objects import Env, stack, Op, Attr, Map
import config
from functools import wraps


Builtins = Env(name='_builtins_', binds=builtins)

def GlobalEnv():
    Global = Env(name='_global_', parent=Builtins)
    Global._ans = []
    return Global

Global = GlobalEnv()


def calc_eval(exp):  # only for testing; calc_exec will use eval_tree
    suppress = exp[-1] == ';'
    if suppress: exp = exp[:-1]
    tree, rest = calc_parse(exp)
    if rest: raise SyntaxError(f'syntax error in "{rest}"')
    result = eval_tree(tree, Global)
    if result is not None and not suppress:
        Global._ans.append(result)
        return result


# some utils
def get_op(ops):
    def get(tr): return ops[tr[1]]
    return get

def hold_tree(f):
    @wraps(f)
    def _f(tr):
        if any(is_tree(t) for t in tr):
            return tr
        else:
            return f(tr)
    return _f

# def forbid_tree(f):
#     @wraps(f)
#     def _f(tr, env):
#         if any(is_tree(t) for t in tr[1:]):
#             return RuntimeError
#         else:
#             return f(tr, env)
#     return _f


# substitution rules

def EMPTY(tr): return None

def LINE(tr): return tr[-1]

def COMPLEX(tr):
    re, pm, im = tr[1:]
    return re + im*1j if pm == '+' else re - im*1j

def REAL(tr):
    if len(tr) > 2: return eval(tr[1]+'e'+tr[2])
    else: return eval(tr[1])

def BIN(tr): return eval(tr[1])

def HEX(tr): return eval(tr[1])

def ATTR(tr): return Attr(tr[1])

def SYM(tr): return Symbol(tr[1])

def ANS(tr):
    s = tr[1]
    if all(c == '_' for c in s):
        id = -len(s)
    else:
        try: id = int(s[1:])
        except: raise SyntaxError('invalid history index!')
    return Global._ans[id]

def BODY(tr):
    return tr[2] if tr[1] == 'PRINTED' else tr[1]

@hold_tree
def SEQtoTREE(tr):
    # stk = stack()
    ops = stack()
    vals = stack()
    
    def pop_val():
        v = vals.pop()
        if isinstance(v, Op):
            raise SyntaxError('op sequence in disorder')
        return v

    def pop_op():
        op = ops.pop()
        if not isinstance(op, Op):
            raise SyntaxError('op sequence in disorder')
        return op
    
    def hold_tree(op):
        "Convert $op to a function that keeps the tree form."
        @wraps(op)
        def f(*args):
            incomplete = any(is_tree(arg) for arg in args)
            if op.type == 'BOP':
                n1, n2 = args
                if incomplete:
                    return ['SEQ', n1, op, n2]
                else:
                    return op(n1, n2)
            else:
                n, = args
                if incomplete:
                    if op.type == 'LOP':
                        return ['SEQ', op, n]
                    else:
                        return ['SEQ', n, op]
                else:
                    return op(n)
        return f

    def reduce():
        op = pop_op()
        # op = hold_tree(op)
        if op.type == 'BOP':
            n2 = pop_val()
            n1 = pop_val()
            args = n1, n2
        else:
            args = pop_val(),
        vals.push(op(*args))

    def push(x):
        if isinstance(x, Op):
            while ops:
                op = ops.peek()
                if x.priority <= op.priority:
                    reduce()
                else: break
            ops.push(x)
        else:
            if not (push.prev is None or
                    isinstance(push.prev, Op)):
                ops.push(binary_ops[''])
            if isinstance(x, Env):
                if hasattr(x, 'val'):
                    x = x.val  # convert Env to its 'val'
            vals.push(x)
        push.prev = x
    push.prev = None

    for x in tr[1:]: push(x)
    while ops: reduce()
    val = pop_val()
    assert not vals, 'sequence evaluation failed'
    return val

@hold_tree
def FIELD(tr):
    field = tr[1]
    for attr in tr[2:]:
        field = attr.getFrom(field)
    return field

@hold_tree
def LIST(tr):
    lst = []
    for it in tr[1:]:
        if callable(it) and it.__name__ == 'UNPACK':
            lst.extend(it())
        else:
            lst.append(it)
    return tuple(lst)

@hold_tree
def SYMLIST(tr): return tr[1:]

@hold_tree
def SLICE(tr): return slice(*tr[1:])


## eval rules which require environment

def NAME(tr, env):
    name = tr[1]
    try: return env[name]
    except KeyError:
        if env is Global and config.symbolic:
            return Symbol(name)
        else:
            raise NameError(f'unbound symbol \'{tr}\'')

def PRINT(tr, env):
    exec('print(f"%s")' % tr[1][1:-1], env.all())
    return 'PRINTED'

def IF_ELSE(tr, env):
    _, t_case, cond, f_case = tr
    cond = eval_tree(cond, env)
    return eval_tree(t_case if cond else f_case, env)

def WHEN(tr, env):
    *cases, default = tr[1:]
    for _, cond, exp in cases:
        if eval_tree(cond, env):
            return eval_tree(exp, env)
    return eval_tree(default, env)

def GEN_LST(tr, env):
    def generate(exp, constraints):
        if constraints:
            constr = constraints[0]
            _, form, ran, *spec = constr
            if spec: spec = spec[0]
            for val in eval_tree(ran, local):
                match(form, val, local)
                if not spec or eval_tree(spec, local):
                    yield from generate(exp, constraints[1:])
        else:
            yield eval_tree(exp, local)
    _, exp, *constraints = tr
    local = env.child()
    return tuple(generate(exp, constraints))

def DICT(tr, env):
    local = env.child()
    for t in tr[1:]:
        BIND(t, local)
    return local

MAP = Map

def CLOSURE(tr, env):
    _, local, body = tr
    if not isinstance(local, Env): return tr
    result = eval_tree(body, env=local)
    if is_tree(result):  # should only happen when @ is used
        result = eval_tree(body, env=env)
    return result

def AT(tr, env):
    drop_tag(tr, 'AT')
    return eval_tree(tr, env)

def BIND(tr, env):
    i = 1
    var = tr[i]; i+=1
    try:
        drop_tag(tr[i], 'AT')
        at = tr[i]; i+=1
    except:
        at = None
    exp = tr[i]; i+=1
    try:
        assert tag(tr[i]) == 'DOC'
        doc = tr[i][1][1:-1]
    except:
        doc = None
    define(var, exp, env, at, doc)
    
def MATCH(tr, env):
    _, form, val = tr
    local = env.child()
    match(form, val, local)
    return local

def match(form, val, local: Env):
    vals = list(val) if is_list(val) else [val]
        
    if form[0] != 'FORM': split_pars(form, local)
    _, pars, opt_pars, ext_par = form
    
    if len(pars) > len(vals):
        raise ValueError(f'not enough items in {vals} to match')
    
    for par in pars:
        val = vals.pop(0)
        if is_name(par): 
            local[par] = val
        else:
            match(par, val, local)
            
    opt_pars = opt_pars.copy()
    while opt_pars and vals:
        define(opt_pars.pop(0)[0], vals.pop(0), local)
    for opt_par, default in opt_pars:
        define(opt_par, default, local)
        
    if ext_par:
        local[ext_par] = tuple(vals)
        

def define(var, exp, env, at=None, doc=None):

    def def_(name, val, env):
        if name in special_names:
            raise NameError('"%s" cannot be bound ' % name
                            + '(reserved for special use)')

        if isinstance(val, Map):
            val.__name__ = name
        elif isinstance(val, Env):
            val.name = name
                
        if doc:
            if not isinstance(val, Env):
                val = Env(val, name=name)
            try: val.__doc__ += '\n' + doc
            except: val.__doc__ = doc
            
        env[name] = val

    def def_all(vars, val, env):
        t, vars = vars[0], vars[1:]
        if t == 'VARS':
            assert is_list(val), 'vars assigned to non-list'
            assert len(vars) == len(val), 'list lengths mismatch'
            for var, item in zip(vars, val):
                def_all(var, item, env)
        else:
            def_(vars[0], val, env)
    
    tag_ = tag(var)

    # evaluate the exp
    if tag_ == 'FUNC':
        form = var[2]
        val = Map(['MAP', form, exp], env, at)
    else:
        assert at is None, 'invalid use of @'
        val = eval_tree(exp, env)

    # bind the variable(s)
    if tag_ == 'VARS':
        def_all(var, val, env)
    else:
        name = var[1] if tag_ == 'NAME' else var[1][1]
        def_(name, val, env)
        
def split_field(tr):
    if tr[0] == 'NAME':
        attr = tr[1]
        parent = Global
    elif tr[0] == 'FIELD':
        parent, attr = tr[:-1], tr[-1][1]
        parent = eval_tree(parent, Global) \
            if len(parent) > 1 else Global
    else:
        raise TypeError('wrong type for split_field')
    return parent, attr


# these rules are commands in the calc

def DEF(tr):
    _, env, bind = tr
    upper, env_name = split_field(env)
    env = upper[env_name]
    if not isinstance(env, Env):
        # if env is not Env instance, convert it
        env = upper.child(env, env_name)
        upper[env_name] = env
    BIND(bind, env)
    
def DEL(tr):
    for t in tr[1:]:
        field, attr = split_field(t)
        field.delete(attr)

def DIR(tr):
    if len(tr) == 1:
        field = Global
    else:
        field = tr[1]
        print(f"(dir): {field.dir()}")
    for name, val in field.items():
        print(f"{name}: {val}")

def LOAD(tr):
    test = '-t' in tr
    verbose = '-v' in tr
    overwrite = '-w' in tr
    path = 'scripts/%s.cal' % '/'.join(tr[1].split('.'))

    global Global
    current_global = Global
    Global = GlobalEnv()  # a new global env
    LOAD.run(path, test, start=0, verbose=verbose)
    
    if overwrite:
        current_global.update(Global)
    else:
        for name in Global:
            if name not in current_global:
                current_global[name] = Global[name]
            else:
                print(f'name {name} not loaded because it is bounded')
    Global = current_global

def IMPORT(tr):
    modname = tr[1]
    verbose = '-v' in tr
    overwrite = '-w' in tr
    env = definitions = {}
    try:
        exec('from modules.%s import export'%modname, env)
        definitions = env['export']
    except ModuleNotFoundError:
        exec('from sympy import %s'%modname, definitions)
    
    for name, val in definitions.items():
        if name not in Global or overwrite:
            if verbose: print(f'imported: {name}')
            Global[name] = val

def CONF(tr):
    conf = tr[1]
    if conf in ('prec', 'precision'):
        if len(tr) == 2:
            print(config.precision)
        else:
            config.precision = max(1, int(tr[2]))
    elif conf == 'tolerance':
        if len(tr) == 2:
            print(config.tolerance)
        else:
            config.tolerance = float(tr[2])
    elif hasattr(config, conf):
        if len(tr) == 2:
            print(getattr(config, conf))
        else:
            setattr(config, conf, tr[2] in ('on', '1'))
    else:
        raise ValueError('no such field in the config')
    

def eval_tree(tree, env):
    if not is_tree(tree):
        return tree
    type_ = tag(tree)
    
    if type_ not in delay_types:
        for i in range(1, len(tree)):
            tree[i] = eval_tree(tree[i], env)
    elif type_ == 'DELAY' and env:
        drop_tag(tree, 'DELAY')
        return tree
    
    if type_ in subs_rules:
        return subs_rules[type_](tree)
    elif type_ in eval_rules and env:
        return eval_rules[type_](tree, env)
    elif type_ in exec_rules:
        exec_rules[type_](tree)
        return
    else:
        return tree


Map.match = match
Map.eval  = eval_tree


LOAD.run  = None  # set this in calc.py

delay_types = {
    'DELAY',    'DEF',      'BIND',     'IF_ELSE',
    'DEL',      'WHEN',     'GEN_LST',  'PAR_LST',
    'FORM',     'DICT'
}

subs_rules = {
    'LINE': LINE,               'BODY': BODY,
    'ANS': ANS,                 'SYM': SYM,
    'FIELD': FIELD,             'ATTR': ATTR,
    'REAL': REAL,               'COMPLEX': COMPLEX,
    'BIN': BIN,                 'HEX': HEX,
    'IDC_LST': LIST,            'SLICE': SLICE,
    'VAL_LST': LIST,            'SYM_LST': SYMLIST, 
    'SEQ': SEQtoTREE,           'BOP': get_op(binary_ops),
    'LOP': get_op(unary_l_ops), 'ROP': get_op(unary_r_ops),
    'EMPTY': EMPTY,
}

eval_rules = {
    'NAME': NAME,               'MAP': MAP,
    'PRINT': PRINT,             'DICT': DICT,
    'MATCH': MATCH,             'IF_ELSE': IF_ELSE,
    'WHEN': WHEN,               'CLOSURE': CLOSURE,
    'EXP': eval_tree,           'BIND': BIND,
    'GEN_LST': GEN_LST,         'AT': AT
}

exec_rules = {
    'DIR': DIR,                 'CONF': CONF,
    'LOAD': LOAD,               'IMPORT': IMPORT,
    'DEL': DEL,                 'DEF': DEF
}


if __name__ == "__main__":
    import doctest
    doctest.testmod()