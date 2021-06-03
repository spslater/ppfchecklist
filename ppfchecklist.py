"""Flask app for a reading list"""

import logging
import sqlite3
from abc import ABC, abstractmethod
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime
from io import UnsupportedOperation
from json import dumps, load
from os import fsync, getenv
from os.path import join
from sys import maxsize, stdout

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, send_from_directory
from tinydb import JSONStorage, TinyDB, where
from tinydb.operations import decrement, increment
from tinydb.table import Document, Table
from werkzeug.datastructures import ImmutableMultiDict

RequestForm = ImmutableMultiDict[str, str]


class PrettyJSONStorage(JSONStorage):
    """Story TinyDB data in a pretty format"""

    # pylint: disable=redefined-outer-name
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def write(self, data):
        self._handle.seek(0)
        serialized = dumps(data, indent=4, sort_keys=True, **self.kwargs)
        try:
            self._handle.write(serialized)
        except UnsupportedOperation as e:
            raise IOError(
                f'Cannot write to the database. Access mode is "{self._mode}"'
            ) from e

        self._handle.flush()
        fsync(self._handle.fileno())

        self._handle.truncate()


class TableNotFoundError(Exception):
    """Custom exception when table in database isn't found"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Database:
    def __init__(
        self,
        basedir: str = None,
        filename: str = None,
        tables: str = None,
    ):
        self._basedir = basedir or getenv("PPF_BASEDIR", ".")

        filename = filename or getenv("PPF_DATABASE", "list.db")
        self._filename = join(self._basedir, filename)

        tables = tables or getenv("PPF_TABLES", "tables.json")
        self._tables_file = join(self._basedir, tables)
        with open(self._tables_file, "r") as fp:
            self._tables = load(fp)

    def _get_table(self, name: str):
        raise NotImplementedError

    def info(self, table: str):
        raise NotImplementedError

    def insert(self, form: dict):
        raise NotImplementedError

    def update(self, form: dict):
        raise NotImplementedError

    def move(self, form: dict):
        raise NotImplementedError

    def delete(self, form: dict):
        raise NotImplementedError


class DatabaseSqlite3(Database):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self._connection = self._get_connection()
        # self._connection.row_factory = sqlite3.Row
        # self._database = self._connection.cursor()

        try:
            self._execute(
                """CREATE TABLE ppfchecklist
                (date TEXT, position INTEGER, name TEXT, checklist TEXT)"""
            )
        except sqlite3.OperationalError as e:
            logging.debug(e)
        except sqlite3.DatabaseError as e:
            logging.exception("Database provided is not an sqlite3 database")
            self._connection.close()
            raise e

    def _connection(self):
        db = getattr(g, "_sqlite3_database", None)
        if db is None:
            db = g._sqlite3_database = sqlite3.connect(self._filename)
            db.row_factory = sqlite3.Row
        return db

    def _execute(self, sql: str, parameters: tuple = None):
        db = self._connection()
        cur = db.cursor()
        result = cur.execute(sql, parameters) if parameters else cur.execute(sql)
        db.commit()
        return result

    def _executemany(self, sql: str, parameters: tuple = None):
        db = self._connection()
        cur = db.cursor()
        result = cur.executemany(sql, parameters) if parameters else cur.executemany(sql)
        db.commit()
        return result

    def import_json(self, filename: str):
        with open(filename, "r") as fp:
            data = load(fp)

        for table, values in data.items():
            if table == "_default":
                continue

            entries = [
                (val.get("date"), val.get("position"), val.get("name"), table)
                for val in values.values()
            ]
            self._executemany("INSERT INTO ppfchecklist VALUES (?, ?, ?, ?)", entries)

    def _get_table(self, name: str):
        if name not in self._tables:
            logging.error("Attempting to access table that does not exist: %s", name)
            raise TableNotFoundError(f"'{name}' is not a valid table name.")

    def info(self, table: str):
        self._get_table(table)
        todo = self._execute(
            """
            SELECT * FROM ppfchecklist
            WHERE checklist = ? AND position > 0
            ORDER BY position ASC
            """,
            (table,),
        ).fetchall()

        done = self._execute(
            """
            SELECT * FROM ppfchecklist
            WHERE checklist = ? AND position = 0
            ORDER BY date ASC
            """,
            (table,),
        ).fetchall()

        return todo, done


class DatabaseTinyDB(Database):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._database = TinyDB(self._filename, storage=PrettyJSONStorage)

    def _get_table(self, name: str):
        if name not in self._tables:
            logging.error("Attempting to access table that does not exist: %s", name)
            raise TableNotFoundError(f"'{name}' is not a valid table name.")
        return self._database.table(name)

    def info(self, table: str):
        items = self._get_table(table).all()
        todo = sorted(
            [a for a in items if a["position"] > 0],
            key=lambda i: i["position"],
        )
        done = sorted(
            [a for a in items if a["position"] == 0],
            key=lambda i: i["date"],
        )
        return todo, done


app = Flask(__name__, static_url_path="")


def getenv_bool(key, default=None):
    value = getenv(key)
    if value is None:
        if isinstance(default, bool):
            return default
        raise TypeError("Default value is not a `bool`")
    return value.lower() in ("true", "t", "1", "yes", "y")


def getenv_int(key, default=None):
    value = getenv(key)
    if value is None:
        if isinstance(default, int):
            return default
        raise TypeError("Default value is not an `int`")
    return int(value)


def get_ip(req: request) -> str:
    """Return the ip address of the request

    :param req: http request
    :type req: request
    :return: ip address of request
    :rtype: str
    """

    ip_address = None
    try:
        ip_address = req.headers["X-Forwarded-For"]
    except KeyError:
        ip_address = req.remote_addr
    return str(ip_address)


def get_table(thing: str) -> Table:
    """Get data from table in the database

    :param thing: name of table to lookup
    :type thing: str
    :raises TableNotFoundError: table does not exist in database
    :return: table from with the name passed in
    :rtype: Table
    """
    if thing not in tbls:
        logging.error("Attempting to access table that does not exist: %s", thing)
        raise TableNotFoundError(f"'{thing}' is not a valid table name.")
    return db.table(thing)


def get_table_all(thing: str) -> list[Document]:
    """Get all data in a table

    :param thing: name of table to lookup
    :type thing: str
    :raises TableNotFoundError: table does not exist in database
    :return: list of documents in the table
    :rtype: list[Document]
    """
    if thing not in tbls:
        logging.error("Attempting to access table that does not exist: %s", thing)
        raise TableNotFoundError(f"'{thing}' is not a valid table name.")
    return db.table(thing).all()


def get_list(items: list[Document]) -> tuple[list[Document], list[Document]]:
    """Separate the todo and done lists from a list of Documents

    :param items: list of Documents to split
    :type items: list[Document]
    :return: the todo and done items from given list of Documents
    :rtype: tuple[list[Document], list[Document]]
    """
    todo = sorted([a for a in items if a["position"] > 0], key=lambda i: i["position"])
    done = sorted([a for a in items if a["position"] == 0], key=lambda i: i["date"])
    return todo, done


@app.route("/favicon.ico")
def favicon():
    """Favicon icon endpoint"""
    return send_from_directory(
        "static",
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


def generate_document(form: RequestForm, table: Table) -> dict:
    """Generate an document to update current data with

    :param form: flask request form
    :type form: RequestForm
    :param table: table to get position information from
    :type table: Table
    :return: info to update document with
    :rtype: dict
    """
    max_pos = max([int(a["position"]) for a in table]) if len(table) else 0

    pos = max(0, int(form["position"] if form["position"] != "" else maxsize))
    position = pos if (pos <= max_pos) else (max_pos + 1)
    name = form["name"].strip()
    date = form["date"] if "date" in form else datetime.now().strftime("%Y-%m-%d")

    return {"position": position, "name": name, "date": date}


@app.route("/", methods=["GET"])
def index():
    """List all tables with their todo and done documents"""
    logging.info("GET /\t%s", get_ip(request))

    things_list = []
    for tbl in db._tables:
        todo, done = db.info(tbl)
        things_list.append({"thing": tbl, "todo": todo, "done": done})

    return render_template("index.html", things=things_list, tbls=db._tables)


# def insert_new_thing(doc: dict, table: Table, uri: str, ipaddr: str) -> str:
#     """Insert a new document into given table

