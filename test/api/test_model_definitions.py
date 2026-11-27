"""The program model is defined twice, in api/models.py (Pydantic) and in
frontend/src/models/ (TypeScript), and the two have to change together: a
field added on one side only is dropped by Pydantic, or never sent by the
frontend, with no error. These tests compare the fields of each Pydantic
model with those of the TypeScript type of the same name, by name."""

import re
from pathlib import Path

import pytest

# The API reads and writes programs with pydantic 2 (api/requirements.txt).
import pydantic  # noqa: E402

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip(
        f"the API needs pydantic 2, and the Python of this pytest has {pydantic.VERSION}",
        allow_module_level=True,
    )

from api import models  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "models"


def _read_typescript_models() -> str:
    """Returns the text of every TypeScript file of the models of the
    frontend, its tests left out."""
    files = sorted(MODELS_DIR.glob("*.ts"))
    return "\n".join(f.read_text() for f in files if not f.name.endswith(".test.ts"))


def _find_typescript_fields(source: str, name: str) -> set[str] | None:
    """Takes the text of the TypeScript models and the name of a type;
    returns the names of the top-level fields of the exported interface or
    object type of that name, or None when there is none."""
    match = re.search(r"export (?:interface|type) " + name + r"\b[^{=]*=?\s*\{", source)
    if not match:
        return None
    # The body, up to the brace that closes the one the match ends on
    depth, end = 1, match.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(source[end], 0)
        end += 1
    fields, depth = set(), 0
    for line in source[match.end():end - 1].splitlines():
        stripped = line.strip()
        # A field of a nested object type belongs to that type, not to this one
        if depth == 0:
            field = re.match(r"^(\w+)\??\s*:", stripped)
            if field:
                fields.add(field.group(1))
        depth += stripped.count("{") - stripped.count("}")
    return fields


def _list_pydantic_models() -> dict[str, type[pydantic.BaseModel]]:
    """Returns the Pydantic models that api/models.py defines, by name."""
    found = {}
    for name, value in vars(models).items():
        if (
            isinstance(value, type)
            and issubclass(value, pydantic.BaseModel)
            and value.__module__ == models.__name__
        ):
            found[name] = value
    return found


def test_every_model_of_the_backend_has_a_type_of_the_frontend_with_the_same_fields():
    source = _read_typescript_models()
    pydantic_models = _list_pydantic_models()
    assert "Program" in pydantic_models and "ProgramOption" in pydantic_models

    mismatches = []
    for name, model in sorted(pydantic_models.items()):
        typescript_fields = _find_typescript_fields(source, name)
        if typescript_fields is None:
            mismatches.append(f"{name}: no TypeScript type of that name")
            continue
        pydantic_fields = set(model.model_fields)
        if pydantic_fields != typescript_fields:
            mismatches.append(
                f"{name}: only in Pydantic {sorted(pydantic_fields - typescript_fields)}, "
                f"only in TypeScript {sorted(typescript_fields - pydantic_fields)}"
            )
    assert mismatches == []
