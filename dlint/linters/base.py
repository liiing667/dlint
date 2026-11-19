#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import collections

from .. import namespace

Flake8Result = collections.namedtuple(
    'Flake8Result',
    ['lineno', 'col_offset', 'message']
)

# Explicit marker for nodes that do not carry source position information,
# e.g. AST nodes synthesized outside of a parsed source file. Flake8 requires
# 1-based line numbers, so 0 is an unambiguous "unknown" sentinel.
UNKNOWN_LINENO = 0
UNKNOWN_COL_OFFSET = 0


def node_position(node):
    """Return the ``(lineno, col_offset)`` pair where ``node`` begins in
    source. Nodes without location information receive an explicit unknown
    marker instead of silently raising ``AttributeError``.
    """
    lineno = getattr(node, 'lineno', None)
    col_offset = getattr(node, 'col_offset', None)

    if lineno is None or col_offset is None:
        return UNKNOWN_LINENO, UNKNOWN_COL_OFFSET

    return lineno, col_offset


def result_from_node(node, message):
    """Build a ``Flake8Result`` whose position points directly at the sink
    ``node`` rather than a parent or decorator node."""
    lineno, col_offset = node_position(node)

    return Flake8Result(
        lineno=lineno,
        col_offset=col_offset,
        message=message
    )


class BaseLinter(ast.NodeVisitor):
    def __init__(self, *args, **kwargs):
        self.results = []
        self.namespace = None

        super(BaseLinter, self).__init__(*args, **kwargs)

    def get_results(self):

        return self.results

    def append_node_result(self, node, message=None):
        """Append a result positioned at the sink ``node``. Results for the
        exact same node are merged once, keeping report order stable as nodes
        are encountered in the tree."""
        result = result_from_node(
            node,
            message if message is not None else self._error_tmpl
        )

        if result not in self.results:
            self.results.append(result)

        return result

    def extend_node_results(self, nodes):
        """Append results for each sink ``node``, merging duplicate nodes
        stably in first-seen order."""
        for node in nodes:
            self.append_node_result(node)

        return self.results

    def visit(self, node):
        if not self.namespace:
            # In MultiNodeVisitor runs this will have already been set since
            # the namespace remains the same for each linter. However, during
            # testing or single-linter runs we still need to initialize the
            # namespace for the linter.
            self.namespace = namespace.Namespace.from_module_node(node)

        super(BaseLinter, self).visit(node)
