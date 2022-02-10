# capabilities
import os

from zmq import Context

APP_ID = os.environ.get("SKYNET_APPLICATION_ID", None)
if APP_ID is None:
    print("WARNING: The environment variable 'SKYNET_APPLICATION_ID' is not set. Assuming "
          "developer mode.")
    APP_ID = "__unknown__"

# sockets
SKYNET_SOCKETS_DIR = "/tmp/skynet/sockets"

# skynet (commons)
SKYNET_HTTP_HEADER = lambda n: f"x-skynet-{n}"

ZMQ_CONTEXT = Context()
