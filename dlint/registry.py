#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import inspect
import re


CODE_PREFIX = 'DUO'
CODE_RE = re.compile(r'^' + CODE_PREFIX + r'\d{3}$')


class RegistryError(ValueError):
    """Raised when a linter class cannot be registered because it violates
    the registry's identity or reporting contract.
    """


class LinterRegistry(object):
    """Registry of concrete linter classes keyed by their rule identity.

    The rule identity is the linter's ``_code`` (e.g. ``DUO104``). Every
    registered class must expose a unique code, a unique class name, and a
    ``_error_tmpl`` whose prefix matches its code. Duplicate or conflicting
    registrations raise ``RegistryError`` rather than silently overwriting an
    existing rule, which would otherwise cause a rule to be missed or masked
    by a subclass.
    """

    def __init__(self):
        self._by_code = {}
        self._by_name = {}

    @staticmethod
    def _validate_linter_class(linter_class):
        if not inspect.isclass(linter_class):
            raise RegistryError(
                "linter must be a class, got {!r}".format(linter_class)
            )

        if inspect.isabstract(linter_class):
            raise RegistryError(
                "cannot register abstract linter {!r}".format(
                    linter_class.__name__
                )
            )

        code = getattr(linter_class, '_code', None)
        if not isinstance(code, str) or not CODE_RE.match(code):
            raise RegistryError(
                "linter {!r} has an invalid _code {!r}; expected a code "
                "matching {!r}".format(
                    linter_class.__name__, code, CODE_RE.pattern
                )
            )

        error_tmpl = getattr(linter_class, '_error_tmpl', None)
        if not isinstance(error_tmpl, str):
            raise RegistryError(
                "linter {!r} has an invalid _error_tmpl {!r}".format(
                    linter_class.__name__, error_tmpl
                )
            )

        expected_tmpl_prefix = code + ' '
        if not error_tmpl.startswith(expected_tmpl_prefix):
            raise RegistryError(
                "linter {!r} _error_tmpl {!r} must start with its code "
                "prefix {!r} so reporting classification matches rule "
                "identity".format(
                    linter_class.__name__,
                    error_tmpl,
                    expected_tmpl_prefix,
                )
            )

    def register(self, linter_class):
        self._validate_linter_class(linter_class)

        code = linter_class._code
        name = linter_class.__name__

        existing_by_code = self._by_code.get(code)
        if existing_by_code is not None and existing_by_code is not linter_class:
            raise RegistryError(
                "duplicate linter code {} registered by {!r}; already "
                "registered by {!r}".format(
                    code, name, existing_by_code.__name__
                )
            )

        existing_by_name = self._by_name.get(name)
        if existing_by_name is not None and existing_by_name is not linter_class:
            raise RegistryError(
                "duplicate linter class name {!r} registered with code {}; "
                "{!r} already uses that name with code {}".format(
                    name, code, existing_by_name.__name__,
                    existing_by_name._code
                )
            )

        self._by_code[code] = linter_class
        self._by_name[name] = linter_class

        return linter_class

    def register_all(self, linter_classes):
        for linter_class in linter_classes:
            self.register(linter_class)

    def get_by_code(self, code):
        return self._by_code[code]

    def get_by_name(self, name):
        return self._by_name[name]

    def all(self):
        return tuple(self._by_code.values())

    def codes(self):
        return tuple(sorted(self._by_code))

    def __contains__(self, linter_class):
        if isinstance(linter_class, str):
            return linter_class in self._by_code
        return self._by_code.get(getattr(linter_class, '_code', None)) is linter_class

    def __len__(self):
        return len(self._by_code)


def build_registry(linter_classes):
    registry = LinterRegistry()
    registry.register_all(linter_classes)
    return registry
