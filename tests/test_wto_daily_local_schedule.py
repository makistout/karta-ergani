import unittest
from unittest.mock import patch

from flask import Flask, session

from app.routes_wto_daily import (
    _ergani_authorization_denied,
    _persist_local_schedule_after_wto_daily,
    _submit_wto_daily_with_auth_retry,
    record_wto_daily_schedule_audit,
)


class _FakeResp:
    def __init__(self, *, status_code=200, ok=False, text="", payload=None):
        self.status_code = status_code
        self.ok = ok
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def document_submit(self, code, payload, bearer):
        self.calls.append((code, payload, bearer))
        return self.responses.pop(0)


class WtoDailyLocalScheduleTests(unittest.TestCase):
    def _payload(self):
        return {"WTOS": {"WTO": [{"f_from_date": "2026-07-02"}]}}

    def test_persist_local_schedule_after_wto_daily_updates_hours(self):
        ctx = {"employer_afm": " 123456789 ", "branch_aa": "2"}
        body = {
            "schedule_type": "ΕΡΓ",
            "hour_from": "10:00",
            "hour_to": "18:00",
        }

        with patch("app.routes_wto_daily.upsert_schedule_for_employee_day") as upsert:
            self.assertTrue(
                _persist_local_schedule_after_wto_daily(
                    ctx,
                    employee_afm=" 987654321 ",
                    body=body,
                    payload=self._payload(),
                )
            )

        upsert.assert_called_once_with(
            " 123456789 ",
            "2",
            "2026-07-02",
            employee_afm=" 987654321 ",
            hour_from="10:00",
            hour_to="18:00",
            shift_type="ΕΡΓ",
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
            intervals=[{"hour_from": "10:00", "hour_to": "18:00"}],
        )

    def test_persist_local_schedule_after_wto_daily_updates_split_hours(self):
        ctx = {"employer_afm": "123456789", "branch_aa": "0"}
        body = {
            "schedule_type": "ΕΡΓ",
            "hour_from": "09:00",
            "hour_to": "21:00",
            "intervals": [
                {"hour_from": "09:00", "hour_to": "13:00"},
                {"hour_from": "17:00", "hour_to": "21:00"},
            ],
        }

        with patch("app.routes_wto_daily.upsert_schedule_for_employee_day") as upsert:
            self.assertTrue(
                _persist_local_schedule_after_wto_daily(
                    ctx,
                    employee_afm="987654321",
                    body=body,
                    payload=self._payload(),
                )
            )

        upsert.assert_called_once_with(
            "123456789",
            "0",
            "2026-07-02",
            employee_afm="987654321",
            hour_from="09:00",
            hour_to="21:00",
            shift_type="ΕΡΓ",
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
            intervals=[
                {"hour_from": "09:00", "hour_to": "13:00"},
                {"hour_from": "17:00", "hour_to": "21:00"},
            ],
        )

    def test_persist_local_schedule_after_wto_daily_updates_rest_day(self):
        ctx = {"employer_afm": "123456789", "branch_aa": "0"}
        body = {
            "schedule_type": "AN",
            "hour_from": "10:00",
            "hour_to": "18:00",
        }

        with patch("app.routes_wto_daily.upsert_schedule_for_employee_day") as upsert:
            self.assertTrue(
                _persist_local_schedule_after_wto_daily(
                    ctx,
                    employee_afm="987654321",
                    body=body,
                    payload=self._payload(),
                )
            )

        upsert.assert_called_once_with(
            "123456789",
            "0",
            "2026-07-02",
            employee_afm="987654321",
            hour_from=None,
            hour_to=None,
            shift_type="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ",
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
            intervals=None,
        )

    def test_record_wto_daily_schedule_audit_includes_before_after_employee_and_protocol(self):
        ctx = {"id": 4, "employer_afm": "123456789", "branch_aa": "0"}
        body = {
            "schedule_type": "ΕΡΓ",
            "hour_from": "09:00",
            "hour_to": "21:00",
            "intervals": [
                {"hour_from": "09:00", "hour_to": "13:00"},
                {"hour_from": "17:00", "hour_to": "21:00"},
            ],
        }
        old = [{"hour_from": "10:00", "hour_to": "18:00", "shift_type": "ΕΡΓ"}]

        with (
            patch("app.routes_wto_daily._current_schedule_snapshot", return_value=[
                {"hour_from": "09:00", "hour_to": "13:00", "shift_type": "ΕΡΓ"},
                {"hour_from": "17:00", "hour_to": "21:00", "shift_type": "ΕΡΓ"},
            ]),
            patch("app.routes_wto_daily.record_audit_event") as audit,
        ):
            record_wto_daily_schedule_audit(
                ctx,
                employee_afm="987654321",
                eponymo="ΟΙΚΟΝΟΜΟΥ",
                onoma="ΕΥΤΥΧΙΑ",
                work_date_ergani="02/07/2026",
                body=body,
                old_schedule=old,
                protocol="123/2026",
                ergani_submission_id="42",
                local_schedule_updated=True,
                http_status=200,
                success=True,
            )

        audit.assert_called_once()
        kwargs = audit.call_args.kwargs
        self.assertEqual(kwargs["action"], "wto_daily.schedule_change")
        self.assertEqual(kwargs["entity_type"], "employee")
        self.assertEqual(kwargs["entity_id"], "987654321")
        details = kwargs["details"]
        self.assertEqual(details["employee_name"], "ΟΙΚΟΝΟΜΟΥ ΕΥΤΥΧΙΑ")
        self.assertEqual(details["old_schedule"], old)
        self.assertEqual(len(details["new_schedule"]), 2)
        self.assertEqual(details["protocol"], "123/2026")

    def test_ergani_authorization_denied_detects_status_and_message(self):
        self.assertTrue(
            _ergani_authorization_denied(
                _FakeResp(status_code=403, text=""),
                {},
            )
        )
        self.assertTrue(
            _ergani_authorization_denied(
                _FakeResp(status_code=200, text="Authorization has been denied for this request."),
                {},
            )
        )
        self.assertTrue(
            _ergani_authorization_denied(
                _FakeResp(status_code=200, text=""),
                {"message": "Authorization has been denied for this request."},
            )
        )

    def test_submit_wto_daily_with_auth_retry_refreshes_expired_bearer_once(self):
        app = Flask(__name__)
        app.secret_key = "test"
        client = _FakeClient(
            [
                _FakeResp(
                    status_code=200,
                    ok=False,
                    payload={"message": "Authorization has been denied for this request."},
                ),
                _FakeResp(
                    status_code=200,
                    ok=True,
                    payload=[{"protocol": "123/2026"}],
                ),
            ]
        )
        ctx = {"id": 4, "ergani_env": "production"}

        with app.test_request_context("/"):
            session["ergani_bearer"] = "old-token"
            session["ergani_bearer_store_id"] = "4"
            session["ergani_bearer_env"] = "production"
            with patch("app.routes_wto_daily.ensure_ergani_bearer", return_value="new-token"):
                resp, parsed, retried = _submit_wto_daily_with_auth_retry(
                    ctx,
                    client,
                    {"WTOS": {"WTO": []}},
                    "old-token",
                )

        self.assertTrue(resp.ok)
        self.assertEqual(parsed, [{"protocol": "123/2026"}])
        self.assertTrue(retried)
        self.assertEqual([call[2] for call in client.calls], ["old-token", "new-token"])


if __name__ == "__main__":
    unittest.main()
