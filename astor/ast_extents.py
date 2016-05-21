# Created by Philip Guo on 2013-07-10

# Put this file in Python-2.7.5/Lib/ to make it part of the Py2crazy
# standard library, so that it's easily importable

# This module is designed SPECIFICALLY to work with Py2crazy, which is a
# hacked Python 2.7.5 interpreter. It won't work well with regular Python!

__all__ = ['create_extent_map']
# The public interface is a function called create_extent_map
# that takes a string of Python source code and creates this map:
#
# Key: (line number, col_offset)
# Value: A dict where:
#          Key: AST type
#          Value: (start_col, extent)
#
# start_col - starting column corresponding to the key
# extent - number of characters to highlight starting at start_col
#
# Note that start_col might not equal col_offset, since a tool might want
# to highlight a larger portion of the expression not rooted at col_offset.
# The classic example is:
#
# x + y
#
# For the BinOp expression, col_offset is 2 (the location of the '+'
# operator), but start_col is 0, and extent is 5, which highlights the
# entirety of 'x + y' while pointing the cursor at the '+' smack dab in
# the middle.
#
# Note that most of the time, there will be only ONE entry in the value
# dict, but sometimes there will be multiple entries corresponding to
# different AST types. e.g.,:


import sys
import ast

# Limitations
# - doesn't support extents that span MULTIPLE LINES
# - BinOps involving ** and field attribute accesses interact funny
#   e.g., "self.val = self.val ** 2"
#
# see tests/known-broken-tests/ for other weirdness


# Consult Parser/Python.asdl for full AST description


# Informally tested by running AddExtentsVisitor on a bunch of files
# from the Python standard library, starting with Lib/ast.py.
# Also test on the Online Python Tutor test suite as well.

# for e in Lib/*.py; do echo $e; ./python.exe ../calculate_ast_extents.py $e; done > out 2> err

# for e in OnlinePythonTutor/v3/tests/backend-tests/*.txt; do echo $e; ./python.exe ../calculate_ast_extents.py $e; done > out 2> err

# for e in OnlinePythonTutor/v3/tests/example-code/*.txt; do echo $e; ./python.exe ../calculate_ast_extents.py $e; done > out 2> err


# NOPs
NOP_CLASSES = [ast.expr_context, ast.cmpop, ast.boolop,
               ast.unaryop, ast.operator,
               ast.Module, ast.Interactive, ast.Expression,
               ast.arguments, ast.keyword, ast.alias,
               ast.excepthandler,
               ast.Set, # TODO: maybe keep extents for this, along with Dict, Tuple, and List
               ast.If, ast.With, ast.GeneratorExp,
               ast.comprehension,
               ast.BoolOp,
               ast.ListComp, ast.DictComp, ast.SetComp,
               ast.IfExp,
               ast.Ellipsis, # a rarely-occuring bad egg; it doesn't have col_offset, ugh
               ast.Expr, # ALWAYS ignore this or else you get into bad conflicts
               ast.Print]


