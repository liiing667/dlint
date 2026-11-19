#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast


PARENT_ATTR = '_dlint_parent'


def attach_parents(tree):
    """Walk the whole tree and attach a parent reference to every node.

    The reference is stored on the node itself so a linter can reconstruct
    the AST parent chain from any node without re-walking the tree. The
    operation is idempotent: re-attaching parents refreshes the links.
    """
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            setattr(child, PARENT_ATTR, node)

    setattr(tree, PARENT_ATTR, None)
    return tree


def get_parent(node):
    """Return the direct AST parent attached by ``attach_parents``."""
    return getattr(node, PARENT_ATTR, None)


def iter_parents(node):
    """Yield every ancestor of ``node`` from the direct parent to the root."""
    parent = get_parent(node)
    while parent is not None:
        yield parent
        parent = get_parent(parent)


def get_enclosing_scope(node):
    """Return the closest function, class, or module node enclosing ``node``."""
    scope_types = (ast.Module, ast.ClassDef, ast.FunctionDef)
    if hasattr(ast, 'AsyncFunctionDef'):
        scope_types += (ast.AsyncFunctionDef,)

    for parent in iter_parents(node):
        if isinstance(parent, scope_types):
            return parent

    if isinstance(node, ast.Module):
        return node

    return None