#     :param doc: Data for new thing
#     :type doc: dict
#     :param table: table to insert into
#     :type table: Table
#     :param uri: path request was made for, for logging purposes
#     :type uri: str
#     :param ipaddr: ip request came from, for logging purposes
#     :type ipaddr: str
#     :return: new unique id for the document
#     :rtype: str
#     """
#     uid = -1
#     try:
#         if doc["position"] > 0:
#             table.update(increment("position"), where("position") >= doc["position"])
#             doc.pop("date", None)
#             uid = table.insert(doc)
#         elif doc["position"] <= 0:
#             doc["position"] = 0
#             if not doc["date"]:
#                 doc["date"] = datetime.now().strftime("%Y-%m-%d")
#             uid = table.insert(doc)
#         logging.info("POST /%s\t%s - %s", uri, ipaddr, doc)
#     # pylint: disable=broad-except
#     except Exception:
#         logging.exception("POST /%s\t%s - %s", uri, ipaddr, doc)
#     return uid


@app.route("/<string:thing>", methods=["GET", "POST"])
def things(thing: str):
    """View or create items for specific thing"""
    ipaddr = get_ip(request)
    if request.method == "GET":
        logging.info("GET /%s\t%s", thing, ipaddr)
        todo, done = db.info(thing)
        return render_template(
            "things.html", thing=thing, todo=todo, done=done, tbls=db._tables
        )
    # # request.method == "POST"
    # doc = generate_document(request.form, table)
    # insert_new_thing(doc, table, thing, ipaddr)
    return redirect(f"/{thing}")


