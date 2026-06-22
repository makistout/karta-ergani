from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urljoin

import requests

from config import Config


class ErganiClient:
    def __init__(self, base_url: str | None = None, timeout: int = 120):
        raw = (base_url or Config.ERGANI_API_BASE_URL).rstrip("/") + "/"
        self.base_url = raw
        self.timeout = timeout

    def _url(self, *parts: str) -> str:
        path = "/".join(p.strip("/") for p in parts)
        return urljoin(self.base_url, path)

    def authenticate(self, username: str, password: str, usertype: str) -> requests.Response:
        return requests.post(
            self._url("Authentication"),
            json={"Username": username, "Password": password, "Usertype": usertype},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )

    def services_list(self, bearer: str) -> requests.Response:
        return requests.get(
            self._url("WebServices", "ServicesList"),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )

    def submissions_list(self, bearer: str) -> requests.Response:
        return requests.get(
            self._url("Lookup", "Submissions"),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )

    def execute_service(
        self,
        service_code: str,
        parameters: list[dict[str, Any]],
        bearer: str,
    ) -> requests.Response:
        return requests.post(
            self._url("WebServices", "ExecuteService"),
            json={"ServiceCode": service_code, "Parameters": parameters},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    def document_submit(
        self, submission_code: str, payload: dict[str, Any], bearer: str
    ) -> requests.Response:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=False)
        return requests.post(
            self._url("Documents", submission_code),
            data=raw.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=self.timeout,
        )
