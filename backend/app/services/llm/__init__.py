"""Provider-agnostic LLM access for selector generation (Item 16).

``schemas`` holds the validated structured-output type; ``client`` resolves which
credential to use and builds the matching Pydantic AI model.
"""
