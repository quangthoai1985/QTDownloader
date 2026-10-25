"""Đổi tên TDownload → QT Downloader (1.1.0): dữ liệu của bản cũ được chuyển sang thư mục mới."""

from qtdownloader.core import settings as S


def _legacy(tmp_path):
    old = tmp_path / "TDownload"
    (old / "logs").mkdir(parents=True)
    (old / "settings.json").write_text('{"max_connections": 16}', encoding="utf-8")
    for suffix in ("", "-wal", "-shm"):
        (old / ("tdownload.db" + suffix)).write_bytes(b"db" + suffix.encode())
    (old / "logs" / "tdownload.log").write_text("log", encoding="utf-8")
    return old


def test_migrate_moves_everything(tmp_path):
    old, new = _legacy(tmp_path), tmp_path / "QTDownloader"
    assert S.migrate_legacy_data(new, old) is True
    assert not old.exists()
    assert S.Settings.load(new / "settings.json").max_connections == 16
    assert (new / "qtdownloader.db").read_bytes() == b"db"
    assert (new / "qtdownloader.db-wal").read_bytes() == b"db-wal"
    assert (new / "qtdownloader.db-shm").exists() and not (new / "tdownload.db").exists()
    assert (new / "logs" / "qtdownloader.log").read_text(encoding="utf-8") == "log"


def test_migrate_never_overwrites_new_dir(tmp_path):
    old, new = _legacy(tmp_path), tmp_path / "QTDownloader"
    new.mkdir()
    (new / "settings.json").write_text("{}", encoding="utf-8")
    assert S.migrate_legacy_data(new, old) is False
    assert (old / "tdownload.db").exists()
    assert S.Settings.load(new / "settings.json").max_connections == 8


def test_migrate_ignores_missing_or_empty_legacy(tmp_path):
    new = tmp_path / "QTDownloader"
    assert S.migrate_legacy_data(new, tmp_path / "TDownload") is False
    (tmp_path / "TDownload").mkdir()
    assert S.migrate_legacy_data(new, tmp_path / "TDownload") is False
    assert not new.exists()


def test_resolve_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("QTDOWNLOADER_DATA", raising=False)
    monkeypatch.delenv("TDOWNLOAD_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _legacy(tmp_path)
    assert S.resolve_data_dir() == tmp_path / "QTDownloader"
    assert (tmp_path / "QTDownloader" / "qtdownloader.db").exists()
    monkeypatch.setenv("TDOWNLOAD_DATA", str(tmp_path / "cu"))          # biến môi trường tên cũ vẫn nhận
    assert S.resolve_data_dir() == tmp_path / "cu"
    monkeypatch.setenv("QTDOWNLOADER_DATA", str(tmp_path / "moi"))
    assert S.resolve_data_dir() == tmp_path / "moi"


def test_resolve_falls_back_to_legacy_when_rename_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("QTDOWNLOADER_DATA", raising=False)
    monkeypatch.delenv("TDOWNLOAD_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _legacy(tmp_path)

    def locked(*_a):
        raise PermissionError("bản cũ đang mở")
    monkeypatch.setattr(S.os, "replace", locked)
    assert S.resolve_data_dir() == tmp_path / "TDownload"     # dùng tạm, không mất danh sách tải


def test_engine_opens_legacy_db_name(tmp_path):
    """Đang dùng tạm thư mục cũ → engine mở đúng tdownload.db, không tạo CSDL trống."""
    from qtdownloader.core.engine import Engine
    eng = Engine(tmp_path / "TDownload", start_api=False)
    eng.start()
    eng.shutdown()
    assert (tmp_path / "TDownload" / "qtdownloader.db").exists()
    for f in (tmp_path / "TDownload").iterdir():
        if f.name.startswith("qtdownloader.db"):
            f.rename(f.with_name(f.name.replace("qtdownloader.db", "tdownload.db")))
    eng = Engine(tmp_path / "TDownload", start_api=False)
    eng.start()
    eng.shutdown()
    assert not (tmp_path / "TDownload" / "qtdownloader.db").exists()
