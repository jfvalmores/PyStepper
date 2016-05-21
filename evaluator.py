"""
	Justine Francis L. Valmores
	February, 2016

	Description: Generates steps of highlighting and evaluation per line.
	This code has been embedded in pg_logger.py for the placement of the 
	evaluation steps into JSON.
"""

import astor
import ast

def generate_steps(source):
	"""
		Returns a list of pairs of strings.
		The pair includes a (1) "highlighted-to-be-evaluated" string
		(2) "highlighted-already-evaluated" string.
		The list to be returned is good for one line of python code.
	"""
	print "Operating Expression:"
	print "main source: " + source + "\n"
	result = source
	start = '<|'
	end = '|>'
	final_eval = []
	while True:
		single_eval = []
		try:
			node = ast.parse(result)
		except Exception as ex:
			single_eval.append(result)
			single_eval.append(result)
			final_eval.append(single_eval)
			print "highlight : %s" % (final_eval[0][0])
			print "evaluation: %s" % (final_eval[0][1])
			break
		result = astor.to_source_eval(node).rstrip()
		given = astor.to_source_highlight(node).rstrip()		
		single_eval.append(given)
		single_eval.append(result)
		final_eval.append(single_eval)
		result = result.replace(start, '').replace(end, '').replace(' ', '')
		if result == final_eval[-1][0].replace(' ', ''):
			final_eval[-1][0] = "<| " + final_eval[-1][0] + " |>"
			further_eval = ""		#this part does a last evaluation of the final result
			if "=" in final_eval[-1][1]:
				further_eval = final_eval[-1][1][final_eval[-1][1].index("=") + 2:]
				left_side = final_eval[-1][1][:final_eval[-1][1].index("=") + 2]
				try:
					further_eval = left_side + str(eval(further_eval))
				except Exception as ex:
					print str(type(ex)) + " Message: " + str(ex)
					further_eval = final_eval[-1][1]
			else:
				further_eval = final_eval[-1][1]
				try:
					further_eval = str(eval(further_eval))
				except Exception as ex:
					pass
			if further_eval != "":
				final_eval[-1][1] = further_eval
			final_eval[-1][1] = "<| " + final_eval[-1][1] + " |>"
			for subl in final_eval:
				print "highlight  : %s" % (subl[0])
				print "evaluation : %s" % (subl[1])
				print ''
			print "~end~"
			return final_eval

# tests:
tree = ast.parse('23')
#print astor.dump_tree(tree)
generate_steps('23')
print ''
tree = ast.parse('5 + 5')
#print astor.dump_tree(tree)
generate_steps('5 + 5')
print ''
tree = ast.parse('answer = (-6) + (8 + 5) * 10')
#print astor.dump_tree(tree)
generate_steps('answer = (-6) + (8 + 5) * 10')
print ''
tree = ast.parse('-(2 + 4)')
#print astor.dump_tree(tree)
generate_steps('-(2 + 4)')
print ''
tree = ast.parse('5 * 5 / 2 + 10 - 1 % 6')
#print astor.dump_tree(tree)
generate_steps('5 * 5 / 2 + 10 - 1 % 6')
print ''
tree = ast.parse('((5 * 5) / 2) + ((10 - 1) % 6)')
#print astor.dump_tree(tree)
generate_steps('((5 * 5) / 2) + ((10 - 1) % 6)')
print ''
tree = ast.parse('x = ((9 - 2) + 4) + 2')
#print astor.dump_tree(tree)
generate_steps('x = ((9 - 2) + 4) + 2')
print ''
tree = ast.parse('answer = 115 + 5')
print astor.dump_tree(tree)
generate_steps('answer = 115 + 5')
print ''
tree = ast.parse('print 4')
print astor.dump_tree(tree)
generate_steps('print 4')
print ''
tree = ast.parse('(True and False) or False')
print astor.dump_tree(tree)
generate_steps('True and False')
print ''
tree = ast.parse('not False')
print astor.dump_tree(tree)
generate_steps('not False')
print ''
tree = ast.parse('\"justinefrancis\"[1:12]')
print astor.dump_tree(tree)
generate_steps('\"justinefrancis\"[1:12]')
"""
class Solver(ast.NodeTransformer):

	evaluated = False

	def visit_BinOp(self, node):
		print 'hello'
		if not self.evaluated:
			if (isinstance(node.left, ast.Num) and isinstance(node.right, ast.Num)):		
				return ast.Num(eval(repr(node.left.n) + astor.get_op_symbol(node.op, ' %s ') + repr(node.right.n)))
				evaluated = True
			elif (isinstance(node.left, ast.Str) and isinstance(node.right, ast.Str)):
				return ast.Str(eval(repr(node.left.s) + astor.get_op_symbol(node.op, ' %s ') + repr(node.right.s)))
				evaluated = True
			elif (isinstance(node.left, bytes) and isinstance(node.right, bytes)):
				return ast.Str(eval(repr(node.left.s) + astor.get_op_symbol(node.op, ' %s ') + repr(node.right.s)))
				evaluated = True
			else:
				self.generic_visit(node)
		else:
			self.generic_visit(node)
		return node

	def visit_Num(self, node):
		return ast.Num(node.n)
# tree = astor.CodeToAst().parse_file('example.py')
tree = ast.parse('((5 * 5) / 2) + ((10 - 1) % 6)')
print astor.dump_tree(tree)
print astor.to_source(tree)
solver = Solver().visit(tree)
solver = ast.fix_missing_locations(solver)
print astor.dump_tree(solver)
print astor.to_source(solver)

print astor.dump_tree(tree)
solver = Solver().visit(tree)
solver = ast.fix_missing_locations(solver)
print astor.dump_tree(solver)
print astor.to_source(solver)

print astor.dump_tree(tree)
solver = Solver().visit(tree)
solver = ast.fix_missing_locations(solver)
print astor.dump_tree(solver)
print astor.to_source(solver)

print astor.dump_tree(tree)
solver = Solver().visit(tree)
solver = ast.fix_missing_locations(solver)
print astor.dump_tree(solver)
print astor.to_source(solver)
"""