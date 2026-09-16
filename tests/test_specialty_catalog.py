# -*- coding: utf-8 -*-
"""Tests for local Step92 specialty catalog helpers."""

from __future__ import annotations

from app.repo_specialty_catalog import _search_blob


def test_search_blob_is_casefold():
    blob = _search_blob("515", "\u03a3\u0395\u03a1\u0392\u0399\u03a4\u039f\u03a1\u039f\u03a3")
    assert "515" in blob
    assert "\u03c3\u03b5\u03c1\u03b2\u03b9\u03c4\u03bf\u03c1\u03bf\u03c3" in blob
