"""Flask app for a reading list"""

import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime
from io import UnsupportedOperation
from json import dumps, load
from os import fsync
from os.path import join
from sys import maxsize, stdout

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


app = Flask(__name__, static_url_path="")


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
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter, add_help=False)

    parser.add_argument("--help", action="help", help="show this help message and exit")

    parser.add_argument(
        "-b",
        "--basedir",
        dest="base",
        default="./",
        help="Base directory that files are located",
        metavar="BASE",
    )
    parser.add_argument(
        "-d",
        "--database",
        dest="database",
        default="list.db",
        help="TinyDB file location",
        metavar="DB",
    )
    parser.add_argument(
        "-t",
        "--tables",
        dest="tables",
        default="tables.json",
        help="JSON file with list of tables",
        metavar="TABLES",
    )
    parser.add_argument(
        "-a",
        "--authorize",
        dest="authorize",
        default=False,
        action="store_true",
        help="Validate users are authorized to access with sso login"
    )
    parser.add_argument(
        "-s",
        "--sso",
        dest="sso",
        default="client_secrets.json",
        help="SSO Client Secrets Json file",
        metavar="JSON",
    )
    parser.add_argument(
        "-e",
        "--sso-env",
        dest="env",
        default=".env",
        help="Environment file to load with OIDC settings",
        metavar="ENV",
    )

    parser.add_argument(
        "--log",
        dest="logfile",
        default=None,
        help="log file",
        metavar="LOGFILE",
    )
    parser.add_argument(
        "--mode",
        dest="mode",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="logging level for output",
        metavar="MODE",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=80,
        help="port the application will run on",
        metavar="PORT",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        default=False,
        action="store_true",
        help="run application in debug mode, reloading on file changes",
    )

    args = parser.parse_args()

    port = args.port
    debug = args.debug

    database = join(args.base, args.database)
    tables = join(args.base, args.tables)
    output = args.logfile

    db = TinyDB(database, storage=PrettyJSONStorage)

    with open(tables, "r") as f:
        tbls = load(f)

    handler_list = (
        [logging.StreamHandler(stdout), logging.FileHandler(output)]
        if output
        else [logging.StreamHandler(stdout)]
    )

    logging.basicConfig(
        format="%(asctime)s\t[%(levelname)s]\t{%(module)s}\t%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG if args.debug else logging.INFO,
        handlers=handler_list,
    )

    if args.authorize:
        logging.debug("Setting up authorizing via OpenID Connect")
        from os import getenv
        from dotenv import load_dotenv
        from flask_oidc import OpenIDConnect

        try:
            load_dotenv(args.env, override=True)
        except IOError:
            logging.warning("No dotenv file found.")
        app.config.update(
            {
                "SECRET_KEY": getenv("SECRET_KEY", "SUPERSECRETKEYTELLNOONE"),
                "TESTING": args.debug,
                "DEBUG": args.debug,
                "OIDC_CLIENT_SECRETS": args.sso,
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
