from datetime import datetime
from json import load
from os.path import join
from pprint import pformat
from sys import argv


class TableNotFoundError(Exception):
    def __init__(self, message):
        self.message = message


BASE_DIR = argv[1]

app = Flask(__name__, static_url_path="")
Bootstrap(app)
db = TinyDB(join(BASE_DIR, "list.db"))

with open(joint(BASE_DIR, "tables.json"), "r") as f:
    tbls = load(f)


def log(message):
    msg = f"{datetime.now().replace(microsecond=0).isoformat()}\t{message}\n"
    with open(OUTPUT, "a") as fp:
        fp.write(msg)
    if STDOUT:
        print(msg[:-1])


def getTable(thing):
    if thing not in tbls:
        log(f"[ERROR]\tAttempting to access table that does not exist: {thing}")
        raise TableNotFoundError(f"'{thing}' is not a valid table name.")
    return db.table(thing)


def getTableAll(thing):
    if thing not in tbls:
        log(f"[ERROR]\tAttempting to access table that does not exist: {thing}")
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

    pos = int(form["position"])
    position = pos if (0 < pos <= maxPos) else maxPos + 1
    name = form["name"]

    return {"position": position, "name": name}


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        "static",
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/", methods=["GET"])
def index():
    ip = str(request.remote_addr)

    log(f"[INFO]: GET /\t{ip}")

    things = []

    for tb in tbls:
        tb_all = getTableAll(tb)
        todo, done = getList(tb_all)
        things.append({"thing": tb, "todo": todo, "done": done})

    return render("index.html", things=things)


def postNewThing(doc, db, uri, ip):
    try:
        db.update(increment("position"), where("position") >= doc["position"])
        db.insert(doc)
        log(f"[INFO]: POST /{uri}\t{ip} - {str(doc)}")
    except Exception as e:
        log(f"[ERROR]: POST /{uri}\t{ip} - {str(doc)}")
        log(f"              \t{str(e)}")


@app.route("/<thing>", methods=["GET", "POST"])
def things(thing):
    ip = str(request.remote_addr)
    tbl = getTable(thing)
    if request.method == "GET":
        log(f"[INFO]: GET /{thing}\t{ip}")
        todo, done = getList(tbl.all())
        return render("things.html", thing=thing, todo=todo, done=done)
    elif request.method == "POST":
        doc = genDoc(request.form, tbl)
        postNewThing(doc, tbl, thing, ip)
        return redirect(f"/#{thing}")


@app.route("/update/<thing>", methods=["POST"])
def update(thing):
    ip = str(request.remote_addr)
    db = getTable(thing)

    form = request.form
    new = int(form["new"])
    old = int(form["old"])
    name = form["name"]

    try:
        if new <= 0:
            db.update(decrement("position"), (where("position") > old))
            db.update(
                {"position": new, "date": datetime.now().strftime("%Y-%m-%d")},
                where("name") == name,
            )
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
            log(f"[INFO]: UPDATE\t{ip} - '{name}': {str(old)} -> {str(new)}")
    except Exception as e:
        log(f"[ERROR]: UPDATE\t{ip} - '{name}': {str(old)} -> {str(new)}")
        log(f"               \t{str(e)}")

    return redirect(f"/#{thing}") if request.args.get("idx") else redirect(f"/{thing}")


if __name__ == "__main__":
    OUTPUT = argv[2] if (len(argv) >= 3) else join(BASE_DIR, "output.log")
    STDOUT = (len(argv) >= 4) and (argv[3] == "stdout")

    app.run(host="0.0.0.0", port=5432, debug=True)
