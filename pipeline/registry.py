"""Parser registry: format_id -> parser instance.

Adding a hospital of an existing format needs no code change (bind its file to a
format_id in the hospitals input). Adding a genuinely new format is a two-line change:
import the parser module and add one entry here.
"""

from __future__ import annotations

from .parsers.base import Parser
from .parsers.hospital_generic_csv import GenericCsvParser
from .parsers.hospital_generic_json import GenericJsonParser

REGISTRY: dict[str, Parser] = {
    GenericCsvParser.format_id: GenericCsvParser(),
    GenericJsonParser.format_id: GenericJsonParser(),
}


class UnknownFormatError(KeyError):
    """Raised when a hospital references a format_id with no registered parser."""


def get_parser(format_id: str) -> Parser:
    try:
        return REGISTRY[format_id]
    except KeyError as exc:
        raise UnknownFormatError(
            f"no parser registered for format_id {format_id!r}; "
            f"known: {sorted(REGISTRY)}"
        ) from exc
