"""A "Super" Python Bytecode Disassembler for Py2crazy"""
# Created by Philip Guo on 2013-07-12
# based on coverage.py/lab/disgen.py by Ned Batchelder
# https://bitbucket.org/ned/coveragepy

import sys
import types
import collections

import ast_extents
import inspect

from opcode import *
from opcode import __all__ as _opcodes_all

__all__ = ["get_bytecode_map", "disassemble", "distb", "disco",
           "findlinestarts", "findlabels"] + _opcodes_all
del _opcodes_all

FN = "<super_dis code>"

# the main event!
def get_bytecode_map(source, verbose=False):
    source_lines = source.splitlines()
    module_code = compile(source, FN, "exec")
    
    extent_map = ast_extents.create_extent_map(source)

    # Key: (code.co_code string, line number, col_offset, instruction offset)
    #      This should be sufficient to pinpoint an exact bytecode.
    #      Note that instruction offset by itself isn't enough since
    #      multiple functions can be defined within a file, each
    #      with their own offsets starting at 0.
    # Value: DisLine object
    bytecode_map = {}

    def helper(cod):
        child_code = set()
        for disline in disgen(cod, extent_map):
            if disline.child_code_obj:
                child_code.add(disline.child_code_obj)
            if verbose:
                if disline.first and disline.offset > 0:
                    print('')
                print(format_dis_line(disline, source_lines))


            key = (disline.code_str, disline.lineno, disline.column, disline.offset)

            if verbose and key in bytecode_map:
                print "WARNING!", key, "already in bytecode_map"
            bytecode_map[key] = disline

        # recurse (TODO: how to avoid infinite loops?)
        for c in child_code:
            if c.co_filename == FN: # and c.co_name != '<genexpr>':
                if verbose:
                    print
                    print 'Disassembling function', c.co_name
                helper(c)

    helper(module_code)
    return bytecode_map


YELLOW_BG = '\033[43m'
BLACK_FG = '\033[30m'
STOP_FG = '\033[39m'
STOP_BG = '\033[49m'

def highlight(s):
  return YELLOW_BG + BLACK_FG + s + STOP_FG + STOP_BG

def format_dis_line(disline, source_lines):
    lc = (disline.lineno, disline.column)
    cod_line = source_lines[disline.lineno - 1]

    if disline.first:
        lineno = '%3d' % disline.lineno
    else:
        lineno = '   '

    cod_line = cod_line[:disline.start_col] + \
               highlight(cod_line[disline.start_col:disline.start_col+disline.extent]) + \
               cod_line[disline.start_col+disline.extent:]

    if disline.target:
        label = ">>"
    else:
        label = "  "
    return "%s %s %4r %-20s %s" % (lineno, label, disline.offset, disline.opcode, cod_line)

def disgen(x, extent_map=None):
    """Disassemble methods, functions, or code."""
    if hasattr(x, 'im_func'):
        x = x.im_func
    if hasattr(x, 'func_code'):
        x = x.func_code
    if hasattr(x, 'co_code'):
        return disassemble(x, extent_map)
    else:
        raise TypeError(
            "don't know how to disassemble %s objects" %
            type(x).__name__
        )


# Note that [start_col, start_col + extent] is the range to highlight,
# and that column and start_col don't necessarily need to be identical
DisLine = collections.namedtuple(
    'DisLine',
    "lineno column start_col extent first target offset opcode oparg argstr code_str child_code_obj"
    )

