"""Δημόσιες SEO υποσελίδες landing (informational + commercial intent)."""

from __future__ import annotations

from flask import Flask, render_template

from app.public_urls import effective_public_base_url

LANDING_HOME_PATH = "/psifiaki-karta-ergasias/"

SEO_PAGES: tuple[dict[str, object], ...] = (
    {
        "slug": "psifiaki-karta-logistika-grafeia",
        "template": "ui/seo/accountants.html",
        "breadcrumb": "Λογιστικά γραφεία",
        "nav_label": "Για λογιστικά γραφεία",
        "title": "Ψηφιακή Κάρτα Εργασίας για λογιστικά γραφεία | erganiOS",
        "description": (
            "Πώς τα λογιστικά γραφεία οργανώνουν την ψηφιακή κάρτα εργασίας πελατών: "
            "εκκρεμότητες, αποκλίσεις ωραρίου, διαχείριση πελατών ΕΡΓΑΝΗ και λιγότερα τηλέφωνα."
        ),
        "related_slugs": (
            "apokliseis-psifiakis-kartas",
            "psifiako-orario-ergani",
            "chttypimata-kartas-ergasias",
        ),
    },
    {
        "slug": "ti-einai-i-psifiaki-karta-ergasias",
        "template": "ui/seo/what-is.html",
        "breadcrumb": "Τι είναι η ψηφιακή κάρτα",
        "nav_label": "Τι είναι η ψηφιακή κάρτα",
        "title": "Τι είναι η Ψηφιακή Κάρτα Εργασίας; | erganiOS",
        "description": (
            "Τι είναι η ψηφιακή κάρτα εργασίας, πώς συνδέεται με το ΕΡΓΑΝΗ, "
            "τι καταγράφουν τα χτυπήματα και τι πρέπει να προσέχει η επιχείρηση."
        ),
        "related_slugs": (
            "chttypimata-kartas-ergasias",
            "psifiako-orario-ergani",
            "apokliseis-psifiakis-kartas",
        ),
    },
    {
        "slug": "chttypimata-kartas-ergasias",
        "template": "ui/seo/punches.html",
        "breadcrumb": "Χτυπήματα κάρτας",
        "nav_label": "Χτυπήματα κάρτας",
        "title": "Χτυπήματα κάρτας εργασίας: τι πρέπει να προσέχει η επιχείρηση | erganiOS",
        "description": (
            "Κανόνες και πρακτικές για χτυπήματα κάρτας εργασίας: είσοδος, έξοδος, "
            "απαγορεύσεις, ελλιπή χτυπήματα και οργάνωση χωρίς παρανομίες."
        ),
        "related_slugs": (
            "ti-einai-i-psifiaki-karta-ergasias",
            "apokliseis-psifiakis-kartas",
            "psifiaki-karta-logistika-grafeia",
        ),
    },
    {
        "slug": "apokliseis-psifiakis-kartas",
        "template": "ui/seo/deviations.html",
        "breadcrumb": "Αποκλίσεις",
        "nav_label": "Αποκλίσεις ψηφιακής κάρτας",
        "title": "Αποκλίσεις ψηφιακής κάρτας: πώς τις ελέγχει η επιχείρηση | erganiOS",
        "description": (
            "Τι είναι οι αποκλίσεις ψηφιακής κάρτας, πώς εντοπίζονται καθυστερήσεις, "
            "ελλιπή χτυπήματα και διαφορές ωραρίου–πραγματικής απασχόλησης."
        ),
        "related_slugs": (
            "psifiako-orario-ergani",
            "chttypimata-kartas-ergasias",
            "psifiaki-karta-logistika-grafeia",
        ),
    },
    {
        "slug": "psifiako-orario-ergani",
        "template": "ui/seo/schedule.html",
        "breadcrumb": "Ψηφιακό ωράριο",
        "nav_label": "Ψηφιακό ωράριο ΕΡΓΑΝΗ",
        "title": "Ψηφιακό ωράριο ΕΡΓΑΝΗ: αλλαγές, βάρδιες και εκκρεμότητες | erganiOS",
        "description": (
            "Πώς λειτουργεί το ψηφιακό ωράριο ΕΡΓΑΝΗ, ημερήσιες και εβδομαδιαίες αλλαγές, "
            "σπαστά ωράρια και τι χρειάζεται η καθημερινή διαχείριση."
        ),
        "related_slugs": (
            "apokliseis-psifiakis-kartas",
            "ti-einai-i-psifiaki-karta-ergasias",
            "psifiaki-karta-logistika-grafeia",
        ),
    },
)

_PAGES_BY_SLUG = {str(p["slug"]): p for p in SEO_PAGES}


def landing_home_url() -> str:
    return f"{effective_public_base_url().rstrip('/')}{LANDING_HOME_PATH}"


def seo_page_url(slug: str) -> str:
    return f"{effective_public_base_url().rstrip('/')}/{slug.strip('/')}/"


def seo_public_paths() -> frozenset[str]:
    paths: set[str] = set()
    for page in SEO_PAGES:
        slug = str(page["slug"])
        paths.add(f"/{slug}")
        paths.add(f"/{slug}/")
    return frozenset(paths)


def _related_pages(slugs: tuple[str, ...]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for slug in slugs:
        page = _PAGES_BY_SLUG.get(slug)
        if not page:
            continue
        out.append(
            {
                "slug": slug,
                "label": str(page["nav_label"]),
                "url": f"/{slug}/",
            }
        )
    return out


def article_context(page: dict[str, object]) -> dict[str, object]:
    slug = str(page["slug"])
    canonical = seo_page_url(slug)
    return {
        "canonical_url": canonical,
        "page_title": str(page["title"]),
        "meta_description": str(page["description"]),
        "breadcrumb_label": str(page["breadcrumb"]),
        "landing_home_url": LANDING_HOME_PATH,
        "contact_url": f"{LANDING_HOME_PATH}#contact",
        "seo_guides": [
            {
                "slug": str(p["slug"]),
                "label": str(p["nav_label"]),
                "url": f"/{p['slug']}/",
            }
            for p in SEO_PAGES
        ],
        "related_pages": _related_pages(tuple(page.get("related_slugs") or ())),
    }


def register_landing_seo_routes(app: Flask) -> None:
    for page in SEO_PAGES:
        slug = str(page["slug"])
        template = str(page["template"])

        def _view(p: dict[str, object] = page, tpl: str = template):
            return render_template(tpl, **article_context(p))

        app.add_url_rule(f"/{slug}", endpoint=f"seo_{slug}", view_func=_view)
        app.add_url_rule(f"/{slug}/", endpoint=f"seo_{slug}_slash", view_func=_view)
