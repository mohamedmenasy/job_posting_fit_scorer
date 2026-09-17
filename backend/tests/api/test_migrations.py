from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import app.models  # noqa: F401
from app.db import Base, make_engine, run_migrations


def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    run_migrations(url)
    engine = make_engine(url)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        fks = inspect(conn).get_foreign_keys("job_postings")
        assert [fk["referred_table"] for fk in fks] == ["fit_results"]
    assert {"profile_versions", "job_postings", "job_evaluations", "scoring_configs", "fit_results"} <= \
        set(inspect(engine).get_table_names())
