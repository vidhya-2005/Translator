def validate_source_target(source, target):
    if not source:
        raise ValueError("Source language is required.")
    if not target:
        raise ValueError("Target language is required.")
