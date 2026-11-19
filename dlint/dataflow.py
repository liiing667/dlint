#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import collections

from . import parents


# Sentinel states for a value whose runtime origin cannot be resolved
# statically. We keep the reason explicit so rules never silently treat
# unknown dynamic behavior as safe or as a confirmed dangerous sink.
UNKNOWN = 'unknown'
UNKNOWN_DYNAMIC = 'unknown-dynamic-call'
UNKNOWN_ARGUMENT = 'unknown-argument'
UNKNOWN_REASSIGNED = 'unknown-reassigned'


ValueOrigin = collections.namedtuple(
    'ValueOrigin',
    ['state', 'module_path', 'steps']
)

EvidenceStep = collections.namedtuple(
    'EvidenceStep',
    ['kind', 'description', 'lineno', 'col_offset']
)


def unknown_origin(state=UNKNOWN, steps=None):
    return ValueOrigin(state=state, module_path=None, steps=list(steps or []))


def known_origin(module_path, steps=None):
    return ValueOrigin(
        state='known',
        module_path=module_path,
        steps=list(steps or [])
    )


class AssignmentMap(object):
    """Collects the value expression assigned to every local name.

    Only assignments that happen directly inside a scope (function, class,
    or module) are recorded for that scope. Assignments nested in inner
    scopes belong to the inner scope and therefore do not count.
    """

    def __init__(self):
        # scope node -> {name: (value node, assign node)}
        self._scopes = collections.defaultdict(dict)

    @classmethod
    def build(cls, module_node):
        assignment_map = cls()
        scope_types = (ast.Module, ast.FunctionDef, ast.ClassDef)
        if hasattr(ast, 'AsyncFunctionDef'):
            scope_types += (ast.AsyncFunctionDef,)

        for node in ast.walk(module_node):
            if isinstance(node, scope_types):
                assignment_map._visit_scope(node)
        return assignment_map

    def _visit_scope(self, scope_node):
        for node in ast.walk(scope_node):
            # Only record assignments whose nearest enclosing scope is this
            # one; assignments inside nested functions or classes belong to
            # those scopes and are collected when they are visited.
            if parents.get_enclosing_scope(node) is not scope_node:
                continue

            self._record(node)

    def _record(self, node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self._record_target(target, node.value, node)
        elif isinstance(node, (ast.FunctionDef,)) or (
            hasattr(ast, 'AsyncFunctionDef')
            and isinstance(node, ast.AsyncFunctionDef)
        ):
            # Function names are local bindings that can be aliased and
            # reassigned, so record them the same way variable bindings are.
            self._scopes[self._scope_of(node)][node.name] = (node, node)
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                # x += foo() is effectively a reassignment to an unknown
                # combined value, mark it explicitly as unresolvable.
                self._scopes[self._scope_of(node)][node.target.id] = (None, node)
        elif isinstance(node, (ast.For,)):
            self._record_target(node.target, None, node)
        elif hasattr(ast, 'NamedExpr') and isinstance(node, ast.NamedExpr):
            self._record_target(node.target, node.value, node)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars is not None:
                    self._record_target(item.optional_vars, item.context_expr, node)

    def _scope_of(self, node):
        return parents.get_enclosing_scope(node)

    def _record_target(self, target, value_node, assign_node):
        scope = self._scope_of(target)
        if isinstance(target, ast.Name):
            self._scopes[scope][target.id] = (value_node, assign_node)
        elif isinstance(target, (ast.Tuple, ast.List)):
            # Tuple/list unpacking cannot be mapped name-to-value reliably;
            # mark every unpacked name as an unknown origin.
            for element in target.elts:
                if isinstance(element, ast.Name):
                    self._scopes[scope][element.id] = (None, assign_node)
                elif isinstance(element, ast.Starred) and isinstance(element.value, ast.Name):
                    self._scopes[scope][element.value.id] = (None, assign_node)

    def lookup(self, scope_node, name):
        """Return the (value node, assignment node) recorded for a name."""
        starting_scope = scope_node
        scope = scope_node
        visited = set()
        while scope is not None:
            # Walk the enclosing scopes. A class scope is skipped for nested
            # functions because Python does not leak class namespaces into
            # method bodies, but it is still consulted when the lookup starts
            # inside the class body itself.
            if id(scope) in visited:
                break
            visited.add(id(scope))

            if isinstance(scope, ast.ClassDef) and scope is not starting_scope:
                scope = self._module_scope(scope)
                continue

            if name in self._scopes.get(scope, {}):
                return self._scopes[scope][name]

            scope = parents.get_parent(scope)
        return None

    def _module_scope(self, node):
        for ancestor in parents.iter_parents(node):
            if isinstance(ancestor, ast.Module):
                return ancestor
        return None


class DataflowResolver(object):
    """Resolves an expression back to its originating importable value.

    The resolver follows assignment aliases, keyword argument forwarding,
    and nested attribute access while recording an evidence chain for each
    hop. Anything that cannot be resolved statically returns an explicit
    unknown origin instead of guessing.
    """

    MAX_HOPS = 32

    def __init__(self, module_node, namespace, assignment_map=None):
        self.module_node = module_node
        self.namespace = namespace
        self.assignment_map = assignment_map or AssignmentMap.build(module_node)

    def resolve(self, node):
        return self._resolve(node, scope=parents.get_enclosing_scope(node), seen=set())

    def _resolve(self, node, scope, seen, steps=None):
        steps = list(steps or [])

        if node is None:
            return unknown_origin(UNKNOWN, steps)

        key = (id(node), id(scope))
        if key in seen or len(steps) >= self.MAX_HOPS:
            return unknown_origin(UNKNOWN_REASSIGNED, steps)
        seen = seen | {key}

        if isinstance(node, ast.Name):
            return self._resolve_name(node, scope, seen, steps)

        if isinstance(node, ast.Attribute):
            return self._resolve_attribute(node, scope, seen, steps)

        if isinstance(node, ast.Call):
            return self._resolve_call(node, scope, seen, steps)

        if isinstance(node, ast.Subscript):
            steps.append(self._step('dynamic', node))
            return unknown_origin(UNKNOWN_DYNAMIC, steps)

        if isinstance(node, ast.Lambda):
            steps.append(self._step('dynamic', node))
            return unknown_origin(UNKNOWN_DYNAMIC, steps)

        steps.append(self._step('dynamic', node))
        return unknown_origin(UNKNOWN, steps)

    def _resolve_name(self, node, scope, seen, steps):
        assignment = self.assignment_map.lookup(scope, node.id)

        # A local binding shadows an import of the same name, so check
        # assignments before falling back to import resolution.
        if assignment is not None:
            value_node, assign_node = assignment
            steps.append(self._step('alias', assign_node, node.id))

            if value_node is None:
                return unknown_origin(UNKNOWN_REASSIGNED, steps)

            return self._resolve(value_node, scope, seen, steps)

        if self.namespace and self.namespace.name_imported(node.id):
            module_path = self._canonicalize([node.id])
            steps.append(self._step('import', node, module_path))
            return known_origin(module_path, steps)

        star_module = self._star_import_module(node.id)
        if star_module is not None:
            module_path = star_module + '.' + node.id
            steps.append(self._step('import', node, module_path))
            return known_origin(module_path, steps)

        if assignment is None:
            steps.append(self._step('unknown', node))
            return unknown_origin(UNKNOWN_ARGUMENT, steps)

    def _resolve_attribute(self, node, scope, seen, steps):
        base_origin = self._resolve(node.value, scope, seen, steps)
        if base_origin.state != 'known':
            return unknown_origin(base_origin.state, base_origin.steps)

        module_path = base_origin.module_path + '.' + node.attr
        steps.append(self._step('attribute', node, module_path))
        return known_origin(module_path, steps)

    def _resolve_call(self, node, scope, seen, steps):
        func = node.func

        if not isinstance(func, (ast.Name, ast.Attribute)):
            # E.g. subscript calls, boolean calls, lambda calls
            steps.append(self._step('dynamic', node))
            return unknown_origin(UNKNOWN_DYNAMIC, steps)

        if isinstance(func, ast.Name) and func.id in self._dynamic_builtins():
            steps.append(self._step('dynamic', node))
            return unknown_origin(UNKNOWN_DYNAMIC, steps)

        callee_origin = self._resolve(func, scope, seen, steps)
        if callee_origin.state != 'known':
            return unknown_origin(callee_origin.state, callee_origin.steps)

        # A call to a resolved importable path produces a value whose type
        # originates from that same path, e.g. pickle.Pickler() -> pickle.Pickler
        steps.append(self._step('call', node, callee_origin.module_path))
        return known_origin(callee_origin.module_path, steps)

    def _dynamic_builtins(self):
        return (
            'getattr', 'setattr', 'delattr', 'globals', 'locals',
            'vars', 'eval', 'exec', 'compile', 'input', '__import__',
        )

    def _canonicalize(self, modules):
        canonical = list(modules)

        for imp in self.namespace.imports:
            for alias in imp.names:
                if modules[0] == alias.asname:
                    canonical = alias.name.split('.') + modules[1:]

        for imp in self.namespace.from_imports:
            if not imp.module:
                continue

            imp_modules = imp.module.split('.')
            for alias in imp.names:
                if modules[0] in (alias.name, alias.asname):
                    canonical = imp_modules + [alias.name] + modules[1:]
                if alias.name == '*':
                    canonical = imp_modules + modules

        return '.'.join(canonical)

    def _star_import_module(self, name):
        # A 'from foo.bar import *' makes every name under foo.bar available
        # without an explicit binding. We cannot confirm the name exists, so
        # return the candidate path and let namespace matching decide whether
        # it is the illegal one.
        for imp in self.namespace.from_imports:
            if imp.module and any(alias.name == '*' for alias in imp.names):
                return imp.module
        return None

    def _step(self, kind, node, description=None):
        if description is None:
            description = type(node).__name__
        return EvidenceStep(
            kind=kind,
            description=description,
            lineno=getattr(node, 'lineno', 0),
            col_offset=getattr(node, 'col_offset', 0),
        )
