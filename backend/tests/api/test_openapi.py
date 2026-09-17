from app.main import create_app


def test_openapi_describes_responses():
    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    for name in ["JobDetailOut", "JobListOut", "FitResultOut", "ProfileSaveOut", "ScoringSettingsOut", "MetaOut",
                 "EvaluatePostingOut", "SemanticSignals", "HealthOut", "RequestRebuildOut", "BatchOut"]:
        assert name in schemas, name
    detail = spec["paths"]["/api/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert detail == {"$ref": "#/components/schemas/JobDetailOut"}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            ok = next((code for code in op["responses"] if code.startswith("2")), None)
            if ok != "204":
                assert op["responses"][ok].get("content", {}).get("application/json", {}).get("schema"), (method, path)
