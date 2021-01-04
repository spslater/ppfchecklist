import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime
from io import UnsupportedOperation
from json import dumps, load
from os import fsync
from os.path import join
from pprint import pformat
from sys import argv, maxsize, stdout

from flask import Flask, redirect
from flask import render_template as render
from flask import request, send_from_directory
from tinydb import JSONStorage, TinyDB, where
from tinydb.operations import decrement, increment


class PrettyJSONStorage(JSONStorage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def write(self, data):
        self._handle.seek(0)
        serialized = dumps(data, indent=4, sort_keys=True, **self.kwargs)
        try:
            self._handle.write(serialized)
        except UnsupportedOperation:
            raise IOError(
                f'Cannot write to the database. Access mode is "{self._mode}"'
            )

        self._handle.flush()
        fsync(self._handle.fileno())

        self._handle.truncate()


class TableNotFoundError(Exception):
    def __init__(self, message):
        self.message = message


app = Flask(__name__, static_url_path="")


def getIp(request):
    ip = None
    try:
        ip = request.headers["X-Forwarded-For"]
    except:
        ip = request.remote_addr
    return str(ip)


def getTable(thing):
    if thing not in tbls:
        logging.error("Attempting to access table that does not exist: %s", thing)
        raise TableNotFoundError(f"'{thing}' is not a valid table name.")
    return db.table(thing)


def getTableAll(thing):
    if thing not in tbls:
        logging.error("Attempting to access table that does not exist: %s", thing)
        raise TableNotFoundError(f"'{thing}' is not a valid table name.")
    return db.table(thing).all()


def getList(all_items):
    todo = sorted(
        [a for a in all_items if a["position"] > 0], key=lambda i: i["position"]
    )
    done = sorted([a for a in all_items if a["position"] == 0], key=lambda i: i["date"])
    return todo, done


def genDoc(form, db):
    maxPos = max([int(a["position"]) for a in db]) if len(db) else 0

    pos = max(0, int(form["position"] if form["position"] != "" else maxsize))
    position = pos if (pos <= maxPos) else (maxPos + 1)
    name = form["name"].strip()
    date = form["date"] if "date" in form else datetime.now().strftime("%Y-%m-%d")

    return {"position": position, "name": name, "date": date}


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        "static",
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/", methods=["GET"])
def index():
    ip = getIp(request)

    for tb in tbls:
        tb_all = getTableAll(tb)
        todo, done = getList(tb_all)
        things.append({"thing": tb, "todo": todo, "done": done})

    return render("index.html", things=things, tbls=tbls)


def insertNewThing(doc, db, uri, ip):
    uid = -1
    try:
        if doc["position"] > 0:
            db.update(increment("position"), where("position") >= doc["position"])
            doc.pop("date", None)
            uid = db.insert(doc)
        elif doc["position"] <= 0:
            doc["position"] = 0
            if not doc["date"]:
                doc["date"] = datetime.now().strftime("%Y-%m-%d")
            uid = db.insert(doc)
        logging.info("POST /%s\t%s - %s", uri, ip, doc)
    except Exception as e:
        logging.exception("POST /%s\t%s - %s; %s", uri, ip, doc, e)
    return uid


@app.route("/<thing>", methods=["GET", "POST"])
def things(thing):
    ip = getIp(request)
    tbl = getTable(thing)
    if request.method == "GET":
        logging.info("GET /%s\t%s", thing, ip)
        todo, done = getList(tbl.all())
        return render("things.html", thing=thing, todo=todo, done=done, tbls=tbls)
    elif request.method == "POST":
        doc = genDoc(request.form, tbl)
        insertNewThing(doc, tbl, thing, ip)
        return redirect(f"/{thing}")


@app.route("/update/<thing>", methods=["POST"])
def update(thing):
    ip = getIp(request)
    db = getTable(thing)

    form = request.form
    uid = int(form["uid"])
    new = int(form["new"])
    old = int(form["old"])
    name = form["name"].strip()
    date = form["date"] if form["date"] else datetime.now().strftime("%Y-%m-%d")

    try:
        if old == new == 0:
            db.update({"date": date, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tChange Complete Date: %s", ip, thing, uid, date
            )
        elif old == new:
            db.update({"name": name}, doc_ids=[uid])
            logging.info("UPDATE\t%s - %s %s\tName Only: %s", ip, thing, uid, name)
        elif new <= 0:
            db.update(decrement("position"), (where("position") > old))
            db.update({"position": 0, "date": date, "name": name}, doc_ids=[uid])
            logging.info("UPDATE\t%s - %s %s\tFirst Complete: %s", ip, thing, uid, date)
        elif old > new:
            db.update(
                increment("position"),
                (where("position") >= new) & (where("position") < old),
            )
            db.update({"position": new, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tMove Down Up Rank\t%s -> %s",
                ip,
                thing,
                uid,
                old,
                new,
            )
        elif old < new:
            db.update(
                decrement("position"),
                (where("position") <= new) & (where("position") > old),
            )
            db.update({"position": new, "name": name}, doc_ids=[uid])
            logging.info(
                "UPDATE\t%s - %s %s\tMove Down In Rank\t%s -> %s",
                ip,
                thing,
                uid,
                old,
                new,
            )

    except Exception as e:
        logging.exception("UPDATE\t%s - %s %s: %s; %s", ip, thing, uid, form, e)

    return redirect(f"/{thing}")


@app.route("/move/<thing>", methods=["POST"])
def move(thing):
    ip = getIp(request)
    db = getTable(thing)

    form = request.form
    uid = int(form["uid"])
    old = int(form["old"])
    new = int(form["new"])
    pos = 0 if (old == new == 0) else (int(maxsize) if old == new else new)
    table = form["table"]
    newTable = getTable(table)
    newUid = -1

    if newTable != thing:
        val = db.get(doc_id=uid)
        val["position"] = pos
        newVal = genDoc(val, newTable)
        newUid = insertNewThing(newVal, newTable, "move/" + thing, ip)
        db.remove(doc_ids=[uid])
        if pos != 0:
            db.update(decrement("position"), (where("position") > old))

        logging.info("MOVE\t%s - %s %s -> %s %s", ip, thing, uid, table, newUid)

    return redirect(f"/{thing}")


@app.route("/delete/<thing>", methods=["POST"])
def delete(thing):
    ip = getIp(request)
    db = getTable(thing)

    form = request.form
    uid = int(form["uid"])
    name = form["name"].strip()
    val = db.get(doc_id=uid)

    if val["name"] == name:
        db.remove(doc_ids=[uid])
        log.info("DELETE\t%s - %s %s - %s", ip, thing, uid, name)

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
        default=5000,
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
        level=logging.INFO,
        handlers=handler_list,
    )

    app.run(host="0.0.0.0", port=port, debug=debug)
