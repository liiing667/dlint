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
from ... import dataflow
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

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        self._check_calls(node)

    def visit_Module(self, node):
        self.generic_visit(node)
        self._check_calls(node)

    def _check_calls(self, scope_node):
        for inner_node in ast.walk(scope_node):
            if not (isinstance(inner_node, ast.Call)
                    and isinstance(inner_node.func, ast.Attribute)
                    and isinstance(inner_node.func.value, ast.Name)):
                continue

            # Only inspect calls that belong to this scope so nested
            # function/class rebindings cannot leak outward.
            if dataflow.enclosing_scope(inner_node) is not scope_node:
                continue

            if getattr(inner_node, '_dlint_name_attribute_checked', False):
                continue

            inner_node._dlint_name_attribute_checked = True

            attribute = inner_node.func.attr

            if attribute not in self.illegal_name_attributes:
                continue

            origin = self.resolver.resolve(inner_node.func.value)

            if origin.state != dataflow.STATE_KNOWN or origin.module_path is None:
                # Dynamic/unknown value source: keep the explicit state and
                # do not raise on clean code.
                continue

            is_illegal = any(
                self.module_imported(
                    origin.module_path,
                    illegal_name,
                    inner_node
                )
                for illegal_name in self.illegal_name_attributes[attribute]
            )

            if is_illegal:
                self.append_result(
                    inner_node,
                    self._error_tmpl,
                    origin=origin
                )

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)
