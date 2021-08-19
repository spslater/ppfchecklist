"""Database for the lists"""
import sqlite3
import logging
from abc import ABC, abstractmethod
from json import dumps, load
from os import getenv
from os.path import join
from sys import maxsize


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

    def import_json(self, filename: str):
        logging.debug("Dropping tables")
        self._execute("DROP TABLE Entry")
        self._execute("DROP TABLE ListStatus")
        self._execute("DROP TABLE List")
        self._execute("DROP TABLE Status")
        logging.debug("Loading tables again")
        self._init_database()

        with open(filename, "r") as fp:
            data = load(fp)

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
                position = value.get("position")
                date = value.get("date")
                name = value.get("name")
                status = None
                if position > 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Planned'"
                    )
                    status = result[0]["rowid"]
                elif position == 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Done'"
                    )
                    status = result[0]["rowid"]
                elif position < 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'Dropped'"
                    )
                    status = result[0]["rowid"]
                try:
                    self._execute(
                        "INSERT INTO Entry VALUES (?, ?, ?, ?, ?)",
                        (name, position, date, status, table_id),
                    )
                except sqlite3.IntegrityError:
                    pass

    def dump(self):
        return (
            [tuple(v) for v in self._execute("SELECT rowid, * FROM Status")],
            [tuple(v) for v in self._execute("SELECT rowid, * FROM List")],
            [tuple(v) for v in self._execute("SELECT rowid, * FROM ListStatus")],
            [tuple(v) for v in self._execute("SELECT rowid, * FROM Entry")],
        )

    def tables(self):
        rows = self._execute(
            """SELECT name
            FROM List
            WHERE active = 1
            ORDER BY position ASC"""
        )
        return [r["name"] for r in rows]

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
        todo = self._execute(
            """
            SELECT Entry.rowid, * FROM Entry
            JOIN List
                ON List.rowid = Entry.list
                AND List.name = ?
            JOIN Status
                ON Status.rowid = Entry.status
                AND Status.name = 'Planned'
            ORDER BY
                CASE 
                    WHEN Status.orderByPosition == 1 THEN Entry.position
                    WHEN Status.orderByPosition == 0 THEN Entry.date
                END ASC
            """,
            (table,),
        )

        done = self._execute(
            """
            SELECT Entry.rowid, * FROM Entry
            JOIN List
                ON List.rowid = Entry.list
                AND List.name = ?
            JOIN Status
                ON Status.rowid = Entry.status
                AND Status.name = 'Done'
            ORDER BY
                CASE 
                    WHEN Status.orderByPosition == 1 THEN Entry.position
                    WHEN Status.orderByPosition == 0 THEN Entry.date 
                END ASC
            """,
            (table,),
        )

        return todo, done

    def _incrament(self, table_id, status_id, position):
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

    def _decrament(self, table_id, status_id, position):
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
                WHERE Entry.position <= ?
            )
            """,
            (table_id, status_id, position),
        )

    def insert(self, form, table):
        status = [s for s in self.status(table) if s["rowid"] == int(form["status"])][0]
        status_id = status["rowid"]
        orderByPosition = status["orderByPosition"]
        table_id = self._execute(
                "SELECT rowid FROM List WHERE name = ?",
                (table,)
            )[0]["rowid"]
        name = form["name"].strip()
        date = None
        position = None

        if orderByPosition:
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
            except IndexError:
                max_pos = 0
            pos = max(1, int(form["position"] if form["position"] != "" else maxsize))
            position = pos if (pos <= max_pos) else (max_pos + 1)

            if position <= max_pos:
                self._incrament(table_id, status_id, position)
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
            (name, position, date, status_id, table_id)
        )
