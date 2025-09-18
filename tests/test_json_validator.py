# tests/test_json_validate.py
from app.services.validator import JsonValidatorService

def test_json_validate_ok():
    svc = JsonValidatorService()
    instance = {"items": [{"sku": "A", "qty": 2}]}
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"sku": {"type": "string"}, "qty": 
                                   {"type": "integer", "minimum": 1}},
                    "required": ["sku", "qty"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
    }
    res = svc.validate(instance, schema, "2020-12")
    assert res["valid"] is True
    assert res["errors"] == []

def test_json_validate_errors():
    svc = JsonValidatorService()
    instance = {"items": [{"sku": "A", "qty": 0}]}
    schema = {
        "type": "object",
        "properties": {
            "items": {"type": "array", 
                      "items": {"type": "object", "properties": {"qty": {"minimum": 1}}}}
        },
        "required": ["items"],
    }
    res = svc.validate(instance, schema)
    assert res["valid"] is False
    # At least one error referencing "minimum"
    assert any(e.get("keyword") == "minimum" for e in res["errors"])
