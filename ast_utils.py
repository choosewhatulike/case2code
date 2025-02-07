from typing import List, Dict
import ast
import astor
import subprocess

def source_to_ast(code: str) -> ast.AST:
    try:
        return ast.parse(code)
    except Exception as e:
        if not isinstance(e, SyntaxError):
            print(f'{type(e).__name__}: {e}')
        return None

def get_functions(tree: ast.AST) -> List[ast.FunctionDef]:
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]

def ast_to_source(node: ast.AST) -> str:
    try:
        return astor.to_source(node)
    except Exception as e:
        print(f'{type(e).__name__}: {e}')
        return ''

def has_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return True
    return False

def get_imports(root: ast.AST):
    for node in ast.iter_child_nodes(root):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    code = f'import {alias.name} as {alias.asname}'
                else:
                    code = f'import {alias.name}'
                yield code, alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    code = f'from {node.module} import {alias.name} as {alias.asname}'
                else:
                    code = f'from {node.module} import {alias.name}'
                yield code, node.module
        else:
            continue

class FunctionAst:
    def __init__(self, node: ast.FunctionDef):
        self.node = node
        assert isinstance(node, ast.FunctionDef)
        
    @property
    def name(self):
        return self.node.name
    
    @property
    def args(self):
        return [arg.arg for arg in self.node.args.args]
    
    def is_nested_function(self):
        for node in ast.iter_child_nodes(self.node):
            if isinstance(node, ast.FunctionDef):
                return True
        return False
    
    def has_return(self):
        for node in ast.walk(self.node):
            if isinstance(node, ast.Return):
                return True
        return False
    
    def has_args(self):
        return len(self.args) > 0
    
    def has_import(self):
        for node in ast.walk(self.node):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return True
        return False
    
