// Dùng chung cho service worker, popup và trang tuỳ chọn.
export const DEFAULTS = {
  enabled: true,
  port: 41888,
  minSizeKB: 0,
  exts: "3gp 7z aac apk avi bin bz2 deb dmg exe flac flv gz iso jar m4a m4v mkv mov mp3 mp4 mpeg mpg msi msix " +
        "ogg pdf pkg ppt pptx rar rpm tar tgz wav webm wma wmv xapk xz zip zst docx xlsx",
  excludeHosts: "",
};

export async function getCfg() {
  return chrome.storage.sync.get(DEFAULTS);
}

export const apiBase = (cfg) => `http://127.0.0.1:${cfg.port}`;

export async function ping(cfg, timeout = 800) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(apiBase(cfg) + "/api/ping", { signal: ctl.signal, cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

export async function post(cfg, path, body) {
  const r = await fetch(apiBase(cfg) + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error("TDownload trả lỗi HTTP " + r.status);
  return r.json();
}

// Cookie đúng của URL đó (kể cả cookie HttpOnly mà trang web không đọc được) — không gửi cho host khác.
export async function cookiesFor(url) {
  try {
    const list = await chrome.cookies.getAll({ url });
    return list.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    return "";
  }
}

export function nameFromUrl(u) {
  try {
    const p = new URL(u).pathname;
    return decodeURIComponent(p.split("/").pop() || "");
  } catch {
    return "";
  }
}

export function extOf(name) {
  const m = /\.([a-z0-9]{1,8})$/i.exec(name || "");
  return m ? m[1].toLowerCase() : "";
}

export function hostExcluded(cfg, url) {
  let host = "";
  try { host = new URL(url).hostname; } catch { return false; }
  return cfg.excludeHosts.split(/[\s,]+/).filter(Boolean).some((h) => host === h || host.endsWith("." + h));
}

export function fmtSize(n) {
  if (!n || n < 0) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 100 ? 1 : 0) : n) + " " + u[i];
}
