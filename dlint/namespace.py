#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import copy

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


class Namespace(object):
    def __init__(self, imports, from_imports):
        self.imports = imports
        self.from_imports = from_imports

    @classmethod
    def from_module_node(cls, module_node):
        # For now only add top-level, module imports. Let's avoid the rabbit
        # hole of looking at things like function and class-scope imports and
        # conditional imports in 'if' or 'try' statements
        if not isinstance(module_node, ast.Module):
            raise TypeError('expected type ast.Module, received {}'.format(type(module_node)))

        imports = []
        from_imports = []

        for node in module_node.body:
            if isinstance(node, ast.Import):
                imports.append(copy.copy(node))
            elif isinstance(node, ast.ImportFrom):
                from_imports.append(copy.copy(node))

        return cls(imports, from_imports)

    @lru_cache(maxsize=1024)
    def name_imported(self, name):
        def alias_includes_name(alias):
            return (
                (
                    alias.asname is None
                    and (
                        alias.name == name
                        # 'import foo.bar' binds the top-level name 'foo'
                        or alias.name.split('.')[0] == name
                    )
                )
                or (alias.asname == name)
            )

        return any(
            alias_includes_name(alias)
            for imp in self.imports + self.from_imports
            for alias in imp.names
        )

    def asname_to_name(self, asname):
        for imp in self.imports + self.from_imports:
            for alias in imp.names:
                if alias.asname == asname:
                    return alias.name

        return None

    @lru_cache(maxsize=1024)
    def illegal_module_imported(self, module_path, illegal_module_path):
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
                if alias.name == '*' and util.lstartswith(
                    illegal_modules, imp_modules
                ):
                    # 'from foo.bar import *' can reach the caller in two
                    # shapes: a relative path ('baz.qux', the legacy calling
                    # convention) or the fully resolved path
                    # ('foo.bar.baz.qux') produced by the data-flow resolver.
                    relative_modules = illegal_modules[len(imp_modules):]
                    resolved_modules = imp_modules + relative_modules

                    if relative_modules == modules:
                        # Legacy relative path: canonicalize to the full path.
                        module_imported = True
                        canonicalized_modules = resolved_modules
                    elif (
                        util.lstartswith(modules, imp_modules)
                        and self._matches_illegal_path(
                            modules,
                            illegal_modules
                        )
                    ):
                        # Already fully resolved, possibly with extra nested
                        # attributes accessed on the illegal origin.
                        module_imported = True
                        canonicalized_modules = modules

        return module_imported and self._matches_illegal_path(
            canonicalized_modules,
            illegal_modules
        )

    @staticmethod
    def _matches_illegal_path(modules, illegal_modules):
        # A resolved value that originates from an illegal importable path
        # remains illegal when further attributes are accessed on it, e.g.
        # blacklisting 'foo.bar' must also cover 'foo.bar.baz.qux'.
        return (
            modules == illegal_modules
            or (
                len(modules) > len(illegal_modules)
                and util.lstartswith(modules, illegal_modules)
            )
        )
