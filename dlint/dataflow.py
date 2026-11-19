#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import collections

from . import tree


# An Origin describes where a value comes from.
#
#   state         - one of the STATE_* constants below
#   module_path   - dotted module/attribute path when the origin is known,
#                   e.g. "subprocess.Popen"; None otherwise
#   node          - the AST node that physically holds the value
#   source        - the AST node the value was ultimately resolved from
#                   (e.g. the right-hand side of an assignment)
#   evidence      - chain of Evidence records linking the value back to
#                   its original source through the AST parent chain
Origin = collections.namedtuple(
    'Origin',
    ['state', 'module_path', 'node', 'source', 'evidence']
)

# Evidence is a single hop in a data-flow path, e.g. an assignment or a
# keyword-argument binding that moves a value closer to a sink.
Evidence = collections.namedtuple(
    'Evidence',
    ['kind', 'node', 'detail']
)

STATE_KNOWN = 'known'
STATE_UNKNOWN = 'unknown'
STATE_DYNAMIC = 'dynamic'


def _is_str_node(node):
    if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
        return isinstance(node.value, str)

    return hasattr(ast, 'Str') and isinstance(node, ast.Str)


def _str_value(node):
    return node.s if hasattr(node, 's') else node.value

_SCOPE_NODES = (ast.Module, ast.FunctionDef, ast.ClassDef)
if hasattr(ast, 'AsyncFunctionDef'):
    _SCOPE_NODES = _SCOPE_NODES + (ast.AsyncFunctionDef,)


def annotate_parents(module_node):
    """Walk the whole tree once and attach a ``dlint_parent`` pointer to
    every node so that any node can walk back up the AST parent chain.
    """
    for parent in ast.walk(module_node):
        for child in ast.iter_child_nodes(parent):
            child.dlint_parent = parent

    return module_node


def get_parent(node):
    """Return the annotated AST parent of a node, or None for the root."""
    return getattr(node, 'dlint_parent', None)


def enclosing_scope(node):
    """Walk the parent chain up to the nearest module, function or class
    scope. Assignments outside of this scope do not bind the node's name.
    """
    parent = get_parent(node)

    while parent is not None and not isinstance(parent, _SCOPE_NODES):
        parent = get_parent(parent)

    return parent


def same_scope(assignment_node, reference_node):
    return enclosing_scope(assignment_node) is enclosing_scope(reference_node)


class _VirtualKeyword(object):
    """Keyword-argument view of a value that reached a call through an
    assignment (e.g. ``kwargs = {"shell": True}; func(**kwargs)``) rather
    than being written inline.
    """

    def __init__(self, arg, value):
        self.arg = arg
        self.value = value


class ResolvedCall(object):
    """Data-flow aware view of a Call node. Keyword arguments are presented
    as a single flat list regardless of whether they were written inline,
    unpacked from a dictionary, or assigned to a variable first, which keeps
    the value origin, the AST parent chain and the rule evidence on one path.
    """

    def __init__(self, call, resolver):
        self.call = call
        self.resolver = resolver
        self.keywords = self._resolve_keywords()

    def _resolve_keywords(self):
        keywords = []

        for keyword in self.call.keywords:
            if keyword.arg is not None:
                # Inline keyword argument, e.g. foo(shell=True)
                keywords.append(keyword)
                continue

            # Dictionary unpacking, e.g. foo(**kwargs) or foo(**{"shell": True})
            origin = self.resolver.resolve(keyword.value)
            dict_node = origin.source

            if not isinstance(dict_node, ast.Dict):
                # The unpacked object is dynamic; retain an explicit state
                # instead of silently dropping the argument.
                keywords.append(_VirtualKeyword(None, origin.node))
                continue

            for key, value in zip(dict_node.keys, dict_node.values):
                if _is_str_node(key):
                    keywords.append(_VirtualKeyword(_str_value(key), value))
                else:
                    keywords.append(_VirtualKeyword(None, value))

        return keywords


