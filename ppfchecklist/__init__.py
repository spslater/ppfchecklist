"""Flask app for a reading list"""
import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime
from json import load
from os import getenv
from os.path import join
from sys import maxsize, stdout

from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)
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


@app.route("/download", methods=["GET"])
def dump():
    return jsonify(get_db().download())


@app.route("/upload", methods=["GET", "POST"])
def upload():
    """Upload json to load info into database"""
    if request.method == "GET":
        return render_template("upload.html.j2")

    filename = request.files["filename"]
    data = load(filename.stream)
    get_db().upload(data)
    return redirect("/")


@app.route("/", methods=["GET"])
def index():
    """List all tables with their todo and done documents"""
    logging.info("GET /\t%s", get_ip(request))

    db = get_db()
    tables = db.tables()
    things_list = []
    for table in tables:
        tbl = table["name"]
        results = db.info(tbl, limit=10)
        things_list.append(
            {
                "thing": table,
                "results": results,
                "status": db.status(tbl),
            }
        )

    return render_template("index.html.j2", things=things_list, tbls=tables)


@app.route("/list/<string:thing>", methods=["GET"])
def things(thing: str):
    """View or create items for specific thing"""
    logging.info("GET /%s\t%s", thing, get_ip(request))

    db = get_db()
    if not db.is_table(thing):
        return redirect("/")
    results = db.info(thing)
    return render_template(
        "things.html.j2",
        thing=db.table(thing),
        results=results,
        tbls=db.tables(),
        status=db.status(thing),
    )


@app.route("/insert/<string:thing>", methods=["POST"])
def insert(thing: str):
    """Insert item in list"""
    ipaddr = get_ip(request)
    get_db().insert(request.form, thing)
    return redirect(f"/list/{thing}")


@app.route("/update/<string:thing>", methods=["POST"])
def update(thing: str):
    """Update item in list"""
    ipaddr = get_ip(request)
    goto = get_db().update(request.form, thing)
    return redirect(f"/list/{goto}")


@app.route("/delete/<string:thing>", methods=["POST"])
def delete(thing: str):
    """Remove item from table"""
    ipaddr = get_ip(request)
    get_db().delete(request.form)
    logging.info("DELETE\t%s - %s", ipaddr, thing)
    return redirect(f"/list/{thing}")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    db = get_db()
    if request.method == "GET":
        settings = db.get_settings()
        return render_template("settings.html.j2", settings=settings)
    res = db.set_settings(request.form)
    return redirect("/")


@app.route("/<string:unknown>", methods=["GET"])
def unknown(unknown: str):
    is_table = get_db().is_table(unknown)
    redirect_url = f"/list/{unknown}" if is_table else "/"
    return redirect(redirect_url)


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = DatabaseSqlite3(getenv("PPF_BASEDIR", "."))
    return db


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
    dump = oidc.require_login(dump)
    upload = oidc.require_login(upload)
    things = oidc.require_login(things)
    update = oidc.require_login(update)
    delete = oidc.require_login(delete)

app.run(host="0.0.0.0", port=port, debug=debug)
