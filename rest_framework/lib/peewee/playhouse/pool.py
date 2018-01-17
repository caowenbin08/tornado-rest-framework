import heapq
import logging
import threading
import time

try:
    from Queue import Queue
except ImportError:
    from queue import Queue

try:
    from psycopg2 import extensions as pg_extensions
except ImportError:
    pg_extensions = None

from ..peewee import MySQLDatabase
from ..peewee import PostgresqlDatabase

logger = logging.getLogger('peewee.pool')


def make_int(val):
    if val is not None and not isinstance(val, (int, float)):
        return int(val)
    return val


class MaxConnectionsExceeded(ValueError): pass


class PooledDatabase(object):
    def __init__(self, database, max_connections=20, stale_timeout=None, timeout=None, **kwargs):
        self.max_connections = make_int(max_connections)
        self.stale_timeout = make_int(stale_timeout)
        self.timeout = make_int(timeout)
        if self.timeout == 0:
            self.timeout = float('inf')
        self._closed = set()
        self._connections = []
        self._in_use = {}
        self.conn_key = id

        if self.timeout:
            self._event = threading.Event()
            self._ready_queue = Queue()

        super(PooledDatabase, self).__init__(database, **kwargs)

    def init(self, database, max_connections=None, stale_timeout=None, timeout=None,
             **connect_kwargs):
        super(PooledDatabase, self).init(database, **connect_kwargs)
        if max_connections is not None:
            self.max_connections = make_int(max_connections)
        if stale_timeout is not None:
            self.stale_timeout = make_int(stale_timeout)
        if timeout is not None:
            self.timeout = make_int(timeout)
            if self.timeout == 0:
                self.timeout = float('inf')

    def connect(self):
        if self.timeout:
            start = time.time()
            while start + self.timeout > time.time():
                try:
                    super(PooledDatabase, self).connect()
                except MaxConnectionsExceeded:
                    time.sleep(0.1)
                else:
                    return
            raise MaxConnectionsExceeded('Max connections exceeded, timed out '
                                         'attempting to connect.')
        else:
            super(PooledDatabase, self).connect()

    def _connect(self, *args, **kwargs):
        while True:
            try:
                # Remove the oldest connection from the heap.
                ts, conn = heapq.heappop(self._connections)
                key = self.conn_key(conn)
            except IndexError:
                ts = conn = None
                logger.debug('No connection available in pool.')
                break
            else:
                if self._is_closed(key, conn):
                    # This connecton was closed, but since it was not stale
                    # it got added back to the queue of available conns. We
                    # then closed it and marked it as explicitly closed, so
                    # it's safe to throw it away now.
                    # (Because Database.close() calls Database._close()).
                    logger.debug('Connection %s was closed.', key)
                    ts = conn = None
                    self._closed.discard(key)
                elif self.stale_timeout and self._is_stale(ts):
                    # If we are attempting to check out a stale connection,
                    # then close it. We don't need to mark it in the "closed"
                    # set, because it is not in the list of available conns
                    # anymore.
                    logger.debug('Connection %s was stale, closing.', key)
                    self._close(conn, True)
                    self._closed.discard(key)
                    ts = conn = None
                else:
                    break

        if conn is None:
            if self.max_connections and (
                        len(self._in_use) >= self.max_connections):
                raise MaxConnectionsExceeded('Exceeded maximum connections.')
            conn = super(PooledDatabase, self)._connect(*args, **kwargs)
            ts = time.time()
            key = self.conn_key(conn)
            logger.debug('Created new connection %s.', key)

        self._in_use[key] = ts
        return conn

    def _is_stale(self, timestamp):
        # Called on check-out and check-in to ensure the connection has
        # not outlived the stale timeout.
        return (time.time() - timestamp) > self.stale_timeout

    def _is_closed(self, key, conn):
        return key in self._closed

    def _can_reuse(self, conn):
        # Called on check-in to make sure the connection can be re-used.
        return True

    def _close(self, conn, close_conn=False):
        key = self.conn_key(conn)
        if close_conn:
            self._closed.add(key)
            super(PooledDatabase, self)._close(conn)
        elif key in self._in_use:
            ts = self._in_use[key]
            del self._in_use[key]
            if self.stale_timeout and self._is_stale(ts):
                logger.debug('Closing stale connection %s.', key)
                super(PooledDatabase, self)._close(conn)
            elif self._can_reuse(conn):
                logger.debug('Returning %s to pool.', key)
                heapq.heappush(self._connections, (ts, conn))
            else:
                logger.debug('Closed %s.', key)

    def manual_close(self):
        """
        Close the underlying connection without returning it to the pool.
        """
        conn = self.get_conn()
        self.close()
        if not self._is_closed(self.conn_key(conn), conn):
            self._close(conn, close_conn=True)

    def close_all(self):
        """
        Close all connections managed by the pool.
        """
        for _, conn in self._connections:
            self._close(conn, close_conn=True)


class PooledMySQLDatabase(PooledDatabase, MySQLDatabase):
    def _is_closed(self, key, conn):
        is_closed = super(PooledMySQLDatabase, self)._is_closed(key, conn)
        if not is_closed:
            try:
                conn.ping(False)
            except:
                is_closed = True
        return is_closed


class _PooledPostgresqlDatabase(PooledDatabase):
    def _is_closed(self, key, conn):
        closed = super(_PooledPostgresqlDatabase, self)._is_closed(key, conn)
        if not closed:
            closed = bool(conn.closed)
        return closed

    def _can_reuse(self, conn):
        txn_status = conn.get_transaction_status()
        # Do not return connection in an error state, as subsequent queries
        # will all fail.
        if txn_status == pg_extensions.TRANSACTION_STATUS_INERROR:
            conn.reset()
        return True


class PooledPostgresqlDatabase(_PooledPostgresqlDatabase, PostgresqlDatabase):
    pass


try:
    from ..playhouse.postgres_ext import PostgresqlExtDatabase


    class PooledPostgresqlExtDatabase(_PooledPostgresqlDatabase, PostgresqlExtDatabase):
        pass
except ImportError:
    pass
