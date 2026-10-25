"""Bộ cài Inno Setup (installer.iss) phải khớp với mã: AppId, mutex, tên tệp, khoá registry app tự ghi."""

import os
import re
import sys

from qtdownloader import APP_ID, APP_MUTEX_NAME, APP_NAME, INNO_APP_ID
from qtdownloader.core import integration, updater

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def raw(*p: str) -> bytes:
    with open(os.path.join(ROOT, *p), "rb") as f:
        return f.read()


def iss() -> str:
    return raw("installer.iss").decode("utf-8-sig")


def defines() -> dict[str, str]:
    return dict(re.findall(r'^\s*#define (\w+) "([^"]*)"', iss(), re.M))


def test_inno_files_are_utf8_bom_crlf():
    """ISCC đọc tiếng Việt đúng chỉ khi có BOM; .gitattributes giữ CRLF."""
    for p in ("installer.iss", os.path.join("installer", "Vietnamese.isl")):
        data = raw(p)
        assert data.startswith(b"\xef\xbb\xbf"), p
        assert b"\n" not in data.replace(b"\r\n", b""), f"{p} có dòng kết thúc LF"
        data.decode("utf-8")


def test_app_id_and_mutex_match_code():
    text = iss()
    assert "AppId={" + INNO_APP_ID + "\r\n" in text        # «{{» = dấu { trong Inno
    assert f"AppMutex={APP_MUTEX_NAME}\r\n" in text
    d = defines()
    assert d["AppName"] == APP_NAME and d["AppId"] == APP_ID and d["AppExe"] == f"{APP_ID}.exe"


def test_per_user_install_without_uac():
    text = iss()
    assert "PrivilegesRequired=lowest" in text
    assert r"DefaultDirName={localappdata}\Programs\{#AppName}" in text
    assert "UninstallDisplayName={#AppName}" in text


def test_setup_name_matches_updater():
    """Trình cập nhật (bản đã cài) tìm đúng tên tệp bộ cài sinh ra."""
    assert "OutputBaseFilename={#AppId}-{#AppVersion}-setup" in iss()
    assert updater.SETUP_RE.match(f"{APP_ID}-9.9.9-setup.exe")
    assert updater.ASSET_RE.match(f"{APP_ID}-9.9.9-win64.zip")


def test_uninstall_removes_registry_written_by_app():
    """Giao thức / khởi động cùng Windows do app ghi (cả tên cũ TDownload) phải được trình gỡ cài đặt xoá."""
    text, d = iss(), defines()
    assert d["Protocol"] == integration.PROTOCOL and d["LegacyProtocol"] == integration.LEGACY_PROTOCOL
    assert d["RunKey"] == integration.RUN_KEY
    assert "RegDeleteKeyIncludingSubkeys(HKCU, 'Software\\Classes\\{#Protocol}')" in text
    assert "RegDeleteKeyIncludingSubkeys(HKCU, 'Software\\Classes\\{#LegacyProtocol}')" in text
    for value in (integration.RUN_VALUE, integration.LEGACY_RUN_VALUE):
        assert f"RegDeleteValue(HKCU, '{{#RunKey}}', '{value}')" in text
    # dữ liệu người dùng: hỏi trước, gỡ im lặng thì giữ
    assert "{localappdata}\\{#AppId}" in text and "UninstallSilent()" in text


def test_update_launch_flag_handled():
    """main_window chạy bộ cài với /LAUNCHAPP để mở lại app; .iss phải nhận cờ này."""
    assert "'/LAUNCHAPP'" in iss()
    with open(os.path.join(ROOT, "qtdownloader", "ui", "main_window.py"), encoding="utf-8") as f:
        assert '"/LAUNCHAPP"' in f.read()


def test_custom_messages_exist():
    isl = raw("installer", "Vietnamese.isl").decode("utf-8-sig")
    for name in set(re.findall(r"CustomMessage\('(\w+)'\)|\{cm:(\w+)", iss())) - {("", "")}:
        key = name[0] or name[1]
        assert re.search(rf"^{key}=", isl, re.M), f"Vietnamese.isl thiếu {key}"
    assert "QT PDF Pro" not in isl.split("[CustomMessages]")[1]


def test_installer_ships_licenses():
    text = iss()
    assert 'Source: "LICENSE"' in text and 'Source: "THIRD_PARTY_NOTICES.md"' in text
    assert 'Source: "licenses\\*"' in text


def test_package_release_names():
    import package_release
    assert package_release.LEGACY_ZIP_PREFIX == "TDownload"
    assert re.match(r"^TDownload-.+-win64\.zip$", "TDownload-1.1.0-win64.zip")   # regex của bản ≤ 1.0.3
