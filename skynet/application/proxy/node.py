import os
from typing import Dict, Optional, Union, List

import requests
from requests import Response

from skynet.application.constants import SKYNET_SOCKETS_DIR, APP_ID
from skynet.application.logging import salogger
from skynet.application.utils.rest import UnixSocketHTTPEndpoint
from skynet.application.constants import SKYNET_HTTP_HEADER
from skynet.application.utils.misc import print_exc


JSONObject = Union[Dict, List]


class Node:
    api: UnixSocketHTTPEndpoint = UnixSocketHTTPEndpoint(
        socket_fpath=os.path.join(SKYNET_SOCKETS_DIR, "node.sock"),
        host="node"
    )

    @classmethod
    def call(cls, resource: str, data: Optional[dict] = None, **kwargs) -> Optional[JSONObject]:
        url = f"http://node/{resource.lstrip('/')}"
        # add application id to headers
        headers = kwargs.get("headers", {})
        headers[SKYNET_HTTP_HEADER("application-id")] = APP_ID
        # call node
        try:
            salogger.debug(f"POST: {url}")
            response: Response = cls.api.post(
                url=f"http://node/{resource.lstrip('/')}",
                json=data or {},
                timeout=10,
                headers=headers,
                **kwargs
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            print_exc(e, salogger)
            return None
        # only status 200 is considered a success
        if response.status_code != 200:
            # noinspection PyBroadException
            try:
                error_msg = response.json()["message"]
            except BaseException:
                error_msg = str(response.text)
            error_msg = f"The server replied with error [{response.status_code}]: {error_msg}"
            salogger.error(error_msg)
            return None
        # ---
        return response.json()
