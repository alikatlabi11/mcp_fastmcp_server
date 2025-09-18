# app/services/validator.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Union
import json
from jsonschema import Draft202012Validator, Draft7Validator, Draft201909Validator
from jsonschema.exceptions import ValidationError

class JsonValidatorService:
    """
    Validate JSON instances against JSON Schema (default draft 2020-12).
    Returns a structured result with validity and error details.
    """

    _DRAFTS = {
        "2020-12": Draft202012Validator,
        "2019-09": Draft201909Validator,
        "7": Draft7Validator,
    }

    def _ensure_obj(self, value: Union[str, Dict[str, Any], List[Any]]) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value

    def validate(
        self,
        instance: Union[str, Dict[str, Any], List[Any]],
        schema: Union[str, Dict[str, Any]],
        draft: str = "2020-12",
    ) -> Dict[str, Any]:
        inst = self._ensure_obj(instance)
        sch = self._ensure_obj(schema)

        if draft not in self._DRAFTS:
            raise ValueError(f"Unsupported JSON Schema draft: {draft}")

        Validator = self._DRAFTS[draft]
        validator = Validator(sch)

        errors: List[ValidationError] = sorted(validator.iter_errors(inst), key=lambda e: e.path)
        if not errors:
            return {"valid": True, "errors": []}

        def to_path(err: ValidationError) -> str:
            # Convert deque/path into JSON Pointer-like string
            segments = [str(p) for p in err.path]
            return "/" + "/".join(segments) if segments else "/"

        results = []
        for e in errors:
            entry = {
                "path": to_path(e),
                "keyword": e.validator,                # e.g., "type", "minimum"
                "message": e.message,
            }
            # Expected constraint (optional but useful)
            if e.validator is not None and e.validator_value is not None:
                entry["expected"] = {str(e.validator): e.validator_value}
            # Found value (can be large; include a preview)
            try:
                entry["found"] = e.instance
            except Exception:
                pass
            results.append(entry)

        return {"valid": False, "errors": results}
