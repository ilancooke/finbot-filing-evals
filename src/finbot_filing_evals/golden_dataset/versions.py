"""Stable identifiers for serialized contracts and prompts.

Versions are identifiers, not package versions. Serialized schemas use
``<contract>.v<integer>`` and prompt files use ``<task>_v<integer>.txt``.
Once artifacts exist for a version, that version must not be edited in place.
"""

ANNOTATION_ENVELOPE_SCHEMA_VERSION = "golden_dataset.annotation_envelope.v1"

VISUAL_TABLE_EXTRACTION_PROMPT_VERSION = "visual_table_extraction_v1"
VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION = "visual_table_extraction.v1"

# These are filled with the exact packaged-resource digests. A changed V1
# resource must fail integrity checks rather than silently changing its meaning.
VISUAL_TABLE_EXTRACTION_PROMPT_SHA256 = (
    "a3983d864a25dbb7943bf061dc99acf18a283209bbe7e1fde883f0c679a42972"
)
VISUAL_TABLE_EXTRACTION_SCHEMA_SHA256 = (
    "0ceb11c19035f809fedc586667224238c57755da9d3b128754169451f631491a"
)
