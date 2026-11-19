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
from .. import severity

Flake8Result = collections.namedtuple(
    'Flake8Result',
    ['lineno', 'col_offset', 'message']
)

# A finding's identity is everything that distinguishes one reported issue
# from another: where it was found, which rule found it and how severe it is.
Finding = collections.namedtuple(
    'Finding',
    ['lineno', 'col_offset', 'message', 'code', 'severity']
)


class BaseLinter(ast.NodeVisitor):
    # Subclasses override these with the rule code, message template and
    # severity. The severity must resolve to a valid ``severity.Severity``
    # member; an unknown or missing severity fails closed at construction
    # time rather than being silently treated as harmless.
    _code = None
    _error_tmpl = None
    _severity = 'MEDIUM'

    def __init__(self, *args, **kwargs):
        self.results = []
        self.namespace = None
        self.severity = self._validate_severity()

        super(BaseLinter, self).__init__(*args, **kwargs)

    @classmethod
    def _validate_severity(cls):
        try:
            return severity.Severity.parse(cls._severity)
        except severity.InvalidSeverity:
            raise severity.InvalidSeverity(
                "linter {!r} defines an unknown severity level: {!r}".format(
                    cls.__name__, cls._severity
                )
            )

    @classmethod
    def _get_severity(cls):
        """Return the rule's severity, failing closed on unknown levels."""
        return cls._validate_severity()

    @property
    def code(self):
        return self._code

    def new_result(self, lineno, col_offset, message=None):
        """Build a result and its severity-aware finding identity together.

        The :class:`Flake8Result` keeps its historical shape so existing
        outputs are unchanged, while the paired :class:`Finding` carries the
        rule code and severity needed for sorting and filtering.
        """
        if message is None:
            message = self._error_tmpl

        return (
            Flake8Result(
                lineno=lineno,
                col_offset=col_offset,
                message=message
            ),
            Finding(
                lineno=lineno,
                col_offset=col_offset,
                message=message,
                code=self._code,
                severity=self.severity
            )
        )

    def get_findings(self):
        """Return the finding identity for every reported result.

        Results produced before this method existed only carry line, column
        and message; the rule's code and severity are attached here so a
        finding always has a complete, unambiguous identity.
        """
        return [
            Finding(
                lineno=result.lineno,
                col_offset=result.col_offset,
                message=result.message,
                code=self._code,
                severity=self.severity
            )
            for result in self.get_results()
        ]

    def get_results(self):

        return self.results

    def visit(self, node):
        if not self.namespace:
            # In MultiNodeVisitor runs this will have already been set since
            # the namespace remains the same for each linter. However, during
            # testing or single-linter runs we still need to initialize the
            # namespace for the linter.
            self.namespace = namespace.Namespace.from_module_node(node)

        super(BaseLinter, self).visit(node)
