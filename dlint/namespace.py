#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import copy
import collections

try:
    from functools import lru_cache
except ImportError:
    # Sorry Python 2 users, it's time to upgrade
    def lru_cache(*args, **kwargs):
        def decorator(function):
            def noop(*inner_args, **inner_kwargs):
                return function(*inner_args, **inner_kwargs)
            return noop
        return decorator

from . import util


SCOPE_TYPES = (ast.Module, ast.FunctionDef, ast.ClassDef)

if hasattr(ast, 'AsyncFunctionDef'):
    SCOPE_TYPES += (ast.AsyncFunctionDef,)


Binding = collections.namedtuple('Binding', [
    'bound_name',
    'canonical',
    'head_length',
    'scope',
    'lineno',
    'col_offset',
    'is_star',
    'is_relative',
])


Resolution = collections.namedtuple('Resolution', [
    'canonical',
    'head_length',
    'is_star',
    'reason',
])


class Namespace(object):
    def __init__(self, imports, from_imports):
        self.imports = imports
        self.from_imports = from_imports

        self._module_node = None
        self._module_scope = object()
        self._scope_parents = {}
        self._parent = {}
        self._node_ids = {}
        self._next_node_id = 0
        self._bindings_by_scope = collections.defaultdict(list)
        self._scope_chain_cache = {}
        self._resolution_cache = {}

        self._index_flat_bindings(imports, from_imports)

    @classmethod
    def from_module_node(cls, module_node):
        if not isinstance(module_node, ast.Module):
            raise TypeError('expected type ast.Module, received {}'.format(type(module_node)))

        imports = []
        from_imports = []
        bindings = []
        parent = {}
        scope_parents = {id(module_node): None}
        module_scope = id(module_node)

        def walk(node, scope):
            for child_node in ast.iter_child_nodes(node):
                parent[id(child_node)] = id(node)

                child_scope = scope
                if isinstance(child_node, SCOPE_TYPES):
                    child_scope = id(child_node)
                    scope_parents[child_scope] = scope

                if isinstance(child_node, ast.Import):
                    imports.append(copy.copy(child_node))

                    for alias in child_node.names:
                        bound_name = alias.asname or alias.name.split('.')[0]
                        bindings.append(Binding(
                            bound_name=bound_name,
                            canonical=tuple(alias.name.split('.')),
                            head_length=1,
                            scope=child_scope,
                            lineno=child_node.lineno,
                            col_offset=child_node.col_offset,
                            is_star=False,
                            is_relative=False,
                        ))
                elif isinstance(child_node, ast.ImportFrom):
                    from_imports.append(copy.copy(child_node))

                    is_relative = child_node.level > 0
                    module_parts = (
                        tuple(child_node.module.split('.'))
                        if child_node.module
                        else ()
                    )

                    for alias in child_node.names:
                        if alias.name == '*':
                            bindings.append(Binding(
                                bound_name=None,
                                canonical=None if is_relative else module_parts,
                                head_length=0,
                                scope=child_scope,
                                lineno=child_node.lineno,
                                col_offset=child_node.col_offset,
                                is_star=True,
                                is_relative=is_relative,
                            ))
                        else:
                            bound_name = alias.asname or alias.name
                            bindings.append(Binding(
                                bound_name=bound_name,
                                canonical=(
                                    None
                                    if is_relative
                                    else module_parts + (alias.name,)
                                ),
                                head_length=1,
                                scope=child_scope,
                                lineno=child_node.lineno,
                                col_offset=child_node.col_offset,
                                is_star=False,
                                is_relative=is_relative,
                            ))

                walk(child_node, child_scope)

        walk(module_node, module_scope)

        namespace = cls.__new__(cls)
        namespace.imports = imports
        namespace.from_imports = from_imports
        namespace._module_scope = module_scope
        namespace._module_node = module_node
        namespace._scope_parents = scope_parents
        namespace._parent = parent
        namespace._node_ids = {}
        namespace._next_node_id = 0
        namespace._bindings_by_scope = collections.defaultdict(list)
        namespace._scope_chain_cache = {}
        namespace._resolution_cache = {}

        for binding in bindings:
            namespace._bindings_by_scope[binding.scope].append(binding)

        return namespace

    def _node_key(self, node):
        # AST node ids can be reused after garbage collection, so hand out a
        # stable per-namespace identifier instead of using 'id' as a cache key.
        node_key = self._node_ids.get(id(node))

        if node_key is None:
            node_key = self._next_node_id
            self._next_node_id += 1
            self._node_ids[id(node)] = node_key

        return node_key

    def _index_flat_bindings(self, imports, from_imports):
        # Bindings derived from the flat import node lists handed to the
        # constructor. This keeps the legacy constructor-based entry point
        # working; module parsing goes through 'from_module_node' instead.
        module_scope = id(self._module_scope)
        self._scope_parents = {module_scope: None}

        for imp in imports:
            for alias in imp.names:
                self._bindings_by_scope[module_scope].append(Binding(
                    bound_name=alias.asname or alias.name.split('.')[0],
                    canonical=tuple(alias.name.split('.')),
                    head_length=1,
                    scope=module_scope,
                    lineno=imp.lineno,
                    col_offset=imp.col_offset,
                    is_star=False,
                    is_relative=False,
                ))

        for imp in from_imports:
            is_relative = imp.level > 0
            module_parts = tuple(imp.module.split('.')) if imp.module else ()

            for alias in imp.names:
                if alias.name == '*':
                    self._bindings_by_scope[module_scope].append(Binding(
                        bound_name=None,
                        canonical=None if is_relative else module_parts,
                        head_length=0,
                        scope=module_scope,
                        lineno=imp.lineno,
                        col_offset=imp.col_offset,
                        is_star=True,
                        is_relative=is_relative,
                    ))
                else:
                    self._bindings_by_scope[module_scope].append(Binding(
                        bound_name=alias.asname or alias.name,
                        canonical=(
                            None if is_relative
                            else module_parts + (alias.name,)
                        ),
                        head_length=1,
                        scope=module_scope,
                        lineno=imp.lineno,
                        col_offset=imp.col_offset,
                        is_star=False,
                        is_relative=is_relative,
                    ))

    def _scope_chain(self, node):
        # Return the scope chain enclosing 'node', innermost scope first and
        # the module scope last.
        cache_key = self._node_key(node)
        cached = self._scope_chain_cache.get(cache_key)

        if cached is not None:
            return cached

        chain = []
        current = id(node)

        while current in self._parent:
            current = self._parent[current]

            if current in self._scope_parents:
                chain.append(current)

        if not chain or chain[-1] != self._module_scope:
            chain.append(self._module_scope)

        self._scope_chain_cache[cache_key] = chain

        return chain

    @staticmethod
    def _reason_unresolved(name):
        return "no visible import binding for '{}', treating it as a non-import".format(name)

    @staticmethod
    def _reason_ambiguous(name, bindings):
        paths = ', '.join(
            '.'.join(binding.canonical)
            for binding in bindings
            if binding.canonical is not None
        )

        return "conflicting import bindings for '{}' ({})".format(name, paths)

    @staticmethod
    def _reason_relative(name):
        return "relative import binding for '{}' cannot be resolved statically".format(name)

    def resolve(self, node, name):
        # Resolve the canonical module path behind 'name' as visible from the
        # scope enclosing 'node'. Exact bindings take precedence over wildcard
        # imports, and innermost scopes take precedence over outer scopes.
        cache_key = (self._node_key(node), name)
        cached = self._resolution_cache.get(cache_key)

        if cached is not None:
            return cached

        resolution = self._resolve(node, name)
        self._resolution_cache[cache_key] = resolution

        return resolution

    def _resolve(self, node, name):
        chain = self._scope_chain(node)

        for scope in chain:
            matches = [
                binding for binding in self._bindings_by_scope[scope]
                if binding.bound_name == name
            ]

            if not matches:
                continue

            if any(binding.is_relative for binding in matches):
                return Resolution(None, 0, False, self._reason_relative(name))

            # Multiple 'import pkg.submodule' statements share the same head
            # name ('pkg') without aliasing it, so distinct canonical suffixes
            # are not a conflict. A real conflict rebinds the head name to a
            # different root, e.g. 'import foo as bar' vs 'import baz as bar'.
            plain = [
                binding for binding in matches
                if binding.head_length == 1 and binding.canonical[0] == name
            ]
            rebound = [binding for binding in matches if binding not in plain]

            if plain and not rebound:
                head_lengths = {binding.head_length for binding in plain}

                return Resolution(
                    (name,),
                    head_lengths.pop(),
                    False,
                    None,
                )

            roots = {
                binding.canonical[0]
                for binding in rebound
            }

            if len(roots) > 1 or (plain and rebound):
                return Resolution(
                    None,
                    rebound[0].head_length if rebound else 1,
                    False,
                    self._reason_ambiguous(name, matches),
                )

            head_lengths = {binding.head_length for binding in rebound}

            return Resolution(
                rebound[0].canonical,
                head_lengths.pop(),
                False,
                None,
            )

        for scope in chain:
            stars = [
                binding for binding in self._bindings_by_scope[scope]
                if binding.is_star
            ]

            if not stars:
                continue

            if any(binding.is_relative for binding in stars):
                return Resolution(None, 0, True, self._reason_relative(name))

            canonicals = {binding.canonical for binding in stars}
            head_lengths = {binding.head_length for binding in stars}

            if len(canonicals) > 1:
                return Resolution(None, head_lengths.pop(), True,
                                  self._reason_ambiguous(name, stars))

            return Resolution(canonicals.pop(), head_lengths.pop(), True, None)

        return Resolution(None, 0, False, self._reason_unresolved(name))

    def illegal_module_imported_with_reason(self, module_path, illegal_module_path, node):
        # Same canonical module resolution as 'illegal_module_imported', but
        # also returning why an uncertain finding was retained.
        modules = module_path.split('.')
        illegal_modules = illegal_module_path.split('.')
        illegal_modules_tuple = tuple(illegal_modules)

        resolution = self.resolve(node, modules[0])

        if resolution.reason is not None and resolution.canonical is None:
            if resolution.reason.startswith('no visible import binding'):
                # Unknown names may be local variables or builtins; do not
                # manufacture a finding for something that was never imported.
                return False, None

            # Relative or conflicting bindings cannot be ruled out safely, so
            # retain the finding and explain the uncertainty.
            return True, resolution.reason

        if resolution.is_star:
            # 'from foo.bar import *', 'baz.qux' -> 'foo.bar.baz.qux'. Only
            # report a match when the suffix actually sits under the wildcard's
            # source module, mirroring the legacy wildcard semantics.
            suffix = illegal_modules_tuple[len(resolution.canonical):]
            imported = tuple(suffix) == tuple(modules)
            canonicalized_modules = resolution.canonical + tuple(modules)

            return imported and canonicalized_modules == illegal_modules_tuple, None

        if resolution.head_length == 1 and resolution.canonical[0] == modules[0]:
            # Plain 'import foo.bar' leaves the head name untouched.
            canonicalized_modules = tuple(modules)
        else:
            canonicalized_modules = (
                resolution.canonical
                + tuple(modules[1:])
            )

        return canonicalized_modules == illegal_modules_tuple, None

    @lru_cache(maxsize=1024)
    def name_imported(self, name):
        def alias_includes_name(alias):
            return (
                (alias.name == name and alias.asname is None)
                or (alias.asname == name)
            )

        return any(
            alias_includes_name(alias)
            for imp in self.imports + self.from_imports
            for alias in imp.names
        )

    def name_imported_in_scope(self, node, name):
        # A binding shadows the builtin of the same name when it is visible
        # from the scope enclosing 'node'. Relative imports still bind the
        # name locally, so they count as well.
        chain = self._scope_chain(node)

        return any(
            binding.bound_name == name and not binding.is_star
            for scope in chain
            for binding in self._bindings_by_scope[scope]
        )

    def asname_to_name(self, asname):
        # Backwards-compatible alias lookup. Scope-aware callers should use
        # 'resolve_canonical' instead.
        for binding in self._all_bindings():
            if binding.bound_name == asname and binding.canonical is not None:
                return ".".join(binding.canonical)

        return None

    def _all_bindings(self):
        for bindings in self._bindings_by_scope.values():
            for binding in bindings:
                yield binding

    @lru_cache(maxsize=1024)
    def illegal_module_imported(self, module_path, illegal_module_path):
        # Backwards-compatible, module-scope-only resolution. Scope-aware
        # callers should use 'illegal_module_imported_in_scope'.
        if self._module_node is None:
            return self._illegal_module_imported_legacy(
                module_path,
                illegal_module_path
            )

        return self.illegal_module_imported_in_scope(
            self._module_node,
            module_path,
            illegal_module_path
        )

    def illegal_module_imported_in_scope(self, node, module_path, illegal_module_path):
        is_illegal, _reason = self.illegal_module_imported_with_reason(
            module_path,
            illegal_module_path,
            node
        )

        return is_illegal

    def resolve_module_path(self, node, module_path):
        # Canonicalize a full attribute-based module path (e.g. 'foo.bar.baz')
        # using the binding visible for its head name from the scope enclosing
        # 'node'. Returns (canonical_path_tuple, reason); the reason is set
        # when the head binding is relative or conflicting and the path cannot
        # be resolved statically.
        modules = module_path.split('.')
        resolution = self.resolve(node, modules[0])

        if resolution.canonical is None:
            return None, resolution.reason

        if resolution.is_star:
            # 'from foo import *', 'bar.baz' -> 'foo.bar.baz'
            return resolution.canonical + tuple(modules), resolution.reason

        if resolution.head_length == 1 and resolution.canonical[0] == modules[0]:
            # Plain 'import foo.bar' binds the head name 'foo' without
            # renaming it, so the attribute path is already canonical.
            return tuple(modules), resolution.reason

        # 'import foo.bar as baz' or 'from foo import bar': the head name is
        # rebound, so replace only the head of the access path.
        return (
            resolution.canonical
            + tuple(modules[1:])
        ), resolution.reason

    def resolve_canonical(self, node, name):
        # Return the fully-qualified canonical module path bound to 'name' as
        # visible from the scope enclosing 'node', plus the resolution reason
        # when the binding is uncertain. Returns (None, reason) if it cannot be
        # resolved.
        resolution = self.resolve(node, name)

        if resolution.canonical is None:
            return None, resolution.reason

        if resolution.is_star:
            # Wildcard imports do not bind a specific name; let the caller
            # append the name it is checking against.
            return resolution.canonical + (name,), resolution.reason

        return resolution.canonical, resolution.reason

    def _illegal_module_imported_legacy(self, module_path, illegal_module_path):
        modules = module_path.split('.')
        illegal_modules = illegal_module_path.split('.')

        module_imported = False
        canonicalized_modules = modules

        for imp in self.imports:
            for alias in imp.names:
                if util.lstartswith(illegal_modules, alias.name.split('.')):
                    module_imported = True
                if modules[0] == alias.asname:
                    # 'import foo.bar as baz', 'baz.qux' -> 'foo.bar.baz'
                    canonicalized_modules = alias.name.split('.') + modules[1:]

        for imp in self.from_imports:
            if not imp.module:
                continue  # Relative import, e.g. 'from .'

            imp_modules = imp.module.split('.')

            for alias in imp.names:
                if util.lstartswith(illegal_modules, imp_modules + [alias.name]):
                    module_imported = True
                if modules[0] in [alias.name, alias.asname]:
                    # 'from foo.bar import baz as qux', 'qux.quine' -> 'foo.bar.baz.quine'
                    canonicalized_modules = imp_modules + [alias.name] + modules[1:]
                if (util.lstartswith(illegal_modules, imp_modules)
                        and illegal_modules[len(imp_modules):] == modules
                        and alias.name == '*'):
                    # 'from foo.bar import *', 'baz.qux' -> 'foo.bar.baz.qux'
                    module_imported = True
                    canonicalized_modules = imp_modules + modules

        return module_imported and (canonicalized_modules == illegal_modules)
