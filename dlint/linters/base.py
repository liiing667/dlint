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

Flake8Result = collections.namedtuple(
    'Flake8Result',
    ['lineno', 'col_offset', 'message']
)


class BaseLinter(ast.NodeVisitor):
    def __init__(self, *args, **kwargs):
        self.results = []
        self.namespace = None
        self.resolver = None
        self.evidence = []

        super(BaseLinter, self).__init__(*args, **kwargs)

    def get_results(self):

        return self.results

    def get_evidence(self):
        """Return data-flow evidence aligned by index with ``get_results``.
        Each entry is a list of human-readable evidence strings; an empty
        list means the finding was produced without a tracked value path.
        """
        return self.evidence

    def append_result(self, node, message, origin=None):
        self.results.append(
            Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=message
            )
        )

        if origin is None:
            self.evidence.append([])
        else:
            self.evidence.append([dataflow.format_evidence(origin)])

    def module_imported(self, module_path, illegal_module_path, reference_node=None):
        """Namespace check that also honors function/class-local imports
        visible from the reference node's scope.
        """
        local_imports = None

        if reference_node is not None and self.resolver is not None:
            local_imports = self.resolver.local_imports_for(reference_node)

        return self.namespace.illegal_module_imported_with_local(
            module_path,
            illegal_module_path,
            local_imports
        )

    def visit(self, node):
        if not self.namespace:
            # In MultiNodeVisitor runs this will have already been set since
            # the namespace remains the same for each linter. However, during
            # testing or single-linter runs we still need to initialize the
            # namespace for the linter.
            self.namespace = namespace.Namespace.from_module_node(node)
            self.resolver = dataflow.Resolver(node, self.namespace)

        super(BaseLinter, self).visit(node)
