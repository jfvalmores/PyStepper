"""
Justine Francis L. Valmores
April, 2016

Description: Extends code_gen(2013-2015) by Berker Peksag which converts
 an AST into Python source code.
    
This extension is for generation of the source code highlighted-to-evaluate
and highlighted-already-evaluated-top-precedence-expression python code.
"""

import ast
import sys
from collections import deque

from .op_util import get_op_symbol, get_op_precedence, Precedence
from .string_repr import pretty_string
from .source_repr import pretty_source
from .code_gen import SourceGenerator


return_index = -1   # Keeps track of the index of the returned indexes in 
                    # returned_values list.

bool_counter = 0    # Tracks the number of bool operands in BoolOp.

left_bool = ''      # Stores the left operand and pairs with corresponding 
                    # right operand.

bool_found = False  # Tells whether two operands have been evaluated.


def to_source_highlight(node, current_locals, current_globals, indent_with=' ' * 4, 
                        add_line_information=False, pretty_string=pretty_string, 
                        pretty_source=pretty_source):
    """
    Returns the string version of the node with the highlighted expression to be
    evaluated.

    The highlighted portion of the string is enclosed with "<<<<< " and " >>>>>".
    """
    generator = HighlightSourceGenerator(current_locals, current_globals, indent_with, 
                                            add_line_information, pretty_string)
    generator.visit(node)
    generator.result.append('\n')
    return pretty_source(str(s) for s in generator.result)


def to_source_eval(node, current_locals, current_globals, returned_values, 
                    indent_with=' ' * 4, add_line_information=False, 
                    pretty_string=pretty_string, pretty_source=pretty_source):
    """
    Returns the string version of the node with a highlighted portion of expression/s
    already evaluated.

    The hightlighted portion of the string is enclosed with "<<<<< " and " >>>>>".
    """
    generator = EvalSourceGenerator(current_locals, current_globals, returned_values,
                                    indent_with, add_line_information, pretty_string)
    generator.visit(node)
    generator.result.append('\n')
    return pretty_source(str(s) for s in generator.result)


def set_precedence(value, *nodes):
    """Set the precedence (of the parent) into the children.
    """
    if isinstance(value, ast.AST):
        value = get_op_precedence(value)
    for node in nodes:
        if isinstance(node, ast.AST):
            node._pp = value
        elif isinstance(node, list):
            set_precedence(value, *node)
        else:
            assert node is None, node


class Delimit(object):
    """
    A context manager that can add enclosing
    delimiters around the output of a
    SourceGenerator method.  By default, the
    parentheses are added, but the enclosed code
    may set discard=True to get rid of them.
    """
    discard = False

    def __init__(self, tree, *args):
        """ 
        use write instead of using result directly
        for initial data, because it may flush
        preceding data into result.
        """
        delimiters = '()'
        node = None
        op = None
        for arg in args:
            if isinstance(arg, ast.AST):
                if node is None:
                    node = arg
                else:
                    op = arg
            else:
                delimiters = arg
        tree.write(delimiters[0])
        result = self.result = tree.result
        self.index = len(result)
        self.closing = delimiters[1]
        if node is not None:
            self.p = p = get_op_precedence(op or node)
            self.pp = pp = tree.get__pp(node)
            self.discard = p >= pp

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if self.discard:
            self.result[self.index - 1] = ''
        else:
            self.result.append(self.closing)