class Resolver(object):
    """Resolves AST expression nodes to the Origin of their value by
    following assignments, aliases, imports and nested attribute access
    through the annotated AST parent chain.
    """

    def __init__(self, module_node, namespace):
        annotate_parents(module_node)
        self.module_node = module_node
        self.namespace = namespace
        self._local_imports = self._collect_local_imports(module_node)

    @staticmethod
    def _collect_local_imports(module_node):
        """Map scope node id -> (imports, from_imports) for non-module
        scopes so function/class-local imports can be resolved while the
        shared Namespace keeps its top-level-only semantics.
        """
        local_imports = {}

        for scope in ast.walk(module_node):
            if not isinstance(scope, _SCOPE_NODES) or isinstance(scope, ast.Module):
                continue

            imports = []
            from_imports = []

            for child in ast.walk(scope):
                if child is scope:
                    continue

                if isinstance(child, ast.Import):
                    imports.append(child)
                elif isinstance(child, ast.ImportFrom):
                    from_imports.append(child)

            if imports or from_imports:
                local_imports[id(scope)] = (imports, from_imports)

        return local_imports

    def resolve(self, node, evidence=None):
        if evidence is None:
            evidence = []

        return self._resolve(node, evidence, set())

    def _resolve(self, node, evidence, visited):
        node_id = id(node)

        if node_id in visited:
            # Self-referential alias, e.g. 'a = a.b'; the value is dynamic.
            return self._origin(
                STATE_DYNAMIC, None, node, node,
                evidence + [Evidence('cycle', node, type(node).__name__)]
            )

        visited = visited | {node_id}

        if isinstance(node, ast.Name):
            return self._resolve_name(node, evidence, visited)
        elif isinstance(node, ast.Attribute):
            return self._resolve_attribute(node, evidence, visited)
        elif isinstance(node, ast.Call):
            return self._resolve_call(node, evidence, visited)
        elif self._is_constant(node):
            return self._origin(STATE_KNOWN, None, node, node, evidence)
        else:
            # Subscripts, comprehensions, lambdas, binary operations and
            # other dynamic expressions cannot be statically resolved.
            return self._origin(
                STATE_DYNAMIC, None, node, node,
                evidence + [Evidence('dynamic', node, type(node).__name__)]
            )

    def resolve_call(self, call):
        return ResolvedCall(call, self)

    def local_imports_for(self, node):
        """Return a (imports, from_imports) tuple covering every non-module
        scope enclosing the node, or None when there are no local imports.
        """
        imports = []
        from_imports = []
        scope = enclosing_scope(node)

        while scope is not None and not isinstance(scope, ast.Module):
            local = self._local_imports.get(id(scope))

            if local is not None:
                imports.extend(local[0])
                from_imports.extend(local[1])

            scope = enclosing_scope(scope)

        if not imports and not from_imports:
            return None

        return imports, from_imports

    def _origin(self, state, module_path, node, source, evidence):
        return Origin(
            state=state,
            module_path=module_path,
            node=node,
            source=source,
            evidence=tuple(evidence)
        )

    @staticmethod
    def _is_constant(node):
        if hasattr(ast, 'Num') and isinstance(node, ast.Num):
            return True

        if hasattr(ast, 'Str') and isinstance(node, ast.Str):
            return True

        if hasattr(ast, 'NameConstant') and isinstance(node, ast.NameConstant):
            return True

        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            return True

        return False

    def _resolve_name(self, node, evidence, visited):
        imported_path = self._imported_name_path(node)

        if imported_path is not None:
            return self._origin(
                STATE_KNOWN, imported_path, node, node,
                evidence + [Evidence('import', node, imported_path)]
            )

        if self._name_covered_by_wildcard(node):
            # A wildcard import might bind this name, but to what cannot be
            # determined statically; retain an explicit unknown state.
            return self._origin(
                STATE_UNKNOWN, None, node, node,
                evidence + [Evidence('wildcard-import', node, node.id)]
            )

        assignment = self._nearest_assignment(node)

        if assignment is None:
            # No binding is visible: the value depends on runtime state.
            return self._origin(
                STATE_DYNAMIC, None, node, node,
                evidence + [Evidence('unbound', node, node.id)]
            )

        hop = Evidence(
            'assignment',
            assignment,
            '{} <- {}'.format(
                node.id,
                tree.module_path_str(assignment.value) or type(assignment.value).__name__
            )
        )

        return self._resolve(assignment.value, evidence + [hop], visited)

    def _resolve_attribute(self, node, evidence, visited):
        value_origin = self._resolve(
            node.value,
            evidence + [Evidence('attribute', node, node.attr)],
            visited
        )

        if value_origin.state != STATE_KNOWN or value_origin.module_path is None:
            # The base object is dynamic (e.g. a function parameter or the
            # result of an unknown call) so the attribute cannot be resolved.
            return self._origin(
                value_origin.state, None, node, value_origin.source,
                value_origin.evidence
            )

        module_path = value_origin.module_path + '.' + node.attr

        return self._origin(
            STATE_KNOWN, module_path, node, value_origin.source,
            value_origin.evidence
        )

    def _resolve_call(self, node, evidence, visited):
        if not isinstance(node.func, (ast.Attribute, ast.Name)):
            return self._origin(
                STATE_DYNAMIC, None, node, node,
                evidence + [Evidence('dynamic', node, 'indirect-call')]
            )

        func_origin = self._resolve(
            node.func,
            evidence + [
                Evidence('call', node, tree.module_path_str(node.func))
            ],
            visited
        )

        if func_origin.state != STATE_KNOWN or func_origin.module_path is None:
            # Unknown dynamic call, e.g. get_function()(...): keep an
            # explicit dynamic state rather than guessing the callee.
            return self._origin(
                STATE_DYNAMIC, None, node, node, func_origin.evidence
            )

        return self._origin(
            STATE_KNOWN, func_origin.module_path, node, node,
            func_origin.evidence
        )

    def _imported_name_path(self, node):
        # Module-level (and visible enclosing-scope) imports first.
        path = self._name_path_from_import_lists(
            node, self.namespace.imports, self.namespace.from_imports
        )

        if path is not None:
            return path

        # Function/class-local imports are only visible within that scope.
        scope = enclosing_scope(node)

        while scope is not None and not isinstance(scope, ast.Module):
            local = self._local_imports.get(id(scope))

            if local is not None:
                path = self._name_path_from_import_lists(node, local[0], local[1])

                if path is not None:
                    return path

            scope = enclosing_scope(scope)

        return None

    @staticmethod
    def _name_path_from_import_lists(node, imports, from_imports):
        """Return the canonical module path an imported name is bound to,
        honoring both ``import x as y`` and ``from x import y as z`` aliases.
        """
        name = node.id

        for imp in imports:
            for alias in imp.names:
                bound_name = alias.asname if alias.asname else alias.name.split('.')[0]
                if bound_name == name:
                    if alias.asname:
                        # 'import foo.bar as baz' -> canonical 'foo.bar'
                        return alias.name
                    return name

        for imp in from_imports:
            if not imp.module:
                continue

            for alias in imp.names:
                bound_name = alias.asname if alias.asname else alias.name
                if bound_name == name:
                    if alias.name == '*':
                        # Wildcard imports cannot be resolved to one path.
                        return None
                    return imp.module + '.' + alias.name

        return None

    def _name_covered_by_wildcard(self, node):
        """Whether a wildcard from-import could bind the given name. The
        exact target module is unknown, so callers treat this as STATE_UNKNOWN.
        """
        import_lists = [
            (self.namespace.imports, self.namespace.from_imports)
        ]

        scope = enclosing_scope(node)

        while scope is not None and not isinstance(scope, ast.Module):
            local = self._local_imports.get(id(scope))

            if local is not None:
                import_lists.append(local)

            scope = enclosing_scope(scope)

        return any(
            imp.module
            and any(alias.name == '*' for alias in imp.names)
            for imports, from_imports in import_lists
            for imp in from_imports
        )

    def _nearest_assignment(self, node):
        """Find the closest assignment of the node's name before the node,
        within the same scope, by walking the AST parent chain and its
        preceding siblings.
        """
        if getattr(node, 'ctx', None) is not None and not isinstance(
                node.ctx, ast.Load):
            # Store/Del context nodes are binding sites, not references.
            return None

        name = node.id

        def assignment_matches(assign_node):
            if not isinstance(assign_node, ast.Assign):
                return None

            for target in assign_node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return assign_node

            return None

        # First look for an assignment above the reference inside the scope.
        scope = enclosing_scope(node)

        if scope is not None:
            candidate = self._latest_assignment_in_scope(scope, node, assignment_matches)
            if candidate is not None:
                return candidate

        # Fall back to walking the parent chain (module-level references and
        # references nested inside non-scope statement blocks).
        cursor = get_parent(node)
        child = node

        while cursor is not None:
            for statement in self._statement_body(cursor):
                if statement is child:
                    break

                match = assignment_matches(statement)
                if match is not None and same_scope(match, node):
                    return match

            child = cursor
            cursor = get_parent(cursor)

        return None

    def _latest_assignment_in_scope(self, scope, reference_node, matcher):
        reference_lineno = reference_node.lineno
        reference_col = reference_node.col_offset
        latest = None

        for inner in ast.walk(scope):
            if not isinstance(inner, ast.Assign):
                continue

            match = matcher(inner)

            if match is None or not same_scope(match, reference_node):
                continue

            if (match.lineno, match.col_offset) < (reference_lineno, reference_col):
                if latest is None or (match.lineno, match.col_offset) > (
                        latest.lineno, latest.col_offset):
                    latest = match

        return latest

    @staticmethod
    def _statement_body(node):
        for attr in ('body', 'orelse', 'finalbody'):
            statements = getattr(node, attr, None)
            if isinstance(statements, list):
                for statement in statements:
                    if isinstance(statement, ast.stmt):
                        yield statement


def format_evidence(origin):
    """Render an Origin's evidence chain as a human-readable data-flow path.
    Used by the fixed syntax fixtures to show hit locations and data flow.
    """
    if not origin.evidence:
        return origin.module_path or origin.state

    hops = []

    for record in origin.evidence:
        location = '{}:{}'.format(
            getattr(record.node, 'lineno', '?'),
            getattr(record.node, 'col_offset', '?')
        )
        hops.append('{}[{}]({})'.format(record.kind, location, record.detail))

    endpoint = origin.module_path or origin.state
    return ' -> '.join(hops + [endpoint])
