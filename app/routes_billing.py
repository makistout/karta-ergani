"""API τιμολόγησης. Απομονωμένο από store/card/apologistic flows."""

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from app import repo_billing
from app.billing_agreement import (
    agreement_filename,
    customer_for_agreement,
    fill_agreement_docx,
    fill_offer_docx,
    offer_filename,
)
from app.billing_presentation import presentation_file, send_presentation
from app.email_notify import EmailNotConfigured

billing_bp = Blueprint("billing", __name__, url_prefix="/api/billing")


def _error(exc: Exception, not_found: int = 404):
    if isinstance(exc, KeyError):
        return jsonify(error=str(exc) or "Δεν βρέθηκε"), not_found
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    return jsonify(error=str(exc)), 400


@billing_bp.get("/customers")
def customers_list():
    try:
        return jsonify(customers=repo_billing.list_customers())
    except Exception as exc:
        return jsonify(error=str(exc), db_setup="python scripts/run_migration_billing.py"), 503


@billing_bp.post("/customers")
def customers_create():
    try:
        return jsonify(success=True, customer=repo_billing.create_customer(request.get_json(silent=True) or {})), 201
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/customers/<int:customer_id>")
def customers_get(customer_id: int):
    try:
        customer = repo_billing.get_customer(customer_id)
        if not customer:
            return jsonify(error="Ο πελάτης δεν βρέθηκε."), 404
        return jsonify(customer=customer)
    except Exception as exc:
        return _error(exc)


@billing_bp.put("/customers/<int:customer_id>")
def customers_update(customer_id: int):
    try:
        return jsonify(success=True, customer=repo_billing.update_customer(customer_id, request.get_json(silent=True) or {}))
    except Exception as exc:
        return _error(exc)


@billing_bp.delete("/customers/<int:customer_id>")
def customers_deactivate(customer_id: int):
    try:
        repo_billing.deactivate_customer(customer_id)
        return jsonify(success=True)
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/agreement")
def billing_agreement():
    try:
        customer = customer_for_agreement(request.get_json(silent=True) or {})
        content = fill_agreement_docx(customer)
    except Exception as exc:
        return _error(exc)
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=agreement_filename(customer),
    )


@billing_bp.post("/offer")
def billing_offer():
    try:
        customer = customer_for_agreement(request.get_json(silent=True) or {})
        content = fill_offer_docx(customer)
    except Exception as exc:
        return _error(exc)
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=offer_filename(customer),
    )


@billing_bp.post("/presentation")
def billing_presentation():
    try:
        result = send_presentation(request.get_json(silent=True) or {})
    except EmailNotConfigured as exc:
        return jsonify(error=str(exc)), 503
    except Exception as exc:
        return _error(exc)
    return jsonify(success=True, **result)


@billing_bp.get("/presentation/files/<key>")
def billing_presentation_file(key: str):
    try:
        path = presentation_file(key)
    except Exception as exc:
        return _error(exc)
    return send_file(path, mimetype="application/pdf", as_attachment=False, download_name=path.name)


@billing_bp.put("/customers/<int:customer_id>/stores")
def customers_stores(customer_id: int):
    body = request.get_json(silent=True) or {}
    raw = body.get("store_ids") or []
    store_ids = []
    for item in raw if isinstance(raw, list) else []:
        try:
            store_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    try:
        return jsonify(success=True, stores=repo_billing.set_customer_stores(customer_id, store_ids))
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/stores")
def billing_stores():
    try:
        return jsonify(stores=repo_billing.list_store_assignments())
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/plans")
def billing_plans():
    try:
        return jsonify(plans=repo_billing.list_plans(active_only=False))
    except Exception as exc:
        return _error(exc)


@billing_bp.put("/plans/<int:plan_id>")
def billing_plans_update(plan_id: int):
    try:
        return jsonify(success=True, plan=repo_billing.update_plan(plan_id, request.get_json(silent=True) or {}))
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/plans/<int:plan_id>/duplicate")
def billing_plans_duplicate(plan_id: int):
    try:
        return jsonify(success=True, plan=repo_billing.duplicate_plan(plan_id)), 201
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/subscriptions")
def subscriptions_list():
    try:
        return jsonify(subscriptions=repo_billing.list_all_subscriptions())
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/customers/<int:customer_id>/unbilled-subscriptions")
def subscriptions_unbilled(customer_id: int):
    try:
        return jsonify(subscriptions=repo_billing.unbilled_subscriptions(customer_id))
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/subscriptions")
def subscriptions_create():
    body = request.get_json(silent=True) or {}
    try:
        customer_id = int(body.get("customer_id") or 0)
        if customer_id <= 0:
            raise ValueError("Επιλέξτε πελάτη.")
        return jsonify(success=True, subscription=repo_billing.add_subscription(customer_id, body)), 201
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/subscriptions/<int:subscription_id>/cancel")
def subscriptions_cancel(subscription_id: int):
    try:
        repo_billing.cancel_subscription(subscription_id)
        return jsonify(success=True)
    except Exception as exc:
        return _error(exc)


@billing_bp.get("/documents")
def documents_list():
    try:
        return jsonify(documents=repo_billing.list_documents())
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/documents/issue")
def documents_issue():
    body = request.get_json(silent=True) or {}
    try:
        customer_id = int(body.get("customer_id") or 0)
        if customer_id <= 0:
            raise ValueError("Επιλέξτε πελάτη.")
        return jsonify(success=True, document=repo_billing.issue_from_subscriptions(customer_id, body)), 201
    except Exception as exc:
        return _error(exc)


@billing_bp.post("/documents/<int:document_id>/credit")
def documents_credit(document_id: int):
    try:
        return jsonify(success=True, document=repo_billing.issue_credit(document_id)), 201
    except Exception as exc:
        return _error(exc)
