import logging
from datetime import datetime
from json import load
from os.path import join
from sys import argv, maxsize


class TableNotFoundError(Exception):
    def __init__(self, message):
        self.message = message


BASE_DIR = argv[1]

app = Flask(__name__, static_url_path="")
Bootstrap(app)
db = TinyDB(join(BASE_DIR, "list.db"))

with open(joint(BASE_DIR, "tables.json"), "r") as f:
    tbls = load(f)


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
        [a for a in all_items if a["position"] > 0],
        key=lambda i: i["position"],
    )
    done = sorted([a for a in all_items if a["position"] == 0], key=lambda i: i["date"])
    return todo, done


def genDoc(form, db):
    maxPos = max([int(a["position"]) for a in db]) if len(db) else 0

    pos = max(0, int(form["position"] if form["position"] != "" else maxsize))
    position = pos if (pos <= maxPos) else (maxPos + 1)
    name = form["name"].strip()
    date = form["date"]

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
    ip = str(request.headers["X-Forwarded-For"])
    logging.info("GET /\t%s", ip)

    things = []

    for tb in tbls:
        tb_all = getTableAll(tb)
        todo, done = getList(tb_all)
        things.append({"thing": tb, "todo": todo, "done": done})

    return render("index.html", things=things)


def postNewThing(doc, db, uri, ip):
    try:
        if doc["position"] > 0:
            db.update(increment("position"), where("position") >= doc["position"])
            doc.pop("date", None)
            db.insert(doc)
        elif doc["position"] <= 0:
            doc["position"] = 0
            if not doc["date"]:
                doc["date"] = datetime.now().strftime("%Y-%m-%d")
            db.insert(doc)
        logging.info("POST /%s\t%s - %s", uri, ip, doc)
    except Exception as e:
        logging.exception("POST /%s\t%s - %s: %s", uri, ip, doc, e)


@app.route("/<thing>", methods=["GET", "POST"])
def things(thing):
    ip = str(request.headers["X-Forwarded-For"])
    tbl = getTable(thing)
    if request.method == "GET":
        logging.info("GET /" + thing + "\t" + ip)
        todo, done = getList(tbl.all())
        return render("things.html", thing=thing, todo=todo, done=done)
    elif request.method == "POST":
        doc = genDoc(request.form, tbl)
        postNewThing(doc, tbl, thing, ip)
        return redirect("/" + thing)


@app.route("/update/<thing>", methods=["POST"])
def update(thing):
    ip = str(request.headers["X-Forwarded-For"])
    db = getTable(thing)

    form = request.form
    new = int(form["new"])
    old = int(form["old"])
    name = form["name"]
    date = form["date"] if form["date"] else datetime.now().strftime("%Y-%m-%d")

    try:
        if old == new == 0:
            db.update({"date": date}, where("name") == name)
        elif new <= 0:
            db.update(decrement("position"), (where("position") > old))
            db.update({"position": 0, "date": date}, where("name") == name)
        elif old > new:
            db.update(
                increment("position"),
                (where("position") >= new) & (where("position") < old),
            )
            db.update({"position": new}, where("name") == name)
        elif old < new:
            db.update(
                decrement("position"),
                (where("position") <= new) & (where("position") > old),
            )
            db.update({"position": new}, where("name") == name)

        if old != new:
            logging.info("UPDATE\t%s - '%s': %s -> %s", ip, name, old, new)
    except Exception as e:
        logging.exception("UPDATE\t%s - '%s': %s -> %s; %s", ip, name, old, new, e)

    return redirect(f"/#{thing}") if request.args.get("idx") else redirect(f"/{thing}")


if __name__ == "__main__":
    OUTPUT = argv[2] if (len(argv) >= 3) else join(BASE_DIR, "output.log")

    logging.basicConfig(
        format="%(asctime)s\t[%(levelname)s]\t%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
        filename=OUTPUT,
    )

    app.run(host="0.0.0.0", port=5432, debug=True)
