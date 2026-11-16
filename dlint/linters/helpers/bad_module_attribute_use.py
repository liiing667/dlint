#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import abc

from .. import base
from ... import tree
from ... import util


class BadModuleAttributeUseLinter(base.BaseLinter, util.ABC):
    """This abstract base class provides an simple interface for creating new
    lint rules that block bad attributes within a module.
    """

    @property
    @abc.abstractmethod
    def illegal_module_attributes(self):
        """Subclasses must implement this property to return a dictionary
        that looks like:

            {
                "module_name": [
                    "attribute_name1",
                    "attribute_name2",
                ]
            }
        """

    def __init__(self, *args, **kwargs):
        self.bad_nodes = []

        super(BadModuleAttributeUseLinter, self).__init__(*args, **kwargs)

    def get_results(self):

        results = [
            base.Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=(
                    '{} ({})'.format(self._error_tmpl, reason)
                    if reason
                    else self._error_tmpl
                ),
                reason=reason,
            )
            for node, reason in self.bad_nodes
        ]

        # A single call can be visited as both a Name and an Attribute; report
        # it once, keeping the most informative (reason-bearing) result.
        deduped = {}

        for result in results:
            key = (result.lineno, result.col_offset)
            existing = deduped.get(key)

            if existing is None or (result.reason and not existing.reason):
                deduped[key] = result

        return list(deduped.values())

    def visit_Name(self, node):
        # E.g. 'bar(var)' where 'bar' was imported, possibly via an alias,
        # from one of the illegal modules. Name and Attribute lookups share the
        # same scope-aware canonical module resolution.
        for illegal_module_path, attributes in self.illegal_module_attributes.items():
            canonical, reason = self.namespace.resolve_canonical(node, node.id)

            if canonical is None:
                if node.id not in attributes:
                    # A wildcard import ('from foo import *') cannot be assumed
                    # to provide an arbitrary bare name; only blacklisted
                    # names are eligible for uncertain resolution.
                    continue

                if self._is_uncertain_reason(reason):
                    # Relative or conflicting bindings cannot be ruled out
                    # safely; retain the finding with an explanation.
                    self.bad_nodes.append((node, reason))
                continue

            canonical_path = ".".join(canonical)
            resolved_name = canonical[-1]

            is_illegal = (
                resolved_name in attributes
                and canonical_path == illegal_module_path + "." + resolved_name
            )

            if is_illegal:
                self.bad_nodes.append((node, reason))

    @staticmethod
    def _is_uncertain_reason(reason):
        return bool(reason) and not reason.startswith('no visible import binding')

    def visit_Attribute(self, node):
        self.generic_visit(node)

        # E.g. 'foo.bar(var)'. Both Name and Attribute lookups go through the
        # same scope-aware canonical module resolution; uncertain bindings are
        # retained with an explanation.
        module_path = tree.module_path_str(node.value)

        for illegal_module_path, attributes in self.illegal_module_attributes.items():
            if node.attr not in attributes:
                continue

            canonical, reason = self.namespace.resolve_module_path(node, module_path)

            if canonical is None:
                # Uncertain bindings are retained, but truly unimported names
                # may be local variables and must not produce a finding.
                is_illegal = self._is_uncertain_reason(reason)
            else:
                is_illegal = (
                    ".".join(canonical) + "." + node.attr
                    == illegal_module_path + "." + node.attr
                )

            if is_illegal:
                self.bad_nodes.append((node, reason))