# @app.route("/update/<string:thing>", methods=["POST"])
# def update(thing: str):
#     """Update item in list"""
#     ipaddr = get_ip(request)
#     table = get_table(thing)

#     form = request.form
#     uid = int(form["uid"])
#     new = int(form["new"])
#     old = int(form["old"])
#     name = form["name"].strip()
#     date = form["date"] if form["date"] else datetime.now().strftime("%Y-%m-%d")

#     try:
#         if old == new == 0:
#             table.update({"date": date, "name": name}, doc_ids=[uid])
#             logging.info(
#                 "UPDATE\t%s - %s %s\tChange Complete Date: %s",
#                 ipaddr,
#                 thing,
#                 uid,
#                 date,
#             )
#         elif old == new:
#             table.update({"name": name}, doc_ids=[uid])
#             logging.info("UPDATE\t%s - %s %s\tName Only: %s", ipaddr, thing, uid, name)
#         elif new <= 0:
#             table.update(decrement("position"), (where("position") > old))
#             table.update({"position": 0, "date": date, "name": name}, doc_ids=[uid])
#             logging.info(
#                 "UPDATE\t%s - %s %s\tFirst Complete: %s", ipaddr, thing, uid, date
#             )
#         elif old > new:
#             table.update(
#                 increment("position"),
#                 (where("position") >= new) & (where("position") < old),
#             )
#             table.update({"position": new, "name": name}, doc_ids=[uid])
#             logging.info(
#                 "UPDATE\t%s - %s %s\tMove Up In Rank\t%s -> %s",
#                 ipaddr,
#                 thing,
#                 uid,
#                 old,
#                 new,
#             )
#         elif old < new:
#             table.update(
#                 decrement("position"),
#                 (where("position") <= new) & (where("position") > old),
#             )
#             table.update({"position": new, "name": name}, doc_ids=[uid])
#             logging.info(
#                 "UPDATE\t%s - %s %s\tMove Down In Rank\t%s -> %s",
#                 ipaddr,
#                 thing,
#                 uid,
#                 old,
#                 new,
#             )
#     # pylint: disable=broad-except
#     except Exception:
#         logging.exception("UPDATE\t%s - %s %s: %s", ipaddr, thing, uid, form)

#     return redirect(f"/{thing}")


# @app.route("/move/<string:thing>", methods=["POST"])
# def move(thing: str):
#     """Move item from one list to another"""
#     ipaddr = get_ip(request)
#     table = get_table(thing)

