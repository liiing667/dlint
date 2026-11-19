#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import collections
import re

from .linters.base import BaseLinter


CODE_PREFIX = 'DUO'
CODE_PREFIX_LEN = len(CODE_PREFIX)
CODE_RE = re.compile(r'^' + CODE_PREFIX + r'\d{3}$')


class LinterRegistryError(Exception):
    """Raised when a linter cannot be registered safely."""


class LinterRegistry(object):
    """Registry of concrete linter classes.

    A linter's canonical identity is its flake8 code (``_code``). The
    registry guarantees that:

    - every registered linter has a unique, well-formed ``DUOxxx`` code;
    - every registered linter has a unique class name;
    - the message reported for a finding (``_error_tmpl``) is classified
      under the same code the linter is registered with;
    - duplicate or malformed linters fail fast instead of silently
      shadowing one another.
    """

    def __init__(self):
        self._linters_by_code = collections.OrderedDict()
        self._linters_by_name = {}

    def register(self, linter_class):
        self._validate_linter_class(linter_class)

        code = linter_class._code
        class_name = linter_class.__name__

        existing_code = self._linters_by_code.get(code)
        if existing_code is not None:
            raise LinterRegistryError(
                "duplicate linter code {!r}: {!r} conflicts with {!r}".format(
                    code, class_name, existing_code.__name__
                )
            )

        existing_name = self._linters_by_name.get(class_name)
        if existing_name is not None:
            raise LinterRegistryError(
                "duplicate linter class name {!r}: code {!r} conflicts "
                "with code {!r}".format(
                    class_name, code, existing_name._code
                )
            )

        self._linters_by_code[code] = linter_class
        self._linters_by_name[class_name] = linter_class

        return linter_class

    def register_many(self, linter_classes):
        for linter_class in linter_classes:
            self.register(linter_class)

    def get_linter_classes(self):
        return tuple(self._linters_by_code.values())

    def get_linter_class(self, code):
        return self._linters_by_code[code]

    def get_codes(self):
        return tuple(self._linters_by_code.keys())

    def __len__(self):
        return len(self._linters_by_code)

    def __contains__(self, linter_class):
        if not isinstance(linter_class, type):
            return False
        code = getattr(linter_class, '_code', None)
        return self._linters_by_code.get(code) is linter_class

    def __iter__(self):
        return iter(self._linters_by_code.values())

    @staticmethod
    def _validate_linter_class(linter_class):
        if not isinstance(linter_class, type):
            raise LinterRegistryError(
                "linter must be a class, got {!r}".format(
                    type(linter_class).__name__
                )
            )

        if not issubclass(linter_class, BaseLinter):
            raise LinterRegistryError(
                "linter {!r} must subclass {!r}".format(
                    linter_class.__name__, BaseLinter.__name__
                )
            )

        if getattr(linter_class, '__abstractmethods__', frozenset()):
            raise LinterRegistryError(
                "linter {!r} is abstract and cannot be registered".format(
                    linter_class.__name__
                )
            )

        code = getattr(linter_class, '_code', None)
        if not isinstance(code, str) or not CODE_RE.match(code):
            raise LinterRegistryError(
                "linter {!r} has an invalid code {!r}: expected a string "
                "matching {!r}".format(
                    linter_class.__name__, code, CODE_RE.pattern
                )
            )

        error_tmpl = getattr(linter_class, '_error_tmpl', None)
        if not isinstance(error_tmpl, str) or not error_tmpl:
            raise LinterRegistryError(
                "linter {!r} ({}) must define a non-empty "
                "'_error_tmpl' string".format(
                    linter_class.__name__, code
                )
            )

        if not error_tmpl.startswith(code + ' '):
            raise LinterRegistryError(
                "linter {!r} message classification is inconsistent: code "
                "{} does not prefix message {!r}".format(
                    linter_class.__name__, code, error_tmpl
                )
            )


def build_registry(linter_classes):
    registry = LinterRegistry()
    registry.register_many(linter_classes)
    return registry
