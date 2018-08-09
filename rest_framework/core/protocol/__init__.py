from rest_framework.core.protocol.definitions import *
from rest_framework.core.protocol import cprotocol

locals()['Connection'] = cprotocol.Connection
locals()['update_current_time'] = cprotocol.update_current_time
