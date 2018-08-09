import asyncio

from .peewee import Database, ExceptionWrapper
from .peewee import sort_models_topologically, merge_dict
from .peewee import OperationalError
from .peewee import (
    RESULTS_NAIVE,
    RESULTS_TUPLES,
    RESULTS_DICTS,
    RESULTS_AGGREGATE_MODELS,
    RESULTS_MODELS,
)
from .peewee import SQL, R, Clause, fn, binary_construct
from .peewee import logger

from .context import Atomic, Transaction, SavePoint
from rest_framework.lib.orm.result import AsyncModelQueryResultWrapper
from rest_framework.lib.orm.result import AsyncTuplesQueryResultWrapper
from rest_framework.lib.orm.result import AsyncDictQueryResultWrapper
from rest_framework.lib.orm.result import AsyncNaiveQueryResultWrapper
from rest_framework.lib.orm.result import AsyncAggregateQueryResultWrapper


class AsyncConnection:

    def __init__(self, db, exception_wrapper, autocommit=None, autorollback=None):
        self.autocommit = autocommit
        self.autorollback = autorollback
        self.db = db
        self.acquirer = None
        self.conn = None
        self.context_stack = []
        self.transactions = []
        self.exception_wrapper = exception_wrapper  # TODO: remove

    def transaction_depth(self):
        return len(self.transactions)

    def push_transaction(self, transaction):
        self.transactions.append(transaction)

    def pop_transaction(self):
        return self.transactions.pop()

    async def execute_sql(self, sql, params=None, require_commit=True):
        logger.debug((sql, params))
        with self.exception_wrapper:
            cursor = await self.conn.cursor()
            try:
                await cursor.execute(sql, params or ())
            except Exception:
                if self.autorollback and self.autocommit:
                    await self.rollback()
                raise
            else:
                if require_commit and self.autocommit:
                    await self.commit()
            return cursor

    async def __aenter__(self):
        if self.acquirer is None:
            await self.db.connect()
            self.acquirer = self.db.pool.acquire()

        self.conn = await self.acquirer.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.acquirer.__aexit__(exc_type, exc_val, exc_tb)

    async def begin(self):
        pass

    def commit(self):
        with self.exception_wrapper:
            return self.conn.commit()

    def rollback(self):
        with self.exception_wrapper:
            return self.conn.rollback()

    def transaction(self, transaction_type=None):
        return Transaction(self, transaction_type)
    commit_on_success = property(transaction)

    def savepoint(self, sid=None):
        if not self.savepoints:
            raise NotImplementedError
        return SavePoint(self, sid)


