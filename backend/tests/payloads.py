"""Helpers for reading API payloads in tests, shared by the SCRUM-43 tests.

Not a test module itself: `unittest discover` only collects test*.py files.
"""


def texts(value):
    """Every piece of text in a result, at any depth, without the field names."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in texts(item)]
    return []
