# -*- coding: utf-8 -*-
import socket
import time
import os
import signal


def wait_server_available(host: str, port: int, timeout: int=10) -> None:
    """
    Wait until the server is available by trying to connect to the same.
    :param timeout: How many seconds wait before giving up.
    :param host: Host to connect to and wait until it goes offline.
    :param port: TCP port used to connect.
    :return:
    """
    sock = socket.socket()
    sock.settimeout(timeout)
    while timeout > 0:
        start_time = time.time()
        try:
            sock.connect((host, port))
            sock.close()
            return
        except OSError:
            time.sleep(0.001)
            timeout -= time.time() - start_time
    sock.close()
    raise TimeoutError(f'Server is taking too long to get online.')


def pause() -> None:
    """
    Pauses the process until a signed is received.
    Windows does not have a signal.pause() so we waste a few more cpu cycles.
    :return: None
    """
    if os.name == 'nt':
        while True:
            time.sleep(60)
    else:
        signal.pause()
