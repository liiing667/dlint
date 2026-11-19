#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import collections

from .. import dataflow
from .. import namespace
from .. import parents


class Flake8Result(collections.namedtuple(
    'Flake8Result',
    ['lineno', 'col_offset', 'message', 'evidence']
)):
    """A lint finding plus the optional data-flow evidence that explains it.

    Equality deliberately ignores the evidence chain so existing rule
    fixtures keep asserting on location and message only, while dedicated
    data-flow tests can inspect the full path separately.
    """

    __slots__ = ()

    def __new__(cls, lineno, col_offset, message, evidence=None):
        return super(Flake8Result, cls).__new__(
            cls, lineno, col_offset, message, evidence
        )

    def __eq__(self, other):
        if isinstance(other, Flake8Result):
            return (
                self.lineno == other.lineno
                and self.col_offset == other.col_offset
                and self.message == other.message
            )

        if isinstance(other, tuple):
            return tuple(self[:3]) == other[:3]

        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash((self.lineno, self.col_offset, self.message))


class BaseLinter(ast.NodeVisitor):
    def __init__(self, *args, **kwargs):
        self.results = []
        self.namespace = None
        self.resolver = None

        super(BaseLinter, self).__init__(*args, **kwargs)

    def get_results(self):

        return self.results

    def visit(self, node):
        if not self.namespace:
            # In MultiNodeVisitor runs this will have already been set since
            # the namespace remains the same for each linter. However, during
            # testing or single-linter runs we still need to initialize the
            # namespace for the linter.
            self.namespace = namespace.Namespace.from_module_node(node)

        if self.resolver is None and isinstance(node, ast.Module):
            parents.attach_parents(node)
            self.resolver = dataflow.DataflowResolver(node, self.namespace)

        super(BaseLinter, self).visit(node)

    def append_result(self, node, message=None, evidence=None):
        """Record a finding at ``node`` with an optional data-flow evidence
        chain connecting the node back to its originating value source."""
        self.results.append(
            Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=message or self._error_tmpl,
                evidence=evidence
            )
        )
