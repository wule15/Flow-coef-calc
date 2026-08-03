"""
The standard library only claim, enforced.

The README says this library has no runtime dependencies. That is a claim
about the code, so it is checked by reading the code rather than trusted.
"""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / 'flowcoefficient'

# Everything the package is allowed to import. All standard library.
ALLOWED = {'math', 'dataclasses', 'typing', '__future__', 'argparse', 'sys'}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # relative import, inside the package
                continue
            if node.module:
                found.add(node.module.split('.')[0])
    return found


def test_the_package_imports_nothing_outside_the_standard_library():
    offenders: dict[str, set[str]] = {}
    for module in sorted(PACKAGE.glob('*.py')):
        outside = _imported_top_level_modules(module) - ALLOWED
        if outside:
            offenders[module.name] = outside
    assert not offenders, (
        f'these modules import outside the standard library: {offenders}. '
        f'The README claims no runtime dependencies, so either the import '
        f'goes or the claim does.'
    )


def test_the_package_imports_cleanly_on_its_own():
    """A dependency that only appears at runtime would slip past the AST scan."""
    sys.path.insert(0, str(PACKAGE.parent))
    import flowcoefficient  # noqa: F401

    assert flowcoefficient.__version__
