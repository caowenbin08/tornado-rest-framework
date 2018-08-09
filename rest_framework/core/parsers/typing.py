class URL:

    def __init__(self, schema: bytes, host: bytes, port, path: bytes,
                 query: bytes, fragment: bytes, userinfo: bytes):
        self.schema = schema if schema is not None else b"http"
        self.host = host if host is not None else b"127.0.0.1"
        self.port = port if port else 80
        self.path = path if path is not None else b""
        self.query = query if query is not None else b""
        self.fragment = fragment if fragment is not None else b""
        self.userinfo = userinfo if userinfo is not None else b""
        self.netloc = b"%b://%b:%d" % (self.schema, self.host, self.port)

    def __repr__(self):
        return ('<URL schema: {!r}, host: {!r}, port: {!r}, path: {!r}, '
                'query: {!r}, fragment: {!r}, userinfo: {!r}>'
                .format(self.schema, self.host, self.port, self.path, self.query, self.fragment, self.userinfo))
