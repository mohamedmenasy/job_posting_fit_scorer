from app.models import FitResult, JobEvaluation, JobPostingRow


def job_out(row: JobPostingRow) -> dict:
    return {k: getattr(row, k) for k in ("id", "company", "title", "location", "source", "source_url", "external_id",
                                         "salary_text", "description", "content_hash", "created_at", "imported_at")}


def fit_out(row: FitResult) -> dict:
    return {"id": row.id, "evaluation_id": row.evaluation_id, "profile_version_id": row.profile_version_id,
            "scoring_config_id": row.scoring_config_id, "scoring_config_version": row.scoring_config.version,
            "overall_score": row.overall_score, "aggregate_confidence": row.aggregate_confidence, "status": row.status,
            "needs_review": row.needs_review, "stale_semantics": row.stale_semantics, "created_at": row.created_at,
            **row.details}


def evaluation_out(row: JobEvaluation, *, signals: bool = False, raw: bool = False, fits: bool = True) -> dict:
    out = {k: getattr(row, k) for k in (
        "id", "job_id", "profile_version_id", "evaluator_version", "catalog_hash", "question_set_hash", "model", "status",
        "error", "latency_ms", "input_tokens", "output_tokens", "created_at", "started_at", "finished_at")}
    if signals:
        out["signals"] = row.signals
    if raw:
        out["raw_typesafe_response"] = row.raw_typesafe_response
    if fits:
        out["fit_results"] = [fit_out(f) for f in row.fit_results]
    return out
