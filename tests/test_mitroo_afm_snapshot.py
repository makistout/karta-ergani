from pathlib import Path

from app import mitroo_afm_snapshot as snap


def test_mitroo_afm_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(snap, "_snapshot_dir", lambda: Path(tmp_path))

    assert snap.load_mitroo_afm_snapshot("123456789", "0") is None
    snap.save_mitroo_afm_snapshot("123456789", "0", {"111222333", "444555666", ""})
    loaded = snap.load_mitroo_afm_snapshot("123456789", "0")
    assert loaded == {"111222333", "444555666"}

    snap.save_mitroo_afm_snapshot("123456789", "0", ["444555666", "777888999"])
    assert snap.load_mitroo_afm_snapshot("123456789", "0") == {"444555666", "777888999"}
