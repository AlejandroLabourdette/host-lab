"""Export the title contract as JSON Schema.

ADR 0008 makes the Pydantic models the source of truth and the schema a
generated artifact, so the two cannot disagree. The schema is committed anyway,
because it is what lets an editor or a CI job check a manifest without running
this package, and because a diff on it is the visible signal that the contract
changed.

Regenerate with `make schema`. A test fails if the committed file has drifted,
which is what stops "generated" quietly becoming "stale".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hostlab.manifest import TitleManifest

SCHEMA_PATH = Path("titles/schema.json")


def json_schema() -> dict[str, Any]:
    schema = TitleManifest.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Game server title manifest"
    schema["description"] = (
        "The title contract of ADR 0005. Generated from hostlab.manifest; "
        "edit the models, not this file."
    )
    return schema


def render() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
