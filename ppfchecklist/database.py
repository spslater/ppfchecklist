"""Database for the lists"""
import sqlite3
import logging
from abc import ABC, abstractmethod
from json import dumps, load
from os import getenv
from os.path import join


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

    # @abstractmethod
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
                    position INT,
                    orderByPosition INT
                )"""
            )
            self._executemany(
                "INSERT INTO Status VALUES (?, ?, ?)",
                [
                    ("todo", 2, True),
                    ("done", 3, False),
                    ("drop", 4, False),
                    ("prog", 1, True),
                ],
            )
        except sqlite3.OperationalError as e:
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
            logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE Entry (
                    position INTEGER,
                    date TEXT,
                    name TEXT NOT NULL,
                    status INT,
                    list INT,
                    FOREIGN KEY (status) REFERENCES Status(rowid),
                    FOREIGN KEY (list) REFERENCES List(rowid),
                    UNIQUE(position,date,name,status,list)
                )"""
            )
        except sqlite3.OperationalError as e:
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
        self._execute("DROP TABLE Entry")
        self._execute("DROP TABLE List")
        self._execute("DROP TABLE Status")
        self._init_database()

        with open(filename, "r") as fp:
            data = load(fp)

        tbl_pos = 1
        for table, values in data.items():
            if table == "_default":
                continue

            try:
                table_id, _ = self._execute(
                    "INSERT INTO List VALUES (?,?,?)", (table, tbl_pos, True), True
                )
                tbl_pos += 1
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
                        "SELECT rowid FROM Status WHERE name = 'todo'"
                    )
                    status = result[0]["rowid"]
                elif position == 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'done'"
                    )
                    status = result[0]["rowid"]
                elif position < 0:
                    result = self._execute(
                        "SELECT rowid FROM Status WHERE name = 'drop'"
                    )
                    status = result[0]["rowid"]
                try:
                    self._execute(
                        "INSERT INTO Entry VALUES (?, ?, ?, ?, ?)",
                        (position, date, name, status, table_id),
                    )
                except sqlite3.IntegrityError:
                    pass

    def dump(self):
        return (
            [tuple(v) for v in self._execute("SELECT rowid, * FROM Status")],
            [tuple(v) for v in self._execute("SELECT rowid, * FROM List")],
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

    def info(self, table: str):
        todo = self._execute(
            """
            SELECT Entry.rowid, * FROM Entry
            JOIN List
                ON List.rowid = Entry.list
                AND List.name = ?
            JOIN Status
                ON Status.rowid = Entry.status
                AND Status.name = 'todo'
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
                AND Status.name = 'done'
            ORDER BY
                CASE 
                    WHEN Status.orderByPosition == 1 THEN Entry.position
                    WHEN Status.orderByPosition == 0 THEN Entry.date 
                END ASC
            """,
            (table,),
        )

        return todo, done