class HighlightSourceGenerator(SourceGenerator):
    """
    Resposible for highlighting portions to be evaluated in 
    one line of the python source code.
    Extends the class SourceGenerator by code_gen which just basically
    converts ast to python code.
    """    
    def __init__(self, current_locals, current_globals, indent_with, 
                    add_line_information, pretty_string):
        SourceGenerator.__init__(self, indent_with, add_line_information,
                                pretty_string)
        self.current_locals = current_locals
        self.current_globals = current_globals
        global return_index
        return_index = -1
        global left_bool
        left_bool = ''
        global bool_found
        bool_found = False
        global bool_counter
        bool_counter = 0

    def visit_BinOp(self, node):
        global bool_found
        op, left, right = node.op, node.left, node.right
        with self.delimit(node, op) as delimiters:
            ispow = isinstance(op, ast.Pow)
            p = delimiters.p
            set_precedence((Precedence.Pow + 1) if ispow else p, left)
            set_precedence(Precedence.PowRHS if ispow else (p + 1), right)
            if isinstance(left, ast.Num) and isinstance(right, ast.Num):
                self.write('<<<<< ')
                self.write(left.n, get_op_symbol(op, ' %s '), right.n)
                self.write(' >>>>>')
            elif isinstance(left, ast.Str) and isinstance(right, ast.Str):
                self.write('<<<<< ')
                self.write(repr(left.s), get_op_symbol(op, ' %s '), repr(right.s))
                self.write(' >>>>>')
            elif isinstance(left, bytes) and isinstance(right, bytes):
                self.write('<<<<< ')
                self.write(left.s, get_op_symbol(op, ' %s '), right.s)
                self.write(' >>>>>')
            else:
                self.write(left, get_op_symbol(op, ' %s '), right)
        bool_found = True

    def visit_Str(self, node):
        self.write("'"+str(node.s)+"'")

    def visit_Name(self, node):
        global bool_found
        if isinstance(node.ctx, ast.Load) and node.id != 'True' and \
                            node.id != 'False' and node.id != 'None':
            found = False
            if self.current_locals:
                for key, value in self.current_locals.items():
                    if key == node.id and type(value) is list:
                        self.write(node.id)
                        found = True
                    elif key == node.id and type(value) is not list:
                        self.write('<<<<< ')
                        if value == True or value == False:
                            bool_found = True
                        self.write(node.id)
                        self.write(' >>>>>')
                        found = True
                        break
            if not found and self.current_globals:
                for key, value in self.current_globals.items():
                    if key == node.id and type(value) is list:
                        self.write(node.id)
                        found = True
                    elif key == node.id and type(value) is not list:
                        self.write('<<<<< ')
                        if value == True or value == False:
                            bool_found = True
                        self.write(node.id)
                        self.write(' >>>>>')
                        found = True
                        break
            if not found:
                self.write(node.id)
        else:
            self.write(node.id)

    def visit_BoolOp(self, node):
        global bool_counter
        global left_bool
        global bool_found
        with self.delimit(node, node.op) as delimiters:
            op = get_op_symbol(node.op, ' %s ')
            set_precedence(delimiters.p + 1, *node.values)
            left_bool = ''
            for idx, value in enumerate(node.values):
                if (left_bool == '' and isinstance(value, ast.Name) \
                    and not bool_found):
                    if value.id == 'False' or value.id == 'True':
                        left_bool = value.id
                        # Short-circuit magic highlighting!
                        if not bool_counter and left_bool == 'False' and op == ' and ':
                            self.write('<<<<< ')
                            self.write('False')
                            self.write(' >>>>>')
                            bool_found = True 
                            left_bool = ''       
                        elif not bool_counter and left_bool == 'True' and op == ' or ':
                            self.write('<<<<< ')
                            self.write('True')
                            self.write(' >>>>>')
                            bool_found = True
                            left_bool = ''             
                    else:
                        self.write(left_bool + (bool_counter and op or ''), value)
                # As of now, our algorithm only supports Num, Str, and Boolean in BoolOp
                elif left_bool == '' and isinstance(value, ast.Num) and not bool_found:
                    left_bool = str(value.n)
                elif left_bool == '' and isinstance(value, ast.Str) and not bool_found:
                    left_bool = "'"+str(value.s)+"'"
                elif idx and left_bool != '' and not bool_found:
                    if isinstance(value, ast.Name):
                        if value.id == 'False' or value.id == 'True':                    
                            self.write('<<<<< ')
                            self.write(left_bool + op + value.id)
                            self.write(' >>>>>')
                            bool_found = True
                            left_bool = ''
                        else:
                            self.write(left_bool + (bool_counter and op or ''), value)
                    elif isinstance(value, ast.Num):                    
                        self.write('<<<<< ')
                        self.write(left_bool + op + str(value.n))
                        self.write(' >>>>>')
                        bool_found = True
                        left_bool = ''
                    elif isinstance(value, ast.Str):                    
                        self.write('<<<<< ')
                        self.write(left_bool + op + "'"+str(value.s)+"'")
                        self.write(' >>>>>')
                        bool_found = True
                        left_bool = '' 
                    else:
                        self.write(left_bool + (bool_counter and op or ''), value)
                else:                   
                    self.write(left_bool + (idx and op or ''), value)
                bool_counter += 1  

    def visit_Compare(self, node):
        global bool_found
        super(HighlightSourceGenerator, self).visit_Compare(node)
        bool_found = True                    

    def visit_UnaryOp(self, node):
        global bool_found
        with self.delimit(node, node.op) as delimiters:
            set_precedence(delimiters.p, node.operand)
            node.operand._p_op = node.op
            sym = get_op_symbol(node.op)
            if sym == 'not' and isinstance(node.operand, ast.Name):
                if (node.operand.id == 'True' or node.operand.id == 'False'):
                    self.write('<<<<< ')
                    self.write(sym, ' ' if sym.isalpha() else '', node.operand)
                    self.write(' >>>>>')
                    bool_found = True
                else:
                    self.write(sym, ' ' if sym.isalpha() else '', node.operand)
            elif sym == 'not' and (isinstance(node.operand, ast.Num) or \
                isinstance(node.operand, ast.Str)):
                self.write('<<<<< ')
                self.write(sym, ' ' if sym.isalpha() else '', node.operand)
                self.write(' >>>>>')
                bool_found = True
            else:
                self.write(sym, ' ' if sym.isalpha() else '', node.operand)

    def visit_Call(self, node):
        found = False
        global return_index
        if self.current_locals:
            for key, value in self.current_locals.items():
                if key == "__return__" and type(value) is list:
                    super(HighlightSourceGenerator, self).visit_Call(node)
                    found = True
                    break
                elif key == "__return__" and type(value) is not list:
                    self.write('<<<<< ')
                    super(HighlightSourceGenerator, self).visit_Call(node)
                    self.write(' >>>>>')
                    return_index = return_index - 1
                    found = True
                    break
            if not found:
                super(HighlightSourceGenerator, self).visit_Call(node)
        else:
            super(HighlightSourceGenerator, self).visit_Call(node)


