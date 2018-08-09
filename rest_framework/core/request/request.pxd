# cython: language_level=3, boundscheck=False, wraparound=False, annotation_typing=False
import cython
# noinspection PyUnresolvedReferences
from rest_framework.core.headers.headers cimport Headers
# noinspection PyUnresolvedReferences
from rest_framework.core.protocol.cprotocol cimport Connection


cdef class StreamQueue:

    cdef:
        readonly object items
        object event
        bint waiting
        bint dirty
        bint finished

    cdef void put(self, bytes item)
    cdef void clear(self)
    cdef void end(self)


cdef class Stream:

    cdef:
        bint consumed
        StreamQueue queue
        Connection connection

    cdef void clear(self)


@cython.freelist(409600)
cdef class Request:

    cdef:
        readonly bytes url
        readonly bytes method
        readonly object parent
        readonly Connection protocol
        readonly Headers headers
        readonly Stream stream
        readonly dict context
        object _cookies
        object _parsed_url
        object _args
        dict _form
        str _body

    cpdef str client_ip(self)