# This visitor runs top-down, so we might need to run several times to fixpoint
class AddExtentsVisitor(ast.NodeVisitor):
  def __init__(self):
    ast.NodeVisitor.__init__(self)

  def add_attrs(self, node):
    if 'extent' not in node._attributes:
      node._attributes = node._attributes + ('start_col', 'extent',)

  # this should NEVER be called, since all cases should be exhaustively handled
  def generic_visit(self, node):
    # exception: let these pass through unscathed, since we NOP on them
    for c in NOP_CLASSES:
      if isinstance(node, c):
        # recurse normally into children (if any)
        self.visit_children(node)
        return

    assert False, node.__class__


  # copied from Lib/ast.py generic_visit
  def visit_children(self, node):
      for field, value in ast.iter_fields(node):
          if isinstance(value, list):
              for item in value:
                  if isinstance(item, ast.AST):
                      self.visit(item)
          elif isinstance(value, ast.AST):
              self.visit(value)

  # always end with a call to self.visit_children(node) to recurse
  # (unless you know you're a terminal node)
  # TODO: encapsulate in a decorator

  def visit_Subscript(self, node):
    if hasattr(node.value, 'extent') and hasattr(node.slice, 'extent'):
      self.add_attrs(node)
      node.start_col = node.value.start_col
      # add 1 for trailing ']'
      # of course, that doesn't work so well when you put spaces before
      # like '  ]', but it's okay for the common case.
      node.extent = node.slice.start_col + node.slice.extent + 1 - node.start_col
    self.visit_children(node)

  def visit_Index(self, node):
    if hasattr(node.value, 'extent'):
      self.add_attrs(node)
      node.start_col = node.value.start_col
      node.extent = node.value.extent
    self.visit_children(node)

  def visit_Slice(self, node):
    leftmost = node.lower
    right_padding = 0
    if node.step:
      rightmost = node.step  # A[i:j:k]
    elif node.upper:
      rightmost = node.upper # A[i:j]
    else:
      rightmost = node.lower # A[i:]
      right_padding = 1 # for trailing ':'

    if hasattr(leftmost, 'extent') and hasattr(rightmost, 'extent'):
      # TODO: to be really paranoid, check that they're on the same line
      self.add_attrs(node)
      node.start_col = leftmost.start_col
      node.extent = rightmost.start_col + rightmost.extent + right_padding - node.start_col

      # trickllllly! also add lineno and col_offset to Slice object,
      # since the AST doesn't keep this info for this class, sad :(
      node._attributes += ('lineno', 'col_offset')
      node.lineno = leftmost.lineno
      node.col_offset = leftmost.col_offset

    self.visit_children(node)

  def visit_ExtSlice(self, node):
    # TODO: handle me in a similar way as visit_Slice if necessary
    self.visit_children(node)

  def visit_Attribute(self, node):
      if hasattr(node.value, 'extent'):
          self.add_attrs(node)
          node.start_col = node.value.start_col
          # tricky tricky. the key point here is that node.col_offset
          # is the column of the '.' dot operator
          node.extent = (node.col_offset + len(node.attr) + 1) - node.start_col
      self.visit_children(node)

  def visit_Call(self, node):
    # find the RIGHTMOST argument and use that one for extent
    # (could be either in args, keywords, starargs, or kwargs)
    max_col_offset = -1
    max_elt = None

    # the 'value' field in each element of node.keywords is most relevant
    candidates = node.args + [e.value for e in node.keywords]
    if node.starargs:
      candidates.append(node.starargs)
    if node.kwargs:
      candidates.append(node.kwargs)

    for e in candidates:
      if e.col_offset > max_col_offset and e.lineno == node.lineno:
        max_col_offset = e.col_offset
        max_elt = e

    if max_elt and hasattr(max_elt, 'extent') and hasattr(node.func, 'extent'):
      self.add_attrs(node)
      node.start_col = node.func.start_col
      node.extent = max_elt.start_col + max_elt.extent + 1 - node.start_col
    elif hasattr(node.func, 'extent'):
      # punt and just use the function's info
      self.add_attrs(node)
      node.start_col = node.func.start_col
      node.extent = node.func.extent + 2 # 2 extra for '()'

    self.visit_children(node)

  def visit_Compare(self, node):
    '''
	     -- need sequences for compare to distinguish between
	     -- x < 4 < 3 and (x < 4) < 3
	     | Compare(expr left, cmpop* ops, expr* comparators)
    '''
    leftmost = node.left
    assert len(node.comparators) > 0
    rightmost = node.comparators[-1]
    if hasattr(leftmost, 'extent') and hasattr(rightmost, 'extent'):
      # DO NOT support spanning across multiple lines, or else extents are
      # messed-up and meaningless
      if hasattr(leftmost, 'lineno') and hasattr(rightmost, 'lineno') and \
         (leftmost.lineno == rightmost.lineno):
        self.add_attrs(node)
        node.start_col = leftmost.start_col
        node.extent = rightmost.start_col + rightmost.extent - leftmost.start_col
    self.visit_children(node)

  def visit_BinOp(self, node):
    if hasattr(node.left, 'extent') and hasattr(node.right, 'extent'):
      # DO NOT support spanning across multiple lines, or else extents are
      # messed-up and meaningless
      if hasattr(node.left, 'lineno') and hasattr(node.right, 'lineno') and \
         (node.left.lineno == node.right.lineno):
        self.add_attrs(node)
        node.start_col = node.left.start_col
        node.extent = (node.right.start_col + node.right.extent - node.start_col)
    self.visit_children(node)

  def visit_UnaryOp(self, node):
    if hasattr(node.operand, 'extent'):
      self.add_attrs(node)
      node.start_col = node.col_offset
      node.extent = (node.operand.start_col + node.operand.extent - node.start_col)
    self.visit_children(node)

  # NOP for now since it looks prettier that way ...
  def visit_Assign(self, node):
    self.visit_children(node)
    '''
    if hasattr(node.targets[0], 'extent') and hasattr(node.value, 'extent'):
      self.add_attrs(node)
      node.start_col = node.targets[0].start_col
      node.extent = (node.value.start_col + node.value.extent - node.start_col)
    self.visit_children(node)
    '''

  # NOP for now since it looks prettier that way ...
  def visit_AugAssign(self, node):
    self.visit_children(node)
    '''
    if hasattr(node.target, 'extent') and hasattr(node.value, 'extent'):
      self.add_attrs(node)
      node.start_col = node.target.start_col
      node.extent = (node.value.start_col + node.value.extent - node.start_col)
    self.visit_children(node)
    '''

  def visit_Repr(self, node):
    if hasattr(node.value, 'extent'):
      self.add_attrs(node)
      node.start_col = node.col_offset
      node.extent = node.value.extent + 2 # add 2 for surrounding backquotes
    self.visit_children(node)

  def visit_Tuple(self, node):
    # empty case
    if len(node.elts) == 0:
      node.start_col = node.col_offset
      node.extent = 2 # for '()' case; obviously doesn't handle blank spaces
    else:
      last_elt = node.elts[-1]

      # add 1 to get the offset of the trailing ')'
      trailing_offset = 1
      # a singleton tuple is like '(x,)', so add 1 more for the trailing comma
      if len(node.elts) == 1:
        trailing_offset += 1
      if hasattr(last_elt, 'extent') and \
         hasattr(last_elt, 'lineno') and \
         (node.lineno == last_elt.lineno):
        self.add_attrs(node)
        # tuples start at the first element since "naked tuples" are
        # possible. so in the common case, subtract 1 to get the
        # col_offset of the starting '('
        node.start_col = node.col_offset - 1
        node.extent = last_elt.start_col + last_elt.extent + trailing_offset - node.start_col
    self.visit_children(node)

  def visit_List(self, node):
    # empty case
    if len(node.elts) == 0:
      node.start_col = node.col_offset
      node.extent = 2 # for '[]' case; obviously doesn't handle blank spaces
    else:
      last_elt = node.elts[-1]
      if hasattr(last_elt, 'extent') and \
         hasattr(last_elt, 'lineno') and \
         (node.lineno == last_elt.lineno):
        self.add_attrs(node)
        node.start_col = node.col_offset
        # node.col_offset starts at the '[', so add 1 to the right to end at ']'
        node.extent = last_elt.start_col + last_elt.extent + 1 - node.start_col
    self.visit_children(node)

  def visit_Dict(self, node):
    # empty case
    if len(node.values) == 0:
      node.start_col = node.col_offset
      node.extent = 2 # for '{}' case
    else:
      last_val = node.values[-1] # this is the best approximation I can come up with
      if hasattr(last_val, 'extent') and \
         hasattr(last_val, 'lineno') and \
         (node.lineno == last_val.lineno):
        self.add_attrs(node)
        node.start_col = node.col_offset
        node.extent = last_val.start_col + last_val.extent + 1 - node.start_col
    self.visit_children(node)


  # TODO: abstract out this recurring pattern ...
  def visit_FunctionDef(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('def')
    self.visit_children(node)

  def visit_ClassDef(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('class')
    self.visit_children(node)

  def visit_Raise(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('raise')
    self.visit_children(node)

  def visit_Assert(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('assert')
    self.visit_children(node)

  def visit_TryExcept(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('try')
    self.visit_children(node)

  def visit_TryFinally(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('try')
    self.visit_children(node)

  def visit_ExceptHandler(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('except')
    self.visit_children(node)

  def visit_Global(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('global')
    self.visit_children(node)

  def visit_Lambda(self, node):
    if hasattr(node.body, 'extent'):
      self.add_attrs(node)
      node.start_col = node.col_offset
      node.extent = node.body.start_col + node.body.extent - node.start_col
    self.visit_children(node)

  def visit_Exec(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('exec')
    self.visit_children(node)

  def visit_For(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('for')
    self.visit_children(node)

  def visit_While(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('while')
    self.visit_children(node)

  def visit_Pass(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('pass')
    self.visit_children(node)

  def visit_Break(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('break')
    self.visit_children(node)

  def visit_Continue(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('continue')
    self.visit_children(node)

  def visit_Delete(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('del')
    self.visit_children(node)

  def visit_Return(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('return')
    self.visit_children(node)

  def visit_Import(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('import')
    self.visit_children(node)

  def visit_ImportFrom(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('from')
    self.visit_children(node)

  def visit_Yield(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len('yield')
    self.visit_children(node)


  # terminal nodes
  def visit_Str(self, node):
    # TODO: doesn't work for multi-line strings, or triple-quoted
    # strings, etc.
    # (some weird strings have col_offset as -1, so ignore those
    if node.col_offset >= 0:
      self.add_attrs(node)
      node.start_col = node.col_offset
      node.extent = len(node.s) + 2 # add 2 for quotes

  def visit_Name(self, node):
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len(node.id)

  def visit_Num(self, node):
    # TODO: there might be a danger of getting this number wrong for
    # floats, due to imprecision in converting to strings. eek!
    self.add_attrs(node)
    node.start_col = node.col_offset
    node.extent = len(str(node.n))


# copied from ast.NodeVisitor
class DepthCountingVisitor(object):
    def __init__(self):
        self.max_depth = 0
    def visit(self, node, depth=1):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self.visit(item, depth+1)
            elif isinstance(value, ast.AST):
                self.visit(value, depth+1)
        else:
            # terminal node
            if depth > self.max_depth:
                self.max_depth = depth


class BuildExtentMapVisitor(ast.NodeVisitor):
    def __init__(self, extent_map):
        # Key: (line number, col_offset)
        # Value: A dict where:
        #          Key: AST type
        #          Value: (start_col, extent)
        self.extent_map = extent_map

    def generic_visit(self, node):
        if 'extent' in node._attributes and \
            'lineno' in node._attributes and \
            'col_offset' in node._attributes:
            k = (node.lineno, node.col_offset)
            v = (node.start_col, node.extent)
            ast_typename = node.__class__.__name__

            if k not in self.extent_map:
                self.extent_map[k] = {}

            # don't allow duplicates of the same AST type:
            assert ast_typename not in self.extent_map[k]

            self.extent_map[k][ast_typename] = v


        ast.NodeVisitor.generic_visit(self, node)


# throws an AssertionError if something explodes
def create_extent_map(code_str):
    m = ast.parse(code_str)

    dcv = DepthCountingVisitor()
    dcv.visit(m)
    max_depth = dcv.max_depth

    # To be conservative, run the visitor max_depth number of times, which
    # should be enough to percolate ALL (start_col, extent) values up from
    # the leaves to the root of the tree
    v = AddExtentsVisitor()
    for i in range(max_depth):
        v.visit(m)

    extent_map = {}
    bemv = BuildExtentMapVisitor(extent_map)
    bemv.visit(m)

    return extent_map


# adapted from ast.dump
def pretty_dump(node):
    def _format(node, indent=0, newline=False):
        ind = ('    ' * indent)
        next_ind = ('    ' * (indent+1))

        if isinstance(node, ast.AST):
            if newline:
                print ind + node.__class__.__name__,
            else:
                print node.__class__.__name__,

            if hasattr(node, 'lineno'):
                print '(L=%s, C=%s)' % (node.lineno, node.col_offset)
            else:
                print

            for (fieldname, f) in ast.iter_fields(node):
                print next_ind + fieldname + ':',
                _format(f, indent+1)

        elif isinstance(node, list):
            print '['
            for e in node:
                _format(e, indent+1, True)
            print ind + ']'
        else:
            print repr(node)

    if not isinstance(node, ast.AST):
        raise TypeError('expected AST, got %r' % node.__class__.__name__)

    return _format(node, 0)


if __name__ == "__main__":
    src_cod = open(sys.argv[1]).read()
    extent_map = create_extent_map(src_cod)

    import pprint
    pp = pprint.PrettyPrinter()

    pretty_dump(ast.parse(src_cod))

    for k,v in extent_map.iteritems():
        print k, v