class EvalSourceGenerator(SourceGenerator):
    """
    Resposible for evaluating and highlighting the evaluated value of
    the evaluable portion of the python source code.
    Extends the class SourceGenerator by code_gen which just basically
    converts ast to python code.
    """
    def __init__(self, current_locals, current_globals, returned_values, 
                    indent_with, add_line_information, pretty_string):
        SourceGenerator.__init__(self, indent_with, add_line_information,
                                pretty_string)
        self.current_locals = current_locals
        self.current_globals = current_globals
        self.returned_values = returned_values
        global left_bool
        left_bool = ''
        global bool_found
        bool_found = False
        global bool_counter
        bool_counter = 0

    def visit_BinOp(self, node):
        global bool_found
        op, left, right = node.op, node.left, node.right
        with self.delimit(node, op) as delimiters:
            ispow = isinstance(op, ast.Pow)
            p = delimiters.p
            set_precedence((Precedence.Pow + 1) if ispow else p, left)
            set_precedence(Precedence.PowRHS if ispow else (p + 1), right)
            if isinstance(left, ast.Num) and isinstance(right, ast.Num):
                self.write('<<<<< ')
                try:
                    self.write(eval(repr(left.n) + get_op_symbol(op, ' %s ') + 
                    repr(right.n)))
                except Exception as ex:
                    pass
                self.write(' >>>>>')
            elif isinstance(left, ast.Str) and isinstance(right, ast.Str):
                self.write('<<<<< ')
                try:
                    self.write(repr(eval(repr(left.s) + get_op_symbol(op, ' %s ') + 
                    repr(right.s))))
                except Exception as ex:
                    pass
                self.write(' >>>>>')
            elif isinstance(left, bytes) and isinstance(right, bytes):
                self.write('<<<<< ')
                try:
                    self.write(eval(repr(left.s) + get_op_symbol(op, ' %s ') + 
                    repr(right.s)))
                except Exception as ex:
                    pass
                self.write(' >>>>>')
            else:
                self.write(left, get_op_symbol(op, ' %s '), right)
        bool_found = True

    def visit_Str(self, node):
        self.write("'"+str(node.s)+"'")

    def visit_Name(self, node):
        global bool_found
        if isinstance(node.ctx, ast.Load) and node.id != 'True' and \
                            node.id != 'False' and node.id != 'None':
            found = False
            if self.current_locals:
                for key, value in self.current_locals.items():
                    if key == node.id and type(value) is list:
                        self.write(node.id)
                        found = True
                    elif key == node.id and type(value) is not list:
                        self.write('<<<<< ')
                        if value == True or value == False:
                            bool_found = True
                        if type(value) is unicode:                         
                            self.write("'"+str(value)+"'")
                        else:
                            self.write(value)
                        self.write(' >>>>>')
                        found = True
                        break
            if not found and self.current_globals:
                for key, value in self.current_globals.items():
                    if key == node.id and type(value) is list:
                        self.write(node.id)
                        found = True
                    elif key == node.id and type(value) is not list:
                        self.write('<<<<< ')
                        if value == True or value == False:
                            bool_found = True
                        if type(value) is unicode:                         
                            self.write("'"+str(value)+"'")
                        else:
                            self.write(value)
                        self.write(' >>>>>')
                        found = True
                        break
            if not found:
                self.write(node.id)
        else:
            self.write(node.id)

    def visit_BoolOp(self, node):
        global bool_counter
        global left_bool
        global bool_found
        with self.delimit(node, node.op) as delimiters:
            op = get_op_symbol(node.op, ' %s ')
            set_precedence(delimiters.p + 1, *node.values)            
            left_bool = ""
            for idx, value in enumerate(node.values):
                if (left_bool == '' and isinstance(value, ast.Name) \
                    and not bool_found):
                    if value.id == 'False' or value.id == 'True':
                        left_bool = value.id
                        # Short-circuit magic here...
                        if not bool_counter and left_bool == 'False' and op == ' and ':
                            self.write('<<<<< ')
                            self.write('False')
                            self.write(' >>>>>')
                            bool_found = True
                            left_bool = ''                             
                            break
                        elif not bool_counter and left_bool == 'True' and op == ' or ':
                            self.write('<<<<< ')
                            self.write('True')
                            self.write(' >>>>>')   
                            bool_found = True                         
                            left_bool = ''                             
                            break
                    else:
                        self.write(left_bool + (bool_counter and op or ''), value)
                # As of now, our algorithm only supports Num, Str, and Boolean in BoolOp
                elif left_bool == '' and isinstance(value, ast.Num) and not bool_found:
                    left_bool = str(value.n)
                elif left_bool == '' and isinstance(value, ast.Str) and not bool_found:
                    left_bool = "'"+str(value.s)+"'"
                elif idx and left_bool != '' and not bool_found:
                    if isinstance(value, ast.Name):
                        if value.id == 'False' or value.id == 'True':                    
                            self.write('<<<<< ')
                            self.write(repr(eval(left_bool + op + value.id)))
                            self.write(' >>>>>')
                            bool_found = True
                            left_bool = ''
                        else:
                            self.write(left_bool + (bool_counter and op or ''), value)
                    elif isinstance(value, ast.Num):                    
                        self.write('<<<<< ')
                        self.write(repr(eval(left_bool + op + str(value.n))))
                        self.write(' >>>>>')
                        bool_found = True
                        left_bool = ''
                    elif isinstance(value, ast.Str):                    
                        self.write('<<<<< ')
                        self.write(repr(eval(left_bool + op + "'"+str(value.s)+"'")))
                        self.write(' >>>>>')
                        bool_found = True
                        left_bool = '' 
                    else:
                        self.write(left_bool + (bool_counter and op or ''), value)
                else:               
                    self.write(left_bool + (idx and op or ''), value)
                bool_counter += 1

    def visit_Compare(self, node):
        global bool_found
        super(EvalSourceGenerator, self).visit_Compare(node)
        bool_found = True

    def visit_UnaryOp(self, node):
        global bool_found
        with self.delimit(node, node.op) as delimiters:
            set_precedence(delimiters.p, node.operand)
            node.operand._p_op = node.op
            sym = get_op_symbol(node.op)
            if sym == 'not' and isinstance(node.operand, ast.Name):
                if (node.operand.id == 'True' or node.operand.id == 'False'):
                    self.write('<<<<< ')
                    self.write(eval('not ' + node.operand.id))
                    self.write(' >>>>>')
                    bool_found = True
                else:
                    self.write(sym, ' ' if sym.isalpha() else '', node.operand)
            elif sym == 'not' and isinstance(node.operand, ast.Num):
                self.write('<<<<< ')
                self.write(repr(eval('not ' + str(node.operand.n))))
                self.write(' >>>>>')
                bool_found = True
            elif sym == 'not' and isinstance(node.operand, ast.Str):
                self.write('<<<<< ')
                self.write(repr(eval('not ' + "'"+str(node.operand.s)+"'")))
                self.write(' >>>>>')
                bool_found = True
            else:
                self.write(sym, ' ' if sym.isalpha() else '', node.operand)

    def visit_Call(self, node):
        found = False
        global return_index
        global bool_found       
        if self.current_locals:
            for key, value in self.current_locals.items():
                if key == "__return__" and type(value) is list:
                    super(EvalSourceGenerator, self).visit_Call(node)
                    found = True
                    break
                elif key == "__return__" and type(value) is not list:
                    self.write('<<<<< ')
                    if self.returned_values[return_index] == True \
                        or self.returned_values[return_index] == False:
                        bool_found = True
                    self.write(self.returned_values[return_index])
                    return_index = return_index + 1
                    self.write(' >>>>>')
                    found = True
                    break
            if not found:
                super(EvalSourceGenerator, self).visit_Call(node)
        else:
            super(EvalSourceGenerator, self).visit_Call(node)