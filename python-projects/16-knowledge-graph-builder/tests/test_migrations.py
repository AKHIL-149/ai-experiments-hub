"""The migrations must produce the same schema as the models, and keep existing data"""
import sqlite3

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from src.core import database
from src.core.migrate import BASELINE, _config, upgrade_to_head


def schema(engine):
    insp = inspect(engine)
    out = {}
    for t in sorted(insp.get_table_names()):
        if t == "alembic_version":
            continue
        cols = {c["name"]: (str(c["type"]).split("(")[0], c["nullable"]) for c in insp.get_columns(t)}
        idx = {(tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(t)}
        uq = {tuple(u["column_names"]) for u in insp.get_unique_constraints(t)}
        fks = {(tuple(f["constrained_columns"]), f["referred_table"], (f.get("options") or {}).get("ondelete")) for f in insp.get_foreign_keys(t)}
        out[t] = {"cols": cols, "idx": idx, "uq": uq, "fk": fks}
    return out


def test_migrated_schema_equals_the_models(tmp_path):
    migrated = create_engine(f"sqlite:///{tmp_path}/m.db")
    upgrade_to_head(migrated)
    built = create_engine(f"sqlite:///{tmp_path}/b.db")
    from src import models  # noqa: F401
    database.Base.metadata.create_all(bind=built)
    a, b = schema(migrated), schema(built)
    assert a.keys() == b.keys()
    for table in a:
        assert a[table]["cols"] == b[table]["cols"], table
        assert a[table]["fk"] == b[table]["fk"], table
        # unique constraints and unique indexes both enforce uniqueness: compare them together
        ua = a[table]["uq"] | {i for i, u in a[table]["idx"] if u}
        ub = b[table]["uq"] | {i for i, u in b[table]["idx"] if u}
        assert ua == ub, table
        assert {i for i, u in a[table]["idx"] if not u} == {i for i, u in b[table]["idx"] if not u}, table


def test_upgrade_is_repeatable_and_creates_the_version_table(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path}/m.db")
    upgrade_to_head(e)
    upgrade_to_head(e)
    assert "alembic_version" in inspect(e).get_table_names()


def populated_baseline(path):
    cfg = _config(f"sqlite:///{path}")
    command.upgrade(cfg, BASELINE)
    con = sqlite3.connect(path)
    con.executescript("""
    INSERT INTO documents(id,title,text,char_count,status,stats,chunk_count,chunks_done,created_at) VALUES('d1','Doc','some text',9,'COMPLETED','{}',1,1,'2026-01-01');
    INSERT INTO entities(id,name,key,type,created_at) VALUES('e1','Acme','acme','organization','2026-01-01'),('e2','Beta','beta','organization','2026-01-01');
    INSERT INTO entity_aliases(id,entity_id,key,name,created_at) VALUES('a1','e1','acme corp','Acme Corp','2026-01-01');
    INSERT INTO facts(id,subject_id,predicate,object_id,object_value,valid_from,valid_to,created_at) VALUES('f1','e1','acquired','e2','','','','2026-01-01');
    """)
    con.commit()
    con.close()


def test_existing_data_survives_the_upgrade_and_is_unowned(tmp_path):
    path = tmp_path / "old.db"
    populated_baseline(path)
    e = create_engine(f"sqlite:///{path}")
    upgrade_to_head(e)
    con = sqlite3.connect(path)
    assert con.execute("select count(*), count(owner_id) from entities").fetchone() == (2, 0)
    assert con.execute("select key, owner_id from entity_aliases").fetchall() == [("acme corp", None)]
    assert con.execute("select owner_id from facts").fetchall() == [(None,)]
    assert con.execute("select owner_id from documents").fetchall() == [(None,)]
    # two different owners may now have an entity with the same name
    con.execute("insert into users(id,username,password_hash,is_guest,is_active,created_at) values (1,'ann','x',0,1,'2026-01-01'),(2,'bob','x',0,1,'2026-01-01')")
    con.execute("insert into entities(id,name,key,type,created_at,owner_id) values ('e3','Acme','acme','organization','2026-01-01',1),('e4','Acme','acme','organization','2026-01-01',2)")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into entities(id,name,key,type,created_at,owner_id) values ('e5','Acme','acme','organization','2026-01-01',1)")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into entity_aliases(id,entity_id,key,name,created_at,owner_id) values ('a2','e3','x','X','2026-01-01',1), ('a3','e3','x','X','2026-01-01',1)")
    con.close()


def test_a_database_made_before_migrations_existed_is_adopted(tmp_path):
    """Steps 1-3 created tables with create_all and no alembic_version table"""
    path = tmp_path / "legacy.db"
    populated_baseline(path)
    con = sqlite3.connect(path)
    con.execute("drop table alembic_version")
    con.commit()
    con.close()
    e = create_engine(f"sqlite:///{path}")
    upgrade_to_head(e)
    insp = inspect(e)
    assert "users" in insp.get_table_names() and {"owner_id"} <= {c["name"] for c in insp.get_columns("entities")}
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from entities").fetchone() == (2,)


def test_a_database_already_at_the_newest_schema_without_history_is_stamped(tmp_path):
    from src import models  # noqa: F401
    e = create_engine(f"sqlite:///{tmp_path}/new.db")
    database.Base.metadata.create_all(bind=e)      # e.g. a database made by an in-between version of this step
    upgrade_to_head(e)
    assert "alembic_version" in inspect(e).get_table_names()


def test_downgrade_returns_to_the_baseline_schema(tmp_path):
    path = tmp_path / "d.db"
    cfg = _config(f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BASELINE)
    insp = inspect(create_engine(f"sqlite:///{path}"))
    assert "users" not in insp.get_table_names() and "owner_id" not in {c["name"] for c in insp.get_columns("entities")}
