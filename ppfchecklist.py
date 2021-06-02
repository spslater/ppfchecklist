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
from flask import Flask, redirect
from flask import render_template as render
from flask import request, send_from_directory
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
        with open(tables_file, "r") as fp:
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._connection = sqlite3.connect(self._filename)
        self._database = self._connection.cursor()

        try:
            self._database.execute(
                """CREATE TABLE list
                (date TEXT, position INTEGER, name TEXT, table TEXT)"""
            )
        except sqlite3.ProgrammingError:
            pass
        except sqlite3.DatabaseError as e:
            logging.exception("Database provided is not an sqlite3 database")
            self._connection.close()
            raise e

        self._connection.row_factory = sqlite3.Row

    def _get_table(self, name: str):
        if name not in self._tables:
            logging.error("Attempting to access table that does not exist: %s", name)
            raise TableNotFoundError(f"'{name}' is not a valid table name.")
        return self._database.execute("SELECT * FROM list WHERE table = ?", (name,))

    def info(self, table: str):
        todo = self._database.execute(
            """
            SELECT * FROM list
            WHERE table = ? AND position > 0
            ORDER BY position ASC
            """,
            (table,)
        ).fetchall()

        done = self._database.execute(
            """
            SELECT * FROM list
            WHERE table = ? AND position = 0
            ORDER BY date ASC
            """,
            (table,),
        ).fetchall()

        return todo, done


class DatabaseTinyDB(Database):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._database = TinyDB(self._filename, storage=PrettyJSONStorage)

    def _get_table(self, name: str):
        if name not in self._tables:
            logging.error("Attempting to access table that does not exist: %s", name)
            raise TableNotFoundError(f"'{name}' is not a valid table name.")
        return self._database.table(name)

    def info(self, table: str):
        if table not in tbls:
            logging.error("Attempting to access table that does not exist: %s", table)
            raise TableNotFoundError(f"'{table}' is not a valid table name.")
        items = self._database.table(table).all()

        todo = sorted([a for a in items if a["position"] > 0], key=lambda i: i["position"])
        done = sorted([a for a in items if a["position"] == 0], key=lambda i: i["date"])
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
    for tbl in tbls:
        tb_all = get_table_all(tbl)
        todo, done = get_list(tb_all)
        things_list.append({"thing": tbl, "todo": todo, "done": done})

    return render("index.html", things=things_list, tbls=tbls)


def insert_new_thing(doc: dict, table: Table, uri: str, ipaddr: str) -> str:
    """Insert a new document into given table

    :param doc: Data for new thing
    :type doc: dict
    :param table: table to insert into
    :type table: Table
    :param uri: path request was made for, for logging purposes
    :type uri: str
    :param ipaddr: ip request came from, for logging purposes
    :type ipaddr: str
    :return: new unique id for the document
    :rtype: str
    """
    uid = -1
    try:
        if doc["position"] > 0:
            table.update(increment("position"), where("position") >= doc["position"])
            doc.pop("date", None)
            uid = table.insert(doc)
        elif doc["position"] <= 0:
            doc["position"] = 0
            if not doc["date"]:
                doc["date"] = datetime.now().strftime("%Y-%m-%d")
            uid = table.insert(doc)
        logging.info("POST /%s\t%s - %s", uri, ipaddr, doc)
    # pylint: disable=broad-except
    except Exception:
        logging.exception("POST /%s\t%s - %s", uri, ipaddr, doc)
    return uid


@app.route("/<string:thing>", methods=["GET", "POST"])
def things(thing: str):
    """View or create items for specific thing"""
    ipaddr = get_ip(request)
    table = get_table(thing)
    if request.method == "GET":
        logging.info("GET /%s\t%s", thing, ipaddr)
        todo, done = get_list(table.all())
        return render("things.html", thing=thing, todo=todo, done=done, tbls=tbls)
    # request.method == "POST"
    doc = generate_document(request.form, table)
    insert_new_thing(doc, table, thing, ipaddr)
    return redirect(f"/{thing}")


@app.route("/update/<string:thing>", methods=["POST"])
def update(thing: str):
    """Update item in list"""
    ipaddr = get_ip(request)
    table = get_table(thing)

    form = request.form
    uid = int(form["uid"])
    new = int(form["new"])
    old = int(form["old"])
    name = form["name"].strip()
    date = form["date"] if form["date"] else datetime.now().strftime("%Y-%m-%d")

    try:
        if old == new == 0:
            table.update({"date": date, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tChange Complete Date: %s",
                ipaddr,
                thing,
                uid,
                date,
            )
        elif old == new:
            table.update({"name": name}, doc_ids=[uid])
            logging.info("UPDATE\t%s - %s %s\tName Only: %s", ipaddr, thing, uid, name)
        elif new <= 0:
            table.update(decrement("position"), (where("position") > old))
            table.update({"position": 0, "date": date, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tFirst Complete: %s", ipaddr, thing, uid, date
            )
        elif old > new:
            table.update(
                increment("position"),
                (where("position") >= new) & (where("position") < old),
            )
            table.update({"position": new, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tMove Up In Rank\t%s -> %s",
                ipaddr,
                thing,
                uid,
                old,
                new,
            )
        elif old < new:
            table.update(
                decrement("position"),
                (where("position") <= new) & (where("position") > old),
            )
            table.update({"position": new, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tMove Down In Rank\t%s -> %s",
                ipaddr,
                thing,
                uid,
                old,
                new,
            )
    # pylint: disable=broad-except
    except Exception:
        logging.exception("UPDATE\t%s - %s %s: %s", ipaddr, thing, uid, form)

    return redirect(f"/{thing}")


@app.route("/move/<string:thing>", methods=["POST"])
def move(thing: str):
    """Move item from one list to another"""
    ipaddr = get_ip(request)
    table = get_table(thing)

    form = request.form
    uid = int(form["uid"])
    old = int(form["old"])
    new = int(form["new"])
    pos = 0 if (old == new == 0) else (int(maxsize) if old == new else new)
    table = form["table"]
    new_table = get_table(table)
    new_uid = -1

    if new_table != thing:
        val = table.get(doc_id=uid)
        val["position"] = pos
        new_val = generate_document(val, new_table)
        new_uid = insert_new_thing(new_val, new_table, f"move/{thing}", ipaddr)
        table.remove(doc_ids=[uid])
        if pos != 0:
            table.update(decrement("position"), (where("position") > old))
        logging.info("MOVE\t%s - %s %s -> %s %s", ipaddr, thing, uid, table, new_uid)

    return redirect(f"/{thing}")


@app.route("/delete/<string:thing>", methods=["POST"])
def delete(thing: str):
    """Remove item from table"""
    ipaddr = get_ip(request)
    table = get_table(thing)

    form = request.form
    uid = int(form["uid"])
    name = form["name"].strip()
    val = table.get(doc_id=uid)

    if val["name"] == name:
        table.remove(doc_ids=[uid])
        logging.info("DELETE\t%s - %s %s - %s", ipaddr, thing, uid, name)

    return redirect(f"/{thing}")


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

    database_file = getenv("PPF_DATABASE", "list.db")
    database = join(basedir, database_file)

    tables_file = getenv("PPF_TABLES", "tables.json")
    tables = join(basedir, tables_file)

    output_file = getenv("PPF_LOGFILE", None)
    if output_file and output_file[0] != "/":
        output_file = join(basedir, output_file)

    db = TinyDB(database, storage=PrettyJSONStorage)

    with open(tables, "r") as f:
        tbls = load(f)

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
