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

# Explicit markers for AST nodes that cannot be mapped back to a source
# location. These are intentionally negative so they stand out from valid
# one-based line numbers and zero-based column offsets instead of silently
# emitting a misleading position.
UNKNOWN_LINENO = -1
UNKNOWN_COL_OFFSET = -1


def node_lineno(node):
    """Return the source line for an AST node, or an explicit marker when
    the node has no associated location.
    """
    lineno = getattr(node, 'lineno', None)

    if lineno is None:
        return UNKNOWN_LINENO

    return lineno


def node_col_offset(node):
    """Return the source column for an AST node, or an explicit marker when
    the node has no associated location.
    """
    col_offset = getattr(node, 'col_offset', None)

    if col_offset is None:
        return UNKNOWN_COL_OFFSET

    return col_offset


def node_result(node, message):
    """Build a report whose AST node, source line/column, and fingerprint are
    derived from the same node so they can never disagree.
    """
    return Flake8Result(
        lineno=node_lineno(node),
        col_offset=node_col_offset(node),
        message=message
    )


class BaseLinter(ast.NodeVisitor):
    def __init__(self, *args, **kwargs):
        self.results = collections.OrderedDict()
        self.namespace = None

        super(BaseLinter, self).__init__(*args, **kwargs)

    def get_results(self):

        return list(self.results.values())

    def append_node_result(self, node, message):
        """Record a finding for a concrete AST node. The node is the single
        source of truth for the reported line/column, and the resulting
        Flake8Result doubles as the report fingerprint. Repeated reports for
        the same node and message are merged deterministically.
        """
        result = node_result(node, message)
        self.results.setdefault(result, result)

        return result

    def append_result(self, result):
        """Record a pre-built finding, merging repeated fingerprints
        deterministically while preserving first-seen ordering.
        """
        self.results.setdefault(result, result)

        return result

    def extend_node_results(self, nodes, message):
        for node in nodes:
            self.append_node_result(node, message)

    def extend_results(self, results):
        for result in results:
            self.append_result(result)

    def visit(self, node):
        if not self.namespace:
            # In MultiNodeVisitor runs this will have already been set since
            # the namespace remains the same for each linter. However, during
            # testing or single-linter runs we still need to initialize the
            # namespace for the linter.
            self.namespace = namespace.Namespace.from_module_node(node)

        super(BaseLinter, self).visit(node)
