"""
Connectors: run the evaluated CodeS pipeline against databases other than local SQLite files.

    PostgreSQL · MySQL / MariaDB · SQLite (any SQLAlchemy URL should work; these three are tested)

What a connector does, in the same shape as the authors' SQLite code so the prompt the model
sees has the same structure it was trained on:

  introspect()   tables, columns, types, primary keys, foreign keys and 2 representative
                 values per column  ->  the dict produced by codes_db_utils.get_db_schema
  build_index()  distinct cell values per column (<= 25 characters), gathered ONCE at connect
                 time — as the authors do with their Lucene index — instead of per question.
                 Capped at INDEX_CAP values per column (a documented deviation for scale).
  signature()    translate the SQLite-style SQL CodeS writes into the target dialect (sqlglot),
                 accept only a single read-only query, run it in a READ ONLY transaction with a
                 statement timeout and a row limit, and hash the result exactly as the
                 evaluation does, so candidate agreement means the same thing.

Nothing here ever writes to the connected database.
"""
from __future__ import annotations

import hashlib
import re

import sqlglot
from sqlglot import exp
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

INDEX_CAP = 5000          # distinct values indexed per column
ROW_LIMIT = 1000          # rows fetched per query
TIMEOUT_S = 30            # statement timeout

DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "mariadb": "mysql", "sqlite": "sqlite"}
KINDS = {"PostgreSQL": ("postgresql+psycopg", 5432), "MySQL / MariaDB": ("mysql+pymysql", 3306)}


class ReadOnlyViolation(ValueError):
    pass


def make_url(kind, host, port, database, user, password):
    driver, default_port = KINDS[kind]
    return URL.create(driver, username=user or None, password=password or None, host=host or "localhost",
                      port=int(port) if port else default_port, database=database)


def _type_name(t) -> str:
    """Normalise server type names towards the SQLite-style names CodeS saw in training."""
    s = str(t).lower()
    s = re.sub(r"character varying", "varchar", s)
    if s in ("integer", "bigint", "smallint", "int4", "int8", "int2") or s.startswith(("int(", "bigint(", "tinyint", "smallint(")):
        return "int"
    if s in ("double precision", "real", "float", "double") or s.startswith(("numeric", "decimal", "float")):
        return "real"
    return s


