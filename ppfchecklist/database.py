"""Database for the lists"""
import logging
import sqlite3
from abc import ABC, abstractmethod
from more_itertools import partition
from json import dumps, load
from os import getenv
from os.path import join
from sys import maxsize
from typing import Union


class TableNotFoundError(Exception):
    """Custom exception when table in database isn't found"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Database(ABC):
    @abstractmethod
    def tables(self):
        raise NotImplementedError

    @abstractmethod
    def info(self, table: str, limit: int):
        raise NotImplementedError

    # @abstractmethod
    def delete(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def insert(self, form: dict):
        raise NotImplementedError

    # @abstractmethod
    def move(self, form: dict):
        raise NotImplementedError

    # @abstractmethod
    def update(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError


class DatabaseSqlite3(Database):
    def __init__(self, *args, **kwargs):
        _basedir = kwargs.get("basedir") or getenv("PPF_BASEDIR", ".")
        _filename = kwargs.get("filename") or getenv("PPF_DATABASE", "list.db")
        _fullpath = join(_basedir, _filename)

        self.connection = sqlite3.connect(_fullpath)
        self.connection.row_factory = sqlite3.Row

        self._init_database()

    def _init_database(self):
        try:
            self._execute(
                """CREATE TABLE Status (
                    name TEXT,
                    position INT,
                    orderByPosition INT
                )"""
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE List (
                    name TEXT,
                    position INT,
                    active INT
                )"""
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE ListStatus (
                    list INT,
                    status INT,
                    FOREIGN KEY (list) REFERENCES List(rowid),
                    FOREIGN KEY (status) REFERENCES Status(rowid),
                    UNIQUE (list, status)
                )"""
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

        # tables = self._execute("SELECT rowid FROM List")
        # statuses = self._execute("SELECT rowid FROM Status")
        # for table in tables:
        #     for status in statuses:
        #         try:
        #             self._execute(
        #                 "INSERT INTO ListStatus VALUES (?,?,?)",
        #                 (table["rowid"], status["rowid"], status["rowid"]),
        #             )
        #         except sqlite3.IntegrityError as e:
        #             pass

        try:
            self._execute(
                """CREATE TABLE Entry (
                    name TEXT NOT NULL,
                    position INTEGER,
                    date TEXT,
                    status INT,
                    list INT,
                    FOREIGN KEY (status) REFERENCES Status(rowid),
                    FOREIGN KEY (list) REFERENCES List(rowid),
                    UNIQUE(position,date,name,status,list)
                )"""
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

    def _drop_database(self):
        logging.debug("Dropping tables")
        self._execute("DROP TABLE Entry")
        self._execute("DROP TABLE ListStatus")
        self._execute("DROP TABLE List")
        self._execute("DROP TABLE Status")

    def close(self):
        self.connection.close()

    def _execute(self, sql: str, parameters: tuple = None, rowid: bool = False):
        if parameters is None:
            parameters = tuple()
        cur = self.connection.execute(sql, parameters)
        self.connection.commit()
        return (cur.lastrowid, cur.fetchall()) if rowid else cur.fetchall()

    def _executemany(self, sql: str, parameters: list[tuple] = None):
        if parameters is None:
            parameters = []
        result = self.connection.executemany(sql, parameters).fetchall()
        self.connection.commit()
        return result

    def _upload_oldstyle(self, data):
        tbl_pos = 1
        for table, values in data.items():
            if table == "_default":
                continue

            try:
                table_id, _ = self._execute(
                    "INSERT INTO List VALUES (?,?,?)",
                    (table, tbl_pos, True),
                    True,
                )
                tbl_pos += 1

                statuses = self._execute("SELECT rowid FROM Status")
                for status in statuses:
                    try:
                        self._execute(
                            "INSERT INTO ListStatus VALUES (?,?)",
                            (table_id, status["rowid"]),
                        )
                    except sqlite3.IntegrityError as e:
                        pass
            except sqlite3.IntegrityError:
                result = self._execute(
                    "SELECT rowid FROM List WHERE name = ?", (table,)
                )
                table_id = result[0]["rowid"]

            for value in values.values():
                name = value.get("name")
                position = value.get("position")
                date = value.get("date")
                status = None
                if position > 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Planned'"
                    )
                    status = result[0]["rowid"]
                    date = None
                elif position == 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Done'"
                    )
                    position = None
                    status = result[0]["rowid"]
                elif position < 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Dropped'"
                    )
                    position = None
                    status = result[0]["rowid"]
                try:
                    self._execute(
                        "INSERT INTO Entry VALUES (?, ?, ?, ?, ?)",
                        (name, position, date, status, table_id),
                    )
                except sqlite3.IntegrityError:
                    pass

    def _upload_newstyle(self, data):
        status = data["Status"]
        table = data["List"]
        listStatus = data["ListStatus"]
        entry = data["Entry"]

        status = [(s["rowid"], s["name"], s["rowid"], s["orderByPosition"]) for s in status]
        table = [(t["rowid"], t["name"], t["position"], t["active"]) for t in table]
        listStatus = [(l["rowid"], l["list"], l["status"]) for l in listStatus]
        entry = [(e["rowid"], e["name"], e["position"], e["date"], e["status"], e["list"]) for e in entry]

        self._executemany(
            """
            INSERT INTO Status(rowid, name, position, orderByPosition)
            VALUES (?,?,?,?)
            """,
            status,
        )

        self._executemany(
            """
            INSERT INTO List(rowid, name, position, active)
            VALUES (?,?,?,?)
            """,
            table
        )

        self._executemany(
            """
            INSERT INTO ListStatus(rowid, list, status)
            VALUES (?,?,?)
            """,
            listStatus
        )

        self._executemany(
            """
            INSERT INTO Entry(rowid, name, position, date, status, list)
            VALUES (?,?,?,?,?,?)
            """,
            entry
        )

    def upload(self, data):
        self._drop_database()
        logging.debug("Loading tables again")
        self._init_database()

        if data.get("sqlite", False):
            self._upload_newstyle(data)
        else:
            self._upload_oldstyle(data)

    def download(self):
        return {
            "sqlite": True,
            "Status": [dict(v) for v in self._execute("SELECT rowid, * FROM Status")],
            "List": [dict(v) for v in self._execute("SELECT rowid, * FROM List")],
            "ListStatus": [
                dict(v) for v in self._execute("SELECT rowid, * FROM ListStatus")
            ],
            "Entry": [dict(v) for v in self._execute("SELECT rowid, * FROM Entry")],
        }

    def is_table(self, name):
        return name in [table["name"] for table in self.tables()]


    def tables(self):
        return self._execute(
            """SELECT rowid, name
            FROM List
            WHERE active = 1
            ORDER BY position ASC"""
        )

    def table(self, table: Union[str, int]):
        sql = f"""SELECT rowid, name
        FROM List
        WHERE {"rowid" if isinstance(table, int) else "name"} = ?
        ORDER BY position ASC"""
        return self._execute(sql, (table,))[0]

    def status(self, table: str):
        return self._execute(
            """
            SELECT rowid, *
            FROM Status
            ORDER BY position
            """
        )

    def info(self, table: str, limit: int = None):
        results = []
        for status in self.status(table):
            result = self._execute(
                """
                SELECT
                    Entry.rowid,
                    Entry.name as name,
                    Entry.position as position,
                    Entry.date as date,
                    List.name as table_name,
                    List.rowid as table_id,
                    Status.name as status_name,
                    Status.rowid as status_id
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.name = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                ORDER BY
                    CASE
                        WHEN Status.orderByPosition == 1 THEN Entry.position
                        WHEN Status.orderByPosition == 0 THEN Entry.date
                    END ASC
                """,
                (table, status["rowid"]),
            )
            results.append(
                {
                    "status": status["name"],
                    "status_id": status["rowid"],
                    "orderByPosition": status["orderByPosition"],
                    "rows": result[limit*-1:] if (limit and not status["orderByPosition"]) else result,
                }
            )
        return results

    def _increment(self, table_id, status_id, position):
        self._execute(
            """
            UPDATE Entry
            SET position = position + 1
            WHERE rowid IN (
                SELECT Entry.rowid
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.rowid = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                WHERE Entry.position >= ?
            )
            """,
            (table_id, status_id, position),
        )

    def _decrement(self, table_id, status_id, position):
        self._execute(
            """
            UPDATE Entry
            SET position = position - 1
            WHERE rowid IN (
                SELECT Entry.rowid
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.rowid = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                WHERE Entry.position > ?
            )
            """,
            (table_id, status_id, position),
        )

    def _increment_range(self, table_id, status_id, greater, lesser):
        self._execute(
            """
            UPDATE Entry
            SET position = position + 1
            WHERE rowid IN (
                SELECT Entry.rowid
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.rowid = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                WHERE Entry.position >= ? AND Entry.position < ?
            )
            """,
            (table_id, status_id, greater, lesser),
        )

    def _decrement_range(self, table_id, status_id, lesser, greater):
        self._execute(
            """
            UPDATE Entry
            SET position = position - 1
            WHERE rowid IN (
                SELECT Entry.rowid
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.rowid = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                WHERE Entry.position <= ? AND Entry.position > ?
            )
            """,
            (table_id, status_id, lesser, greater),
        )

    def _calc_position(self, table_id, status_id, position):
        try:
            max_pos = self._execute(
                """
                SELECT MAX(Entry.position)
                FROM Entry
                JOIN List
                    ON List.rowid = Entry.list
                    AND List.rowid = ?
                JOIN Status
                    ON Status.rowid = Entry.status
                    AND Status.rowid = ?
                """,
                (table_id, status_id),
            )[0][0]
            if max_pos is None:
                max_pos = 0
        except IndexError:
            max_pos = 0
        pos = max(1, int(position if (position not in ("", "None", None)) else maxsize))
        res = pos if (pos <= max_pos) else (max_pos + 1)
        return res, max_pos

    def insert(self, form, table):
        status = [s for s in self.status(table) if s["rowid"] == int(form["status"])][0]
        status_id = status["rowid"]
        orderByPosition = status["orderByPosition"]
        table_id = self.table(table)["rowid"]
        name = form["name"].strip()
        date = None
        position = None

        if orderByPosition:
            position, max_pos = self._calc_position(
                table_id, status_id, form["position"]
            )
            if position <= max_pos:
                self._increment(table_id, status_id, position)
        else:
            if form.get("date", "") == "":
                date = datetime.now().strftime("%Y-%m-%d")
            else:
                date = form["date"]

        self._execute(
            """
            INSERT INTO Entry
            VALUES (?,?,?,?,?)
            """,
            (name, position, date, status_id, table_id),
        )

    def update(self, form, table):
        statuses = self.status(table)
        old_table = self.table(table)
        table_id = old_table["rowid"]

        rowid = int(form["rowid"])
        new_table = self.table(int(form["table"]))
        old_status = [s for s in statuses if s["rowid"] == int(form["old_status"])][0]
        new_status = [s for s in statuses if s["rowid"] == int(form["status"])][0]
        old_pos = int(form["old_pos"]) if form["old_pos"] not in ("None", "") else None
        new_pos = int(form["pos"]) if form["pos"] not in ("None", "") else None
        old_name = form["old_name"].strip()
        new_name = form["name"].strip()
        old_date = form["old_date"] or None
        new_date = form["date"] or None

        goto = new_table["name"]

        if (
            old_table == new_table
            and old_status == new_status
            and old_pos == new_pos
            and old_date == new_date
            and old_name == new_name
        ):
            return goto

        if old_table != new_table or old_status != new_status:
            self.insert(
                {
                    "position": new_pos,
                    "name": new_name,
                    "status": new_status["rowid"],
                    "date": new_date,
                },
                new_table["name"],
            )
            self.delete(
                {
                    "rowid": rowid,
                    "name": old_name,
                }
            )
            return goto

        status_id = new_status["rowid"]
        old_pos, _ = self._calc_position(table_id, status_id, old_pos)
        new_pos, max_pos = self._calc_position(table_id, status_id, new_pos)
        if new_pos > max_pos:
            new_pos = max_pos

        if old_pos > new_pos:
            self._increment_range(table_id, status_id, new_pos, old_pos)
        elif old_pos < new_pos:
            self._decrement_range(table_id, status_id, new_pos, old_pos)
        if old_pos != new_pos or old_name != new_name or old_date != new_date:
            self._execute(
                """
                UPDATE Entry
                SET position = ?, name = ?, date = ?
                WHERE rowid = ?
                """,
                (new_pos, new_name, new_date, rowid),
            )
        return goto

    def delete(self, form):
        rowid = int(form["rowid"])
        name = form["name"].strip()

        value = self._execute(
            """SELECT
                Entry.name as name,
                Entry.position as position,
                Status.orderByPosition as orderByPosition,
                List.rowid as table_id,
                Status.rowid as status_id
            FROM Entry
            JOIN List ON List.rowid = Entry.list
            JOIN Status ON Status.rowid = Entry.status
            WHERE Entry.rowid = ?
            """,
            (rowid,),
        )[0]

        if value["name"] == name:
            self._decrement(value["table_id"], value["status_id"], value["position"])
            self._execute("DELETE FROM Entry WHERE rowid = ?", (rowid,))

    def get_settings(self):
        statuses = self._execute("SELECT rowid, * FROM Status")
        tables = self._execute("SELECT rowid, * FROM List")
        enabledStatuses = self._execute(
            """
            SELECT
                Status.position as position,
                List.rowid as table_id,
                Status.rowid as status_id,
                Status.orderByPosition as orderByPosition
            FROM ListStatus
            JOIN List ON List.rowid = ListStatus.list
            JOIN Status ON Status.rowid = ListStatus.status
            """
        )

        statusList = []
        for status in statuses:
            statusList.append(dict(status))
        print(statusList)
        statusList = sorted(statusList, key=lambda i: i["position"])

        tableDict = {}
        for table in tables:
            table = dict(table)
            tableDict[table["rowid"]] = table

        tableList = sorted(tableDict.values(), key=lambda i: i["position"])

        return {
            "statuses": statusList,
            "tables": tableList,
        }

    def set_settings(self, form):
        statusOrder = [int(o) for o in form["statusOrder"].split(",")]
        tableOrder = [int(o) for o in form["tableOrder"].split(",")]
        numStatuses = int(form["numStatuses"])
        numTables = int(form["numTables"])

        statuses = []
        for idx, og in enumerate(statusOrder):
            pre = f"status_{og}"
            if form[f"{pre}_name"]:
                statuses.append(
                    {
                        "rowid": og if og <= numStatuses else 0,
                        "name": form[f"{pre}_name"],
                        "orderByPosition": form.get(f"{pre}_orderByPosition") == "on",
                        "og_name": form.get(f"{pre}_og_name", ""),
                        "og_position": int(form.get(f"{pre}_og_position", 0)),
                    }
                )

        for idx, status in enumerate(statuses):
            status["position"] = idx + 1

        statuses = [
            s
            for s in statuses
            if s["name"] != s["og_name"] or s["position"] != s["og_position"]
        ]

        statusUpdate, statusInsert = partition(lambda i: i["rowid"] == 0, statuses)
        statusUpdate = [(s["name"], s["position"], s["rowid"]) for s in statusUpdate]
        statusInsert = [
            (s["name"], s["position"], s["orderByPosition"]) for s in statusInsert
        ]

        print(statusUpdate)
        if statusUpdate:
            self._executemany(
                """
                UPDATE Status
                SET name = ?, position = ?
                WHERE rowid = ?
                """,
                statusUpdate,
            )

        print(statusInsert)
        if statusInsert:
            self._executemany(
                """
                INSERT INTO Status(name, position, orderByPosition)
                VALUES (?, ?, ?)
                """,
                statusInsert,
            )

        tables = []
        for idx, og in enumerate(tableOrder):
            pre = f"table_{og}"

            if form[f"{pre}_name"]:
                tables.append(
                    {
                        "rowid": og if og <= numTables else 0,
                        "name": form[f"{pre}_name"],
                        "active": form.get(f"{pre}_active") == "on",
                        "og_name": form.get(f"{pre}_name", ""),
                        "og_position": int(form.get(f"{pre}_position", 0)),
                    }
                )

        for idx, table in enumerate(tables):
            table["position"] = idx + 1

        tables = [
            t
            for t in tables
            if t["name"] != t["og_name"] or t["position"] != t["og_position"]
        ]

        tableUpdate, tableInsert = partition(lambda i: i["rowid"] == 0, tables)
        tableUpdate = [
            (t["name"], t["position"], t["active"], t["rowid"]) for t in tableUpdate
        ]
        tableInsert = [(t["name"], t["position"], t["active"]) for t in tableInsert]

        print(tableUpdate)
        if tableUpdate:
            self._executemany(
                """
                UPDATE List
                SET name = ?, position = ?, active = ?
                WHERE rowid = ?
                """,
                tableUpdate,
            )

        print(tableInsert)
        if tableInsert:
            self._executemany(
                """
                INSERT INTO List(name, position, active)
                VALUES (?, ?, ?)
                """,
                tableInsert,
            )

        return {
            "statuses": {
                "update": statusUpdate,
                "insert": statusInsert,
            },
            "tables": {
                "update": tableUpdate,
                "insert": tableInsert,
            },
        }

