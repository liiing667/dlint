#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import collections
import functools
import sys

if sys.version_info >= (3, 0):
    string_types = (str,)
else:
    string_types = (str, unicode)  # noqa: F821


class InvalidSeverity(ValueError):
    """Raised when an unknown severity level is encountered.

    Severity handling fails closed: an unrecognized level can never be
    silently downgraded, so a caller that filters on severity cannot hide
    a real (possibly high-risk) finding.
    """


_SeverityLevel = collections.namedtuple(
    '_SeverityLevel',
    ['name', 'rank']
)


@functools.total_ordering
class Severity(object):
    """An ordered severity level shared by rules, findings and reports.

    Every severity is one of the fixed members defined on this class. The
    ordering reflects risk, from the lowest (:data:`Severity.INFO`) to the
    highest (:data:`Severity.HIGH`). Unknown values are never accepted:
    construction and parsing raise :class:`InvalidSeverity` so that an
    unrecognized level fails closed instead of being treated as harmless.
    """

    INFO = _SeverityLevel('INFO', 0)
    LOW = _SeverityLevel('LOW', 1)
    MEDIUM = _SeverityLevel('MEDIUM', 2)
    HIGH = _SeverityLevel('HIGH', 3)

    _members = (INFO, LOW, MEDIUM, HIGH)
    _members_by_name = dict(
        (member.name, member) for member in _members
    )

    def __init__(self, level):
        if isinstance(level, _SeverityLevel):
            if level not in self._members:
                raise InvalidSeverity(
                    "unknown severity level: {!r}".format(level)
                )
            self.level = level
        elif isinstance(level, Severity):
            self.level = level.level
        elif isinstance(level, string_types):
            normalized = level.strip().upper()
            if normalized not in self._members_by_name:
                raise InvalidSeverity(
                    "unknown severity level: {!r}".format(level)
                )
            self.level = self._members_by_name[normalized]
        else:
            raise InvalidSeverity(
                "unknown severity level: {!r}".format(level)
            )

    @classmethod
    def parse(cls, value):
        """Return the :class:`Severity` for ``value`` or fail closed.

        Accepts existing :class:`Severity` instances, member names and
        member values. Any other input raises :class:`InvalidSeverity`.
        """
        if isinstance(value, Severity):
            return value
        return cls(value)

    @classmethod
    def members(cls):
        """Return all valid levels ordered from lowest to highest."""
        return tuple(cls(member) for member in cls._members)

    @property
    def name(self):
        return self.level.name

    @property
    def rank(self):
        return self.level.rank

    def __eq__(self, other):
        try:
            other = self.parse(other)
        except InvalidSeverity:
            return NotImplemented
        return self.rank == other.rank

    def __lt__(self, other):
        try:
            other = self.parse(other)
        except InvalidSeverity:
            return NotImplemented
        return self.rank < other.rank

    def __hash__(self):
        return hash(self.level)

    def __str__(self):
        return self.level.name

    def __repr__(self):
        return "Severity({!r})".format(self.level.name)
