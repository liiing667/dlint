#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import abc

from .. import base
from ... import dataflow
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
        return [
            base.Flake8Result(
                lineno=bad_node.lineno,
                col_offset=bad_node.col_offset,
                message=self._error_tmpl
            )
            for bad_node, origin in self.bad_nodes
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
            origin = self.resolver.resolve(node)
            self.bad_nodes.append((node, origin))
            self.evidence.append([dataflow.format_evidence(origin)])

    def visit_Attribute(self, node):
        self.generic_visit(node)

        origin = self.resolver.resolve(node)

        # Wildcard imports cannot be resolved to a canonical path; fall back
        # to the textual module path so existing wildcard behavior is kept.
        if origin.state == dataflow.STATE_KNOWN and origin.module_path is not None:
            if self._origin_is_instance_value(origin):
                # The base value was constructed (e.g. 'up = pickle.Unpickler(f)'
                # followed by 'up.load()'); the old textual linter could not
                # track it, so stay silent to avoid a new false report.
                return
            resolved_module_path = origin.module_path
        elif origin.state == dataflow.STATE_UNKNOWN or self._is_wildcard_base(node):
            # Mirror the original textual check, which compares the base
            # value path (node.value), not including node.attr.
            resolved_module_path = tree.module_path_str(node.value)
        else:
            return

        illegal_attribute_use = any(
            node.attr in attributes
            and self._module_path_matches(
                resolved_module_path, illegal_module_path, node
            )
            for illegal_module_path, attributes in self.illegal_module_attributes.items()
        )

        if illegal_attribute_use:
            if origin.state == dataflow.STATE_KNOWN:
                self.evidence.append([dataflow.format_evidence(origin)])
            else:
                self.evidence.append([
                    '{} -> {} (unresolved)'.format(
                        resolved_module_path, origin.state
                    )
                ])
            self.bad_nodes.append((node, origin))

    def _is_wildcard_base(self, node):
        top_level = any(
            imp.module
            and any(alias.name == '*' for alias in imp.names)
            for imp in self.namespace.from_imports
        )

        if top_level:
            return True

        local_imports = self.resolver.local_imports_for(node)

        if local_imports is None:
            return False

        return any(
            imp.module
            and any(alias.name == '*' for alias in imp.names)
            for imp in local_imports[1]
        )

    @staticmethod
    def _origin_is_instance_value(origin):
        return any(record.kind == 'call' for record in origin.evidence)

    def _module_path_matches(self, resolved_module_path, illegal_module_path, node):
        # The rule key names the owning module (e.g. 'os') while the resolved
        # path includes the attribute (e.g. 'os.system'); compare both forms.
        if self.module_imported(
                resolved_module_path, illegal_module_path, node):
            return True

        return tree.same_modules(illegal_module_path, resolved_module_path)