def disassemble(co, extent_map):
    """Disassemble a code object."""
    lasti=-1

    code = co.co_code
    labels = findlabels(code)
    linestarts = dict(findlinestarts(co))
    n = len(code)
    i = 0
    extended_arg = 0
    free = None

    dislines = []
    lineno = linestarts[0]

    # "Remembers" what special (start_col, extent) value has already
    # been set for a particular (lineno, col_offset) combo with a special
    # AST type name
    # Key: (lineno, col_offset)
    # Value: name of AST type that's been set for this location
    hysteresis_map = {}

    while i < n:
        op = byte_from_code(code, i)
        first = i in linestarts
        if first:
            lineno = linestarts[i]

        #if i == lasti: print '-->',
        #else: print '   ',
        target = i in labels
        offset = i
        opcode = opname[op]

        try:
            # this might be pretty darn controversial, but override
            # lineno with the entry from co_coltab. seems to do a
            # reasonable job for (ANNOYING!) multi-line expressions ...
            lineno, column = co.co_coltab[i]
        except KeyError:
            # when there's an error, punt to column 0
            column = 0

        child_code_obj = None # is this loading a code object that we should maybe recurse into?

        i = i+1
        if op >= HAVE_ARGUMENT:
            oparg = byte_from_code(code, i) + byte_from_code(code, i+1)*256 + extended_arg
            extended_arg = 0
            i = i+2
            if op == EXTENDED_ARG:
                extended_arg = oparg*65536
            if op in hasconst:
                c = co.co_consts[oparg]
                argstr = '(' + repr(c) + ')'
                if inspect.iscode(c):
                    child_code_obj = c
            elif op in hasname:
                argstr = '(' + co.co_names[oparg] + ')'
            elif op in hasjabs:
                argstr = '(-> ' + repr(oparg) + ')'
            elif op in hasjrel:
                argstr = '(-> ' + repr(i + oparg) + ')'
            elif op in haslocal:
                argstr = '(' + co.co_varnames[oparg] + ')'
            elif op in hascompare:
                argstr = '(' + cmp_op[oparg] + ')'
            elif op in hasfree:
                if free is None:
                    free = co.co_cellvars + co.co_freevars
                argstr = '(' + free[oparg] + ')'
            else:
                argstr = ""
        else:
            oparg = None
            argstr = ""


        start_col, extent = column, 1 # set boring defaults
        lc = (lineno, column)
        if lc in extent_map:
          v = dict(extent_map[lc]) # make a copy so we can delete from it

          done = False

          # special case hacks!
          # make these non-exclusive if's
          #
          # TODO: implement hysteresis feature for ALL of these special
          # types, not just function calls. It's tricky because the
          # different hystereses might interact weirdly and conflict
          # with one another!
          if 'Subscript' in v:
            if '_SUBSCR' in opcode: # subscripting opcodes
              start_col, extent = v['Subscript']
              done = True
            else:
              if len(v) > 1:
                del v['Subscript']
          if 'List' in v:
            if 'BUILD_LIST' == opcode: # subscripting opcodes
              start_col, extent = v['List']
              done = True
            else:
              if len(v) > 1:
                del v['List']
          if 'Tuple' in v:
            if 'BUILD_TUPLE' == opcode: # subscripting opcodes
              start_col, extent = v['Tuple']
              done = True
            else:
              if len(v) > 1:
                del v['Tuple']

          if 'Slice' in v:
            if 'SLICE' in opcode:
              start_col, extent = v['Slice']
              done = True
            else:
              if len(v) > 1:
                del v['Slice']

          # very brittle -- do this last due to hysteresis
          if 'Call' in v:
            # Apply hysteresis to "remember" the call on this line so
            # that bytecodes afterward with the same lc (lineno,
            # col_offset) value can also get the same start_col and extent.
            #
            # e.g., in this example, the PRINT_ITEM and PRINT_NEWLINE
            # after CALL_FUNCTION have the same lc as CALL_FUNCTION. So
            # after we set start_col, extent = v['Call'], we also set
            # hysteresis_map[lc] so that the PRINT_ITEM and PRINT_NEWLINE
            # instructions also get the same consistent start_col and
            # extent values.
            #          6 CALL_FUNCTION        print repr("aoooooooooga")
            #          9 PRINT_ITEM           print repr("aoooooooooga")
            #         10 PRINT_NEWLINE        print repr("aoooooooooga")
            #
            # very subtle -- if we're already done, then don't try
            # this hysteresis_map trick!
            if opcode.startswith('CALL_') or \
               (not done and hysteresis_map.get(lc, None) == 'Call'):
              start_col, extent = v['Call']
              hysteresis_map[lc] = 'Call'
              done = True
            else:
              if len(v) > 1:
                del v['Call']

          if not done:
            # there should be only one surviving entry left after all
            # the possible deletions!
            assert len(v.values()) == 1, v
            start_col, extent = v.values()[0]

          assert start_col >= 0 and extent >= 0


        yield DisLine(lineno=lineno, column=column,
                      start_col=start_col, extent=extent,
                      first=first, target=target,
                      offset=offset,
                      opcode=opcode, oparg=oparg,
                      argstr=argstr,
                      code_str=code,
                      child_code_obj=child_code_obj)


def byte_from_code(code, i):
    byte = code[i]
    if not isinstance(byte, int):
        byte = ord(byte)
    return byte

def findlabels(code):
    """Detect all offsets in a byte code which are jump targets.

    Return the list of offsets.

    """
    labels = []
    n = len(code)
    i = 0
    while i < n:
        op = byte_from_code(code, i)
        i = i+1
        if op >= HAVE_ARGUMENT:
            oparg = byte_from_code(code, i) + byte_from_code(code, i+1)*256
            i = i+2
            label = -1
            if op in hasjrel:
                label = i+oparg
            elif op in hasjabs:
                label = oparg
            if label >= 0:
                if label not in labels:
                    labels.append(label)
    return labels

def findlinestarts(code):
    """Find the offsets in a byte code which are start of lines in the source.

    Generate pairs (offset, lineno) as described in Python/compile.c.

    """
    byte_increments = [byte_from_code(code.co_lnotab, i) for i in range(0, len(code.co_lnotab), 2)]
    line_increments = [byte_from_code(code.co_lnotab, i) for i in range(1, len(code.co_lnotab), 2)]

    lastlineno = None
    lineno = code.co_firstlineno
    addr = 0
    for byte_incr, line_incr in zip(byte_increments, line_increments):
        if byte_incr:
            if lineno != lastlineno:
                yield (addr, lineno)
                lastlineno = lineno
            addr += byte_incr
        lineno += line_incr
    if lineno != lastlineno:
        yield (addr, lineno)

def _test():
    """Simple test program to disassemble a file."""
    if sys.argv[1:]:
        if sys.argv[2:]:
            sys.stderr.write("usage: python dis.py [-|file]\n")
            sys.exit(2)
        fn = sys.argv[1]
        if not fn or fn == "-":
            fn = None
    else:
        fn = None
    if fn is None:
        f = sys.stdin
    else:
        f = open(fn)
    source = f.read()
    if fn is not None:
        f.close()
    else:
        fn = "<stdin>"
    print 'Disassembling top-level module in', fn
    get_bytecode_map(source, verbose=True)

if __name__ == "__main__":
    _test()
