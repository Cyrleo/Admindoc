from uuid import UUID


def make_json_safe(value):
    """Recursively convert values to JSON-serializable primitives for audit metadata."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    return value

