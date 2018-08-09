from rest_framework.core.client.retries import RetryStrategy


class ClientDefaults:
    TIMEOUT = 30
    HEADERS = {
        'User-Agent': 'XTAPIRF1.0',
        'Accept': '*/*',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, deflate'
    }
    RETRY_STRATEGY = RetryStrategy()
