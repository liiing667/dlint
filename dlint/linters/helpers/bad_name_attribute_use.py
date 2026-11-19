#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import abc
import ast

from .. import base
from ... import tree
from ... import util


class BadNameAttributeUseLinter(base.BaseLinter, util.ABC):
    """This abstract base class provides an simple interface for creating new
    lint rules that block bad attributes on a variable object.
    """

    @property
    @abc.abstractmethod
    def illegal_name_attributes(self):
        """Subclasses must implement this property to return a dictionary
        that looks like:

            {
                "object_attribute": [
                    "parent_module_name1.child_module_name1",
                    "parent_module_name2.child_module_name2",
                ]
            }
        """

    def visit_Module(self, node):
        self.generic_visit(node)
        self._lint_scope(node)

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        self._lint_scope(node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        self._lint_scope(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def _lint_scope(self, scope_node):
        results = []

        def attribute_use_callback(inner_node):
            if not (isinstance(inner_node, ast.Call)
                    and isinstance(inner_node.func, ast.Attribute)
                    and isinstance(inner_node.func.value, ast.Name)):
                return

            attribute = inner_node.func.attr
            if attribute not in self.illegal_name_attributes:
                return

            # Resolve the object the attribute is called on back to the
            # constructor call (or import) that created it. Aliases,
            # forwarded values, and nested attributes are all followed as
            # one data-flow path with evidence collected at every hop.
            origin = self.resolver.resolve(inner_node.func.value)

            if origin.state != 'known':
                # Explicitly unknown dynamic values are never reported so
                # clean, statically-unresolvable code cannot false positive.
                return

            is_illegal = any(
                self.namespace.illegal_module_imported(
                    origin.module_path,
                    illegal_name
                )
                for illegal_name in self.illegal_name_attributes[attribute]
            )

            if is_illegal:
                results.append((inner_node, origin.steps))

        # Stops at nested scope boundaries, so each binding is evaluated
        # against the scope where the attribute call actually lives.
        tree.walk_callback_same_scope(scope_node, attribute_use_callback)

        self.results.extend(
            base.Flake8Result(
                lineno=result.lineno,
                col_offset=result.col_offset,
                message=self._error_tmpl,
                evidence=steps
            )
            for result, steps in results
        )
