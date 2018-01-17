# -*- coding: utf-8 -*-
try:
    import aiopg
except ImportError:
    aiopg = None

from ..peewee import psycopg2, ImproperlyConfigured
from ..peewee import IndexMetadata, ColumnMetadata, ForeignKeyMetadata
from ..playhouse.postgres_ext import PostgresqlExtDatabase
from ..playhouse.db_url import register_database
from .database import AioDatabase


class AioPostgreSQLDatabase(AioDatabase, PostgresqlExtDatabase):
    async def _connect(self, database, loop=None, **kwargs):
        if aiopg is None:
            raise ImproperlyConfigured('aiopg must be installed.')

        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed.')

        conn_kwargs = {}
        conn_kwargs.update(kwargs)
        ud = " ".join([str(i) + "=" + str(j) for i, j in conn_kwargs.items()])
        dsn = 'dbname={} '.format(database) + ud
        return await aiopg.create_pool(dsn)

    async def _close(self, conn):
        self._conn_pool.release(conn)

    async def cancel(self, con, timeout=None):
        con.cancel(timeout=timeout)

    async def execute_sql(self, sql, params=None, require_commit=True):
        with self.exception_wrapper:
            conn = await self.get_conn()
            try:
                cursor = await conn.cursor()
                await cursor.execute(sql, params or ())
                # TODO: MIGHT CLOSE THE CURSOR FROM RESULT WRAPPER...
            except Exception:
                await self.cancel(conn)
                raise

            finally:
                await self._close(conn)

        return cursor

    async def get_tables(self, schema=None):
        cursor = await self.execute_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        return [row for row, in await cursor.fetchall()]

    async def get_indexes(self, table, schema=None):
        cursor = await self.execute_sql(
            "SELECT * FROM pg_indexes WHERE tablename = '{}';".format(table))
        unique = set()
        indexes = {}
        for row in cursor.fetchall():
            if not row[1]:
                unique.add(row[2])
            indexes.setdefault(row[2], [])
            indexes[row[2]].append(row[4])
        return [IndexMetadata(name, None, indexes[name], name in unique, table)
                for name in indexes]

    async def get_columns(self, table, schema=None):
        sql = """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = DATABASE()"""
        cursor = await self.execute_sql(sql, (table,))
        pks = set(self.get_primary_keys(table))
        return [ColumnMetadata(name, dt, null == 'YES', name in pks, table)
                for name, null, dt in await cursor.fetchall()]

    async def get_primary_keys(self, table, schema=None):
        cursor = await self.execute_sql('SHOW INDEX FROM `%s`' % table)
        return [row[4] for row in await cursor.fetchall()
                if row[2] == 'PRIMARY']

    async def get_foreign_keys(self, table, schema=None):
        query = """
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_name = %s
                AND table_schema = DATABASE()
                AND referenced_table_name IS NOT NULL
                AND referenced_column_name IS NOT NULL"""
        cursor = await self.execute_sql(query, (table,))
        return [
            ForeignKeyMetadata(column, dest_table, dest_column, table)
            for column, dest_table, dest_column in await cursor.fetchall()]

    async def commit(self):
        raise psycopg2.ProgrammingError

    async def rollback(self):
        raise psycopg2.ProgrammingError

    # TODO
    def get_binary_type(self):
        return psycopg2.Binary

register_database(AioPostgreSQLDatabase, 'postgres+async', 'postgresql+async')
register_database(AioPostgreSQLDatabase, 'postgres+pool+async', 'postgresql+pool+async')
