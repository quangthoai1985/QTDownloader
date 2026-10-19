// Service worker: bắt tải xuống, menu chuột phải, phát hiện media trên tab.
import { cookiesFor, extOf, getCfg, hostExcluded, nameFromUrl, ping, post } from "./common.js";

const FILE_MIMES = /^(application\/(octet-stream|zip|x-zip|x-rar|vnd\.rar|x-7z|x-msdownload|x-msi|x-iso9660|gzip|x-gzip|x-tar|x-bzip2|x-xz|pdf|vnd\.android|vnd\.ms-|vnd\.openxmlformats|java-archive|x-apple-diskimage|x-debian|x-rpm)|video\/|audio\/)/i;

// ------------------------------------------------------------------ bắt tải xuống của trình duyệt
chrome.downloads.onCreated.addListener(async (item) => {
  const cfg = await getCfg();
  if (!cfg.enabled) return;
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return;               // blob:/data:/file: không chuyển được
  if (item.state && item.state !== "in_progress") return;
  if (hostExcluded(cfg, url) || (item.referrer && hostExcluded(cfg, item.referrer))) return;
  const name = (item.filename || "").split(/[\\/]/).pop() || nameFromUrl(url);
  const ext = extOf(name);
  const wanted = cfg.exts.toLowerCase().split(/[\s,]+/).filter(Boolean);
  const byExt = ext && wanted.includes(ext);
  const byMime = !ext && FILE_MIMES.test(item.mime || "");
  if (!byExt && !byMime) return;
  const size = item.totalBytes || item.fileSize || 0;
  if (cfg.minSizeKB > 0 && size > 0 && size < cfg.minSizeKB * 1024) return;
  if (!(await ping(cfg))) return;                   // app chưa chạy → để trình duyệt tự tải

  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
  } catch (e) {
    // tải quá nhanh đã xong — bỏ qua
  }
  try {
    await post(cfg, "/api/add", {
      url,
      filename: name,
      referer: item.referrer || "",
      cookies: await cookiesFor(url),
      userAgent: navigator.userAgent,
      fileSize: size,
      mime: item.mime || "",
    });
    flashBadge("✓");
  } catch (e) {
    // gửi thất bại → mở lại tải bằng trình duyệt để người dùng không mất link
    chrome.downloads.download({ url });
  }
});

// ------------------------------------------------------------------ menu chuột phải
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "td-link", title: "Tải bằng TDownload", contexts: ["link", "image", "video", "audio"] });
    chrome.contextMenus.create({ id: "td-selection", title: "Tải các liên kết đã chọn bằng TDownload", contexts: ["selection"] });
    chrome.contextMenus.create({ id: "td-all", title: "Tải tất cả liên kết trên trang bằng TDownload", contexts: ["page"] });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const cfg = await getCfg();
  if (!(await ping(cfg))) return notifyAppMissing();
  if (info.menuItemId === "td-link") {
    const url = info.linkUrl || info.srcUrl;
    if (!url || !/^https?:/i.test(url)) return;
    await post(cfg, "/api/add", {
      url, referer: info.pageUrl || "", cookies: await cookiesFor(url), userAgent: navigator.userAgent,
      pageUrl: info.pageUrl || "",
    });
  } else if (tab && tab.id !== undefined) {
    await sendPageLinks(cfg, tab, info.menuItemId === "td-selection");
  }
});