#     form = request.form
#     uid = int(form["uid"])
#     old = int(form["old"])
#     new = int(form["new"])
#     pos = 0 if (old == new == 0) else (int(maxsize) if old == new else new)
#     table = form["table"]
#     new_table = get_table(table)
#     new_uid = -1

#     if new_table != thing:
#         val = table.get(doc_id=uid)
#         val["position"] = pos
#         new_val = generate_document(val, new_table)
#         new_uid = insert_new_thing(new_val, new_table, f"move/{thing}", ipaddr)
#         table.remove(doc_ids=[uid])
#         if pos != 0:
#             table.update(decrement("position"), (where("position") > old))
#         logging.info("MOVE\t%s - %s %s -> %s %s", ipaddr, thing, uid, table, new_uid)

#     return redirect(f"/{thing}")


# @app.route("/delete/<string:thing>", methods=["POST"])
# def delete(thing: str):
#     """Remove item from table"""
#     ipaddr = get_ip(request)
#     table = get_table(thing)

#     form = request.form
#     uid = int(form["uid"])
#     name = form["name"].strip()
#     val = table.get(doc_id=uid)

#     if val["name"] == name:
#         table.remove(doc_ids=[uid])
#         logging.info("DELETE\t%s - %s %s - %s", ipaddr, thing, uid, name)

#     return redirect(f"/{thing}")


if __name__ == "__main__":
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        add_help=False,
    )

    parser.add_argument("--help", action="help", help="show this help message and exit")

    parser.add_argument(
        "-e",
        "--env",
        dest="env",
        default=".env",
        help="File to load with environment settings",
        metavar="ENV",
    )

    args = parser.parse_args()

    try:
        load_dotenv(args.env, override=True)
    except IOError:
        logging.debug("No dotenv file found.")

    port = getenv_int("PPF_PORT", 80)
    debug = getenv_bool("PPF_DEBUG", False)

    basedir = getenv("PPF_BASEDIR", ".")

    output_file = getenv("PPF_LOGFILE", None)
    if output_file and output_file[0] != "/":
        output_file = join(basedir, output_file)

    instance_type = getenv("PPF_DATABASE_TYPE", "tinydb")
    if instance_type == "sqlite3":
        db = DatabaseSqlite3(basedir)
        db.import_json("tinydb.db")
    elif instance_type == "tinydb":
        db = DatabaseTinyDB(basedir)
    else:
        raise ValueError(
            "Database type is invalid,"
            f'must be either "sqlite3" or "tinydb" not "{instance_type}"'
        )

    handler_list = (
        [logging.StreamHandler(stdout), logging.FileHandler(output_file)]
        if output_file
        else [logging.StreamHandler(stdout)]
    )

    loglevel = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }[getenv("PPF_LOGLEVEL", "INFO")]

    logging.basicConfig(
        format="%(asctime)s\t[%(levelname)s]\t{%(module)s}\t%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=loglevel,
        handlers=handler_list,
    )

    if getenv_bool("PPF_AUTHORIZE", False):
        logging.debug("Setting up authorizing via OpenID Connect")
        from flask_oidc import OpenIDConnect

        app.config.update(
            {
                "SECRET_KEY": getenv("SECRET_KEY", "SUPERSECRETKEYTELLNOONE"),
                "TESTING": debug,
                "DEBUG": debug,
                "OIDC_CLIENT_SECRETS": getenv("OIDC_CLIENT_SECRETS"),
                "OIDC_ID_TOKEN_COOKIE_SECURE": True,
                "OIDC_REQUIRE_VERIFIED_EMAIL": False,
                "OIDC_USER_INFO_ENABLED": True,
                "OIDC_VALID_ISSUERS": getenv("OIDC_VALID_ISSUERS"),
                "OIDC_OPENID_REALM": getenv("OIDC_OPENID_REALM"),
                "OIDC_SCOPES": "openid",
                "OIDC_INTROSPECTION_AUTH_METHOD": "client_secret_post",
            }
        )
        oidc = OpenIDConnect()
        oidc.init_app(app)

        index = oidc.require_login(index)
        things = oidc.require_login(things)
        update = oidc.require_login(update)
        move = oidc.require_login(move)
        delete = oidc.require_login(delete)

    app.run(host="0.0.0.0", port=port, debug=debug)