class AsyncDatabase(Database):
    def _connect(self, database, **kwargs):
        raise NotImplementedError

    def begin(self):
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

    def rollback(self):
        raise NotImplementedError

    def get_cursor(self):
        raise NotImplementedError

    def get_tables(self, schema=None):
        raise NotImplementedError

    def get_indexes(self, table, schema=None):
        raise NotImplementedError

    def get_columns(self, table, schema=None):
        raise NotImplementedError

    def get_primary_keys(self, table, schema=None):
        raise NotImplementedError

    def get_foreign_keys(self, table, schema=None):
        raise NotImplementedError

    def sequence_exists(self, seq):
        raise NotImplementedError

    def transaction_depth(self):
        raise NotImplementedError

    def __init__(self, database, autocommit=True, fields=None, ops=None, autorollback=False,
                 loop=None, **connect_kwargs):
        self.connect_kwargs = {}
        self.closed = True
        self.init(database, **connect_kwargs)
        self.pool = None
        self.autocommit = autocommit
        self.autorollback = autorollback
        self.use_speedups = False

        self.field_overrides = merge_dict(self.field_overrides, fields or {})
        self.op_overrides = merge_dict(self.op_overrides, ops or {})
        self.exception_wrapper = ExceptionWrapper(self.exceptions)
        self._loop = loop
        # 用于保持连接
        self._auto_task = None

    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    def is_closed(self):
        return self.closed

    def get_conn(self):
        return AsyncConnection(
            db=self,
            autocommit=self.autocommit,
            autorollback=self.autorollback,
            exception_wrapper=self.exception_wrapper
        )

    async def close(self):
        if self.deferred:
            raise Exception('Error, database not properly initialized before closing connection')

        with self.exception_wrapper:
            if not self.closed and self.pool:
                await self.close_engine()
                self.pool.close()
                self.closed = True
                await self.pool.wait_closed()

    async def connect(self, safe=True):
        if self.deferred:
            raise OperationalError('Database has not been initialized')

        if not self.closed:
            if safe:
                return
            raise OperationalError('Connection already open')

        with self.exception_wrapper:
            self.pool = await self._connect(self.database, **self.connect_kwargs)
            self.closed = False
            # 启动自动链接
            await self.init_engine()

    async def init_engine(self):
        self._auto_task = self.loop.create_task(self.keep_engine())

    async def close_engine(self):
        self._auto_task.cancel()

    async def keep_engine(self):
        while 1:
            async with self.pool.acquire() as conn:
                await conn.ping()

            await asyncio.sleep(60)

    def get_result_wrapper(self, wrapper_type):
        if wrapper_type == RESULTS_NAIVE:
            return AsyncNaiveQueryResultWrapper
        elif wrapper_type == RESULTS_MODELS:
            return AsyncModelQueryResultWrapper
        elif wrapper_type == RESULTS_TUPLES:
            return AsyncTuplesQueryResultWrapper
        elif wrapper_type == RESULTS_DICTS:
            return AsyncDictQueryResultWrapper
        elif wrapper_type == RESULTS_AGGREGATE_MODELS:
            return AsyncAggregateQueryResultWrapper
        else:
            return AsyncNaiveQueryResultWrapper

    def atomic(self, transaction_type=None):
        return Atomic(self.get_conn(), transaction_type)

    def transaction(self, transaction_type=None):
        return Transaction(self.get_conn(), transaction_type)

    commit_on_success = property(transaction)

    async def create_table(self, model_class, safe=False):
        qc = self.compiler()
        async with self.get_conn() as conn:
            args = qc.create_table(model_class, safe)
            return await conn.execute_sql(*args)

    async def create_tables(self, models, safe=False):
        await create_model_tables(models, fail_silently=safe)

    async def create_index(self, model_class, fields, unique=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('Fields passed to "create_index" must be a list or tuple: "%s"' % fields)

        fobjs = [model_class._meta.fields[f] if isinstance(f, str) else f for f in fields]
        async with self.get_conn() as conn:
            args = qc.create_index(model_class, fobjs, unique)
            return await conn.execute_sql(*args)

    async def drop_index(self, model_class, fields, safe=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('Fields passed to "drop_index" must be a list or tuple: "%s"' % fields)

        fobjs = [model_class._meta.fields[f] if isinstance(f, str) else f for f in fields]
        async with self.get_conn() as conn:
            args = qc.drop_index(model_class, fobjs, safe)
            return await conn.execute_sql(*args)

    async def create_foreign_key(self, model_class, field, constraint=None):
        qc = self.compiler()
        async with self.get_conn() as conn:
            args = qc.create_foreign_key(model_class, field, constraint)
            return await conn.execute_sql(*args)

    async def create_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            async with self.get_conn() as conn:
                return await conn.execute_sql(*qc.create_sequence(seq))

    async def drop_table(self, model_class, fail_silently=False, cascade=False):
        qc = self.compiler()
        if cascade and not self.drop_cascade:
            raise ValueError('Database does not support DROP TABLE..CASCADE.')

        async with self.get_conn() as conn:
            args = qc.drop_table(model_class, fail_silently, cascade)
            return await conn.execute_sql(*args)

    async def drop_tables(self, models, safe=False, cascade=False):
        await drop_model_tables(models, fail_silently=safe, cascade=cascade)

    async def truncate_table(self, model_class, restart_identity=False, cascade=False):
        qc = self.compiler()
        async with self.get_conn() as conn:
            args = qc.truncate_table(model_class, restart_identity, cascade)
            return await conn.execute_sql(*args)

    async def truncate_tables(self, models, restart_identity=False,  cascade=False):
        for model in reversed(sort_models_topologically(models)):
            await model.truncate_table(restart_identity, cascade)

    async def drop_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            async with self.get_conn() as conn:
                return await conn.execute_sql(*qc.drop_sequence(seq))

    async def execute_sql(self, sql, params=None, require_commit=True):
        async with self.get_conn() as conn:
            return await conn.execute_sql(sql, params, require_commit=require_commit)

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(Clause(date_part, R('FROM'), date_field))

    def truncate_date(self, date_part, date_field):
        return fn.DATE_TRUNC(date_part, date_field)

    def default_insert_clause(self, model_class):
        return SQL('DEFAULT VALUES')

    def get_noop_sql(self):
        return 'SELECT 0 WHERE 0'

    def get_binary_type(self):
        return binary_construct


async def create_model_tables(models, **create_table_kwargs):
    for m in sort_models_topologically(models):
        await m.create_table(**create_table_kwargs)


async def drop_model_tables(models, **drop_table_kwargs):
    for m in reversed(sort_models_topologically(models)):
        await m.drop_table(**drop_table_kwargs)
