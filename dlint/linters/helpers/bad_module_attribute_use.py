#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import abc

from .. import base
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
        self._evidence = {}

        super(BadModuleAttributeUseLinter, self).__init__(*args, **kwargs)

    def get_results(self):
        return [
            base.Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=self._error_tmpl,
                evidence=self._evidence.get(id(node))
            )
            for node in self.bad_nodes
        ]

    def visit_Name(self, node):
        def illegal_import_with_name_resolution(name, attributes, illegal_module_path):
            if name in attributes:
                resolved_name = name
            else:
                resolved_name = self.namespace.asname_to_name(name)
                if resolved_name not in attributes:
                    return False

            return self.namespace.illegal_module_imported(
                resolved_name,
                illegal_module_path + "." + resolved_name
            )

        illegal_call_use = any(
            illegal_import_with_name_resolution(
                node.id,
                attributes,
                illegal_module_path
            )
            for illegal_module_path, attributes in self.illegal_module_attributes.items()
        )

        if illegal_call_use:
            self.bad_nodes.append(node)

    def visit_Attribute(self, node):
        self.generic_visit(node)

        # Resolve the full attribute expression so aliases and nested
        # attribute access on an aliased value are traced back to the
        # importable path they originate from.
        origin = self.resolver.resolve(node)

        if origin.state != 'known':
            # Dynamic or otherwise unresolvable values keep an explicit
            # unknown state instead of being optimistically matched.
            return

        illegal_attribute_use = any(
            node.attr in attributes
            and self.namespace.illegal_module_imported(
                origin.module_path,
                illegal_module_path
            )
            for illegal_module_path, attributes in self.illegal_module_attributes.items()
        )

        if illegal_attribute_use:
            self.bad_nodes.append(node)
            self._evidence[id(node)] = origin.steps
