"""Database for the lists"""
import sqlite3
import logging
from abc import ABC, abstractmethod
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
    def info(self, table: str):
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
                    name TEXT UNIQUE,
                    orderByPosition INT
                )"""
            )
            self._executemany(
                "INSERT INTO Status VALUES (?, ?)",
                [
                    ("In Progress", True),
                    ("Planned", True),
                    ("Done", False),
                    ("Dropped", False),
                ],
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE List (
                    name TEXT UNIQUE,
                    position INT UNIQUE,
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
                    position INT,
                    FOREIGN KEY (list) REFERENCES List(rowid),
                    FOREIGN KEY (status) REFERENCES Status(rowid),
                    UNIQUE (list, status)
                )"""
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                logging.debug(e)

        tables = self._execute("SELECT rowid FROM List")
        statuses = self._execute("SELECT rowid FROM Status")
        for table in tables:
            for status in statuses:
                try:
                    self._execute(
                        "INSERT INTO ListStatus VALUES (?,?,?)",
                        (table["rowid"], status["rowid"], status["rowid"]),
                    )
                except sqlite3.IntegrityError as e:
                    pass

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

    def close(self):
        self.connection.close()

    def _cursor(self):
        return self.connection.cursor()

    def _execute(self, sql: str, parameters: tuple = None, rowid: bool = False):
        cur = self._cursor()
        cur.execute(sql, parameters) if parameters else cur.execute(sql)
        result = (cur.lastrowid, cur.fetchall()) if rowid else cur.fetchall()
        self.connection.commit()
        return result

    def _executemany(self, sql: str, parameters: tuple = None):
        cur = self._cursor()
        cur.executemany(sql, parameters) if parameters else cur.executemany(sql)
        result = cur.fetchall()
        self.connection.commit()
        return result

    def upload(self, data):
        logging.debug("Dropping tables")
        self._execute("DROP TABLE Entry")
        self._execute("DROP TABLE ListStatus")
        self._execute("DROP TABLE List")
        self._execute("DROP TABLE Status")
        logging.debug("Loading tables again")
        self._init_database()

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
                            "INSERT INTO ListStatus VALUES (?,?,?)",
                            (table_id, status["rowid"], status["rowid"]),
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

    def download(self):
        return {
            "Status": [dict(v) for v in self._execute("SELECT rowid, * FROM Status")],
            "List": [dict(v) for v in self._execute("SELECT rowid, * FROM List")],
            "ListStatus": [dict(v) for v in self._execute("SELECT rowid, * FROM ListStatus")],
            "Entry": [dict(v) for v in self._execute("SELECT rowid, * FROM Entry")],
        }

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
        return self._execute(
            sql,
            (table,)
        )[0]

    def status(self, table: str):
        return self._execute(
            """
            SELECT 
                Status.rowid as rowid,
                Status.name as name,
                ListStatus.position as position,
                Status.orderByPosition as orderByPosition
            FROM Status
            JOIN ListStatus
                ON Status.rowid = ListStatus.status
            JOIN List 
                ON List.rowid = ListStatus.list
                AND List.name = ?
            ORDER BY position
            """,
            (table,),
        )

    def info(self, table: str):
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
                    "rows": result,
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
            position, max_pos = self._calc_position(table_id, status_id, form["position"])
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
            self.insert({
                "position": new_pos,
                "name": new_name,
                "status": new_status["rowid"],
                "date": new_date
            }, new_table["name"])
            self.delete({
                    "rowid": rowid,
                    "name": old_name,
            })
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
        if (
            old_pos != new_pos
            or old_name != new_name
            or old_date != new_date
        ):
            self._execute(
                """
                UPDATE Entry
                SET position = ?, name = ?, date = ?
                WHERE rowid = ?
                """,
                (new_pos, new_name, new_date, rowid)
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
