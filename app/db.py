import os
import pymysql
import pymysql.cursors
from flask import g


def get_db():
    """Returns the request-scoped DB connection, opening one if needed."""
    if "db" not in g:
        g.db = pymysql.connect(
            host=os.environ["DB_HOST"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASS"],
            database=os.environ.get("DB_NAME", "mystore"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query_one(sql, params=()):
    """SELECT ... expecting zero or one row. Returns a dict or None."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def query_all(sql, params=()):
    """SELECT ... expecting any number of rows. Returns a list of dicts."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE. Returns (rowcount, lastrowid)."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount, cur.lastrowid
