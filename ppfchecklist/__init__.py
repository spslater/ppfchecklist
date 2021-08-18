"""Flask app for a reading list"""
import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime
from os import getenv
from os.path import join
from sys import maxsize, stdout

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, send_from_directory
from werkzeug.datastructures import ImmutableMultiDict

from .database import DatabaseSqlite3

RequestForm = ImmutableMultiDict[str, str]

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

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


@app.route("/favicon.ico")
def favicon():
    """Favicon icon endpoint"""
    return send_from_directory(
        "static",
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


def generate_document(form: RequestForm, table) -> dict:
    """Generate an document to update current data with"""
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

    db = get_db()
    tables = db.tables()
    things_list = []
    for tbl in tables:
        todo, done = db.info(tbl["rowid"])
        things_list.append({"thing": tbl["name"], "todo": todo, "done": done})

    return render_template("index.html", things=things_list, tbls=[t["name"] for t in tables])


@app.route("/dump", methods=["GET"])
def dump():
    return str(get_db().dump())

@app.route("/load", methods=["GET"])
def load():
    get_db().import_json("list.db.sample")
    return redirect("/")

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


@app.route("/list/<string:thing>", methods=["GET", "POST"])
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


def get_db():
    db = getattr(g, "_database", None)
    print("getting db", db)
    if db is None:
        db = g._database = DatabaseSqlite3(getenv("PPF_BASEDIR", "."))
    return db


def _main():
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

    # if getenv_bool("PPF_AUTHORIZE", False):
    #     logging.debug("Setting up authorizing via OpenID Connect")
    #     from flask_oidc import OpenIDConnect

    #     app.config.update(
    #         {
    #             "SECRET_KEY": getenv("SECRET_KEY", "SUPERSECRETKEYTELLNOONE"),
    #             "TESTING": debug,
    #             "DEBUG": debug,
    #             "OIDC_CLIENT_SECRETS": getenv("OIDC_CLIENT_SECRETS"),
    #             "OIDC_ID_TOKEN_COOKIE_SECURE": True,
    #             "OIDC_REQUIRE_VERIFIED_EMAIL": False,
    #             "OIDC_USER_INFO_ENABLED": True,
    #             "OIDC_VALID_ISSUERS": getenv("OIDC_VALID_ISSUERS"),
    #             "OIDC_OPENID_REALM": getenv("OIDC_OPENID_REALM"),
    #             "OIDC_SCOPES": "openid",
    #             "OIDC_INTROSPECTION_AUTH_METHOD": "client_secret_post",
    #         }
    #     )
    #     oidc = OpenIDConnect()
    #     oidc.init_app(app)

    #     index = oidc.require_login(index)
    #     things = oidc.require_login(things)
    #     update = oidc.require_login(update)
    #     move = oidc.require_login(move)
    #     delete = oidc.require_login(delete)

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    _main()