export async function sendPageLinks(cfg, tab, selectionOnly) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    args: [selectionOnly],
    func: (onlySel) => {
      const out = new Map();
      const sel = window.getSelection();
      const inSel = (el) => !onlySel || (sel && sel.rangeCount && sel.containsNode(el, true));
      for (const a of document.querySelectorAll("a[href]")) {
        if (inSel(a) && /^https?:/i.test(a.href)) out.set(a.href, (a.textContent || "").trim().slice(0, 120));
      }
      for (const m of document.querySelectorAll("img[src], video[src], audio[src], source[src]")) {
        if (inSel(m) && /^https?:/i.test(m.src) && !out.has(m.src)) out.set(m.src, m.alt || "");
      }
      return [...out].map(([url, text]) => ({ url, text }));
    },
  });
  const links = (res && res.result) || [];
  if (!links.length) return;
  const jar = new Map();     // cookie theo từng origin — không gửi cookie của trang cho host khác
  for (const l of links) {
    let origin = "";
    try { origin = new URL(l.url).origin; } catch { continue; }
    if (!jar.has(origin)) jar.set(origin, await cookiesFor(origin + "/"));
    l.cookies = jar.get(origin);
    l.referer = tab.url;
  }
  await post(cfg, "/api/add-batch", { items: links, pageUrl: tab.url, referer: tab.url, userAgent: navigator.userAgent });
}

// ------------------------------------------------------------------ phát hiện media (video/âm thanh/HLS)
const MEDIA_KEY = (tabId) => `media:${tabId}`;

chrome.webRequest.onHeadersReceived.addListener(
  (d) => {
    if (d.tabId < 0 || d.statusCode >= 400) return;
    const h = Object.fromEntries((d.responseHeaders || []).map((x) => [x.name.toLowerCase(), x.value || ""]));
    const ct = (h["content-type"] || "").toLowerCase();
    const len = parseInt(h["content-length"] || "0", 10) || 0;
    const range = h["content-range"] || "";
    const total = parseInt((range.split("/")[1] || "0"), 10) || len;
    const path = d.url.split("?")[0].toLowerCase();
    let kind = "";
    if (ct.includes("mpegurl") || path.endsWith(".m3u8")) kind = "HLS";
    else if (path.endsWith(".mpd") || ct.includes("dash+xml")) kind = "DASH";
    else if ((ct.startsWith("video/") || ct.startsWith("audio/")) && !ct.includes("mp2t") && total > 512 * 1024
             && !/\.(ts|m4s|aac)$/.test(path)) kind = ct.split("/")[1].split(";")[0].toUpperCase();
    if (!kind) return;
    recordMedia(d.tabId, { url: d.url, kind, size: total, time: Date.now() });
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] },
  ["responseHeaders"],
);

async function recordMedia(tabId, entry) {
  const key = MEDIA_KEY(tabId);
  const cur = (await chrome.storage.session.get(key))[key] || [];
  const base = (u) => u.split("?")[0];
  if (cur.some((m) => m.url === entry.url || (m.kind !== "HLS" && base(m.url) === base(entry.url)))) return;
  cur.unshift(entry);
  await chrome.storage.session.set({ [key]: cur.slice(0, 40) });
  chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" });
  chrome.action.setBadgeText({ tabId, text: String(Math.min(cur.length, 99)) });
}

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "loading" && info.url) {
    chrome.storage.session.remove(MEDIA_KEY(tabId));
    chrome.action.setBadgeText({ tabId, text: "" });
  }
});
chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(MEDIA_KEY(tabId)));

// ------------------------------------------------------------------ tin nhắn từ popup
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    const cfg = await getCfg();
    if (msg.type === "sendMedia") {
      await post(cfg, "/api/add", {
        url: msg.url, referer: msg.pageUrl, pageUrl: msg.pageUrl, cookies: await cookiesFor(msg.url),
        userAgent: navigator.userAgent, filename: msg.filename || "", kind: msg.kind === "HLS" ? "hls" : "http",
      });
      reply({ ok: true });
    } else if (msg.type === "sendAll") {
      await sendPageLinks(cfg, msg.tab, false);
      reply({ ok: true });
    }
  })().catch((e) => reply({ ok: false, error: String(e) }));
  return true;
});

function flashBadge(text) {
  chrome.action.setBadgeBackgroundColor({ color: "#16a34a" });
  chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 2500);
}

function notifyAppMissing() {
  chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
  chrome.action.setBadgeText({ text: "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
}
