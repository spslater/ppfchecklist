"""Database for the lists"""
import sqlite3
from abc import ABC, abstractmethod
from json import dumps, load
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

    @abstractmethod
    def insert(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def update(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def move(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def delete(self, form: dict):
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError


class DatabaseSqlite3(Database):
    def __init__(self, *args, **kwargs):
        _basedir = basedir or getenv("PPF_BASEDIR", ".")
        _filename = filename or getenv("PPF_DATABASE", "list.db")
        _fullpath = join(_basedir, filename)

        self.connection = sqlite3.connect(_fullpath)
        self.connection.row_factory = sqlite3.Row

        try:
            self._execute(
                """CREATE TABLE List (
                    position INTEGER,
                    date TEXT,
                    name TEXT NOT NULL,
                    progress INT,
                    completed INT,
                    dropped INT,
                    table INT,
                    FOREIGN KEY (talble) REFERENCES Table(id),
                )"""
            )
        except sqlite3.OperationalError as e:
            logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE Status (
                    name TEXT,
                    position INT,
                )"""
            )
        except sqlite3.OperationalError as e:
            logging.debug(e)

        try:
            self._execute(
                """CREATE TABLE Table (
                    name TEXT,
                    active INT,
                )"""
            )
        except sqlite3.OperationalError as e:
            logging.debug(e)

    def close(self):
        self.connection.close()

    def _cursor(self):
        return self.connection.cursor()

    def _execute(self, sql: str, parameters: tuple = None):
        cur = self._cursor()
        result = cur.execute(sql, parameters) if parameters else cur.execute(sql)
        db.commit()
        return result

    def _executemany(self, sql: str, parameters: tuple = None):
        db = self._cursor()
        result = (
            cur.executemany(sql, parameters) if parameters else cur.executemany(sql)
        )
        db.commit()
        return result

    def import_json(self, filename: str):
        with open(filename, "r") as fp:
            data = load(fp)

        for table, values in data.items():
            if table == "_default":
                continue

            entries = [
                (val.get("date"), val.get("position"), val.get("name"), table)
                for val in values.values()
            ]
            self._executemany("INSERT INTO ppfchecklist VALUES (?, ?, ?, ?)", entries)

    def tables(self):
        rows = self._execute("SELECT name FROM Table WHERE active = 1")
        return rows.fetchall()

    def info(self, table: str):
        self._get_table(table)
        todo = self._execute(
            """
            SELECT * FROM ppfchecklist
            WHERE checklist = ? AND position > 0
            ORDER BY position ASC
            """,
            (table,),
        ).fetchall()

        done = self._execute(
            """
            SELECT * FROM ppfchecklist
            WHERE checklist = ? AND position = 0
            ORDER BY date ASC
            """,
            (table,),
        ).fetchall()

        return todo, done