class SqlAlchemySource:
    """A connected database. `label` names it in the app; the password lives only in the engine."""

    def __init__(self, url, label: str | None = None):
        self.engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)
        self.backend = self.engine.dialect.name                     # postgresql / mysql / sqlite
        self.dialect = DIALECTS.get(self.backend, self.backend)     # sqlglot dialect name
        db = self.engine.url.database or "database"
        self.label = label or f"{db} · {self.backend}@{self.engine.url.host or 'local'}"
        self.db_id = str(db)
        self._schema = None
        self._index = None
        with self.engine.connect() as c:                            # fail fast on bad credentials
            c.execute(text("SELECT 1"))

    # ---------- read-only execution ----------
    def _begin_read_only(self, conn):
        if self.backend == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = '{TIMEOUT_S}s'"))
        elif self.backend in ("mysql", "mariadb"):
            conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME = {TIMEOUT_S * 1000}"))

    def _run(self, sql, limit=ROW_LIMIT):
        with self.engine.connect() as conn:
            if self.backend in ("mysql", "mariadb"):
                conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            trans = conn.begin()
            try:
                self._begin_read_only(conn)
                if self.engine.dialect.paramstyle in ("format", "pyformat"):
                    sql = sql.replace("%", "%%")                    # literal % (LIKE) is not a parameter
                res = conn.exec_driver_sql(sql)
                cols = list(res.keys())
                rows = [tuple(r) for r in res.fetchmany(limit)]
                return cols, rows
            finally:
                trans.rollback()                                    # never commit anything

    def translate(self, sql: str) -> str:
        """SQLite-style SQL from CodeS -> one read-only query in the target dialect."""
        try:
            trees = sqlglot.parse(sql, read="sqlite")
        except sqlglot.errors.ParseError as exc:
            raise ReadOnlyViolation(f"could not parse the query ({exc.errors[0]['description'] if exc.errors else exc})")
        trees = [t for t in trees if t is not None]
        if len(trees) != 1:
            raise ReadOnlyViolation("only a single query is allowed")
        tree = trees[0]
        if not isinstance(tree, exp.Query) or any(isinstance(n, (exp.Insert, exp.Update, exp.Delete, exp.Create,
                                                                  exp.Drop, exp.Alter, exp.Command))
                                                   for n in tree.walk()):
            raise ReadOnlyViolation("only read-only SELECT queries are allowed")
        return self._sqlite_semantics(tree).sql(dialect=self.dialect)

    def _known_names(self):
        sch = self.introspect()
        return {t["table_name"] for t in sch["schema_items"]} | \
               {c for t in sch["schema_items"] for c in t["column_names"]}

    def _sqlite_semantics(self, tree):
        """Rewrite the SQLite behaviours CodeS relies on (it learned on SQLite) so the query means
        the same thing on the target server. Measured by scripts/check_postgres_translation.py."""
        known = self._known_names()

        # 1. SQLite accepts "double-quoted" text as a string when no such column exists.
        def quoted_strings(node):
            if isinstance(node, exp.Column) and not node.table:
                ident = node.this
                if isinstance(ident, exp.Identifier) and ident.quoted and ident.name.lower() not in known:
                    return exp.Literal.string(ident.name)
            return node
        tree = tree.transform(quoted_strings)

        # 2. SQLite LIKE ignores (ASCII) case; Postgres LIKE does not.
        if self.dialect == "postgres":
            tree = tree.transform(lambda n: exp.ILike(this=n.this, expression=n.expression)
                                  if isinstance(n, exp.Like) else n)

        # 3. SQLite allows bare (non-grouped) columns next to aggregates; Postgres/MySQL(strict) do not.
        #    Wrap them in MAX(). Not done when MIN/MAX is present: there SQLite returns the row that
        #    holds the min/max, which MAX() would not reproduce — such queries are left to fail, and
        #    a failing candidate lowers agreement (the app abstains) instead of answering wrongly.
        if self.dialect != "sqlite":
            for sel in list(tree.find_all(exp.Select)):
                projs = sel.expressions
                has_agg = any(p.find(exp.AggFunc) for p in projs)
                group = sel.args.get("group")
                if not (has_agg or group) or any(p.find(exp.Max, exp.Min) for p in projs):
                    continue
                grouped = {g.sql().lower() for g in (group.expressions if group else [])}
                def bare(e):
                    return isinstance(e, exp.Column) and e.sql().lower() not in grouped
                new = []
                for p in projs:
                    target = p.this if isinstance(p, exp.Alias) else p
                    if bare(target):
                        wrapped = exp.alias_(exp.Max(this=target.copy()), p.alias_or_name, quoted=False)
                        new.append(wrapped)
                    else:
                        new.append(p)
                sel.set("expressions", new)
                order = sel.args.get("order")
                if order:
                    for o in order.expressions:
                        if bare(o.this):
                            o.set("this", exp.Max(this=o.this.copy()))
        return tree

    def explain_ok(self, sql: str) -> bool:
        """Analogue of the authors' EXPLAIN QUERY PLAN check: plan the query without running it."""
        try:
            self._run("EXPLAIN " + self.translate(sql), limit=1)
            return True
        except Exception:
            return False

    def signature(self, sql: str):
        """(ok, columns, rows, hash, error) — hash computed as in the evaluation."""
        try:
            cols, rows = self._run(self.translate(sql))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).splitlines()[0][:300]
            return False, [], [], None, msg
        canon = sorted([tuple(str(c) for c in r) for r in rows])
        return True, cols, rows, hashlib.md5(repr(canon).encode()).hexdigest(), ""

    # ---------- schema and value index ----------
    def _tables_in_creation_order(self, insp):
        names = insp.get_table_names()
        if self.backend == "postgresql":
            with self.engine.connect() as c:
                order = [r[0] for r in c.execute(text(
                    "SELECT relname FROM pg_class WHERE relkind = 'r' "
                    "AND relnamespace = 'public'::regnamespace ORDER BY oid"))]
            names = [n for n in order if n in names] + [n for n in names if n not in order]
        return names

    def _q(self, name):
        return self.engine.dialect.identifier_preparer.quote(name)

    def introspect(self):
        if self._schema is not None:
            return self._schema
        insp = inspect(self.engine)
        items, fks = [], []
        for t in self._tables_in_creation_order(insp):
            cols = insp.get_columns(t)
            pk = set(insp.get_pk_constraint(t).get("constrained_columns") or [])
            names = [c["name"] for c in cols]
            contents = []
            for n in names:
                try:
                    _, rows = self._run(f"SELECT DISTINCT {self._q(n)} FROM {self._q(t)} "
                                        f"WHERE {self._q(n)} IS NOT NULL LIMIT 2", limit=2)
                    vals = [str(r[0]).strip() for r in rows]
                    contents.append([v for v in vals if 0 < len(v) <= 25])
                except Exception:
                    contents.append([])
            items.append({"table_name": t.lower(), "table_comment": "",
                          "column_names": [n.lower() for n in names],
                          "column_types": [_type_name(c["type"]) for c in cols],
                          "column_comments": ["" for _ in names], "column_contents": contents,
                          "pk_indicators": [1 if n in pk else 0 for n in names]})
            for fk in insp.get_foreign_keys(t):
                for a, b in zip(fk["constrained_columns"], fk["referred_columns"]):
                    fks.append([t.lower(), a.lower(), fk["referred_table"].lower(), b.lower()])
        self._schema = {"schema_items": items, "foreign_keys": fks}
        return self._schema

    def build_index(self):
        if self._index is not None:
            return self._index
        idx = {}
        for item in self.introspect()["schema_items"]:
            t = item["table_name"]
            for c in item["column_names"]:
                try:
                    _, rows = self._run(f"SELECT DISTINCT {self._q(c)} FROM {self._q(t)} "
                                        f"WHERE {self._q(c)} IS NOT NULL LIMIT {INDEX_CAP}", limit=INDEX_CAP)
                except Exception:
                    continue
                vals = []
                for (v,) in rows:
                    v = str(v).strip()
                    if 0 < len(v) <= 25:
                        vals.append(v)
                if vals:
                    idx[f"{t}.{c}"] = sorted(set(vals))
        self._index = idx
        return idx

    def tables_summary(self):
        out = []
        for item in self.introspect()["schema_items"]:
            try:
                _, rows = self._run(f"SELECT COUNT(*) FROM {self._q(item['table_name'])}", limit=1)
                n = rows[0][0]
            except Exception:
                n = 0
            out.append((item["table_name"], item["column_names"], int(n)))
        return out
