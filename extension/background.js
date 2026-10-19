// Service worker: bắt tải xuống, menu chuột phải, phát hiện media trên tab.
import {
  cookiesFor, extOf, getCfg, hostExcluded, nameFromUrl, ping, post, protocolState, waitForApp,
} from "./common.js";

const FILE_MIMES = /^(application\/(octet-stream|zip|x-zip|x-rar|vnd\.rar|x-7z|x-msdownload|x-msi|x-iso9660|gzip|x-gzip|x-tar|x-bzip2|x-xz|pdf|vnd\.android|vnd\.ms-|vnd\.openxmlformats|java-archive|x-apple-diskimage|x-debian|x-rpm)|video\/|audio\/)/i;

// ------------------------------------------------------------------ bắt tải xuống của trình duyệt
// Link extension cố ý giao lại cho trình duyệt (app không nhận) — không bắt lại, tránh vòng lặp gửi/tải.
const toBrowser = new Set();

function browserDownload(url) {
  toBrowser.add(url);
  setTimeout(() => toBrowser.delete(url), 60000);
  return chrome.downloads.download({ url });
}

// Quyết định lượt tải có giao cho app không; nếu có thì huỷ bên trình duyệt và gửi sang app.
// Trả về true khi đã nhận (trình duyệt không được tải tiếp), false khi để trình duyệt tự tải.
async function intercept(item) {
  const cfg = await getCfg();
  if (!cfg.enabled) return false;
  if (toBrowser.delete(item.url) || toBrowser.delete(item.finalUrl)) return false;
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return false;         // blob:/data:/file: không chuyển được
  if (item.state && item.state !== "in_progress") return false;
  if (hostExcluded(cfg, url) || (item.referrer && hostExcluded(cfg, item.referrer))) return false;
  const name = (item.filename || "").split(/[\\/]/).pop() || nameFromUrl(url);
  const ext = extOf(name);
  const wanted = cfg.exts.toLowerCase().split(/[\s,]+/).filter(Boolean);
  const byExt = ext && wanted.includes(ext);
  const byMime = !ext && FILE_MIMES.test(item.mime || "");
  if (!byExt && !byMime) return false;
  const size = item.totalBytes || item.fileSize || 0;
  if (cfg.minSizeKB > 0 && size > 0 && size < cfg.minSizeKB * 1024) return false;
  if (!(await ping(cfg))) return false;             // app chưa chạy → để trình duyệt tự tải

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
    browserDownload(url);
  }
  return true;
}

if (chrome.downloads.onDeterminingFilename) {
  // Chrome/Edge/Cốc Cốc: trình duyệt TẠM GIỮ lượt tải cho tới khi extension gọi suggest() — hộp thoại
  // "Lưu thành…" và khung/bong bóng tải xuống chỉ hiện sau bước này. Huỷ ngay tại đây thì trình duyệt không
  // hiện gì; onCreated thì chạy song song với giao diện tải của trình duyệt nên luôn huỷ muộn.
  chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
    intercept(item)
      .then((taken) => { if (!taken) suggest(); })
      .catch(() => suggest());
    return true;                                    // gọi suggest() bất đồng bộ
  });
} else {
  chrome.downloads.onCreated.addListener((item) => void intercept(item));
}

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
  const tabId = tab && tab.id >= 0 ? tab.id : undefined;
  if (info.menuItemId === "td-link") {
    const url = info.linkUrl || info.srcUrl;
    if (!url || !/^https?:/i.test(url)) return;
    await sendLink(cfg, tabId, {
      url, referer: info.pageUrl || "", cookies: await cookiesFor(url), userAgent: navigator.userAgent,
      pageUrl: info.pageUrl || "",
    });
  } else if (tabId !== undefined) {
    const why = await ensureApp(cfg, tabId);
    if (why) return warn("Chưa gửi được sang TDownload", why);
    await sendPageLinks(cfg, tab, info.menuItemId === "td-selection");
  }
});

// ------------------------------------------------------------------ app chưa chạy
const HINT_ENABLE = "Bật Tuỳ chọn → Trình duyệt → “Cho phép trình duyệt mở TDownload” trong app để extension tự mở " +
                    "app, hoặc bật “Khởi động cùng Windows”.";

// Bảo đảm app đang chạy; nếu chưa thì mở qua tdownload:// rồi chờ API lên.
// Trả về "" khi app sẵn sàng, ngược lại là lý do (tiếng Việt) để báo người dùng.
// manual = người dùng bấm "Mở TDownload": luôn thử và hiện cửa sổ chính.
async function ensureApp(cfg, tabId, manual = false) {
  if (await ping(cfg)) return "";
  const known = await protocolState();
  if (!manual && !cfg.launchApp) return "TDownload chưa chạy (đã tắt “Tự mở TDownload” trong tuỳ chọn extension).";
  if (!manual && known === false) return "TDownload chưa chạy. " + HINT_ENABLE;
  setWaiting(true);
  let tmp;
  try {
    // Mở ở tab tạm (launch.html tự điều hướng tới tdownload://) thay vì điều hướng tab hiện tại: không đụng
    // tới trang người dùng đang xem. Giao thức đã đăng ký → trình duyệt hỏi "Mở TDownload?" kèm ô "Luôn cho
    // phép" (nhờ origin của extension); chưa đăng ký → không có gì xảy ra.
    const target = manual ? "tdownload://open" : "tdownload://open?minimized=1";
    tmp = await chrome.tabs.create({
      url: chrome.runtime.getURL("launch.html") + "?u=" + encodeURIComponent(target),
      active: true, ...(tabId !== undefined ? { openerTabId: tabId } : {}),
    });
    // app khởi động mất 3–4 giây, người dùng còn phải bấm "Mở" trong hộp thoại; biết chắc giao thức đã
    // đăng ký thì chờ lâu hơn. Chưa biết (app chưa từng báo) mà không mở được thì tab tạm đứng 10 giây.
    if (await waitForApp(cfg, known || manual ? 15000 : 10000)) return "";
    return known ? "Không mở được TDownload (đã chờ 15 giây). Hãy mở app rồi thử lại."
                 : "TDownload chưa chạy và không mở được. " + HINT_ENABLE;
  } catch (e) {
    return "Không mở được TDownload: " + e;
  } finally {
    if (tmp) await closeTempTab(tmp.id);
    setWaiting(false);
  }
}

async function closeTempTab(id) {
  try {
    const t = await chrome.tabs.get(id);
    const u = t.pendingUrl || t.url || "";   // không có quyền xem URL → "" (vẫn là tab của mình)
    const ours = !u || u.startsWith(chrome.runtime.getURL("launch.html")) || u.startsWith("tdownload:");
    if (ours) await chrome.tabs.remove(id);   // người dùng đã chuyển tab sang trang khác thì để nguyên
  } catch {
    // người dùng đã tự đóng tab
  }
}

// Gửi 1 link sang app (mở app nếu cần). Không được thì để trình duyệt tải — không làm mất link.
// Trả về "sent" | "browser" | "failed".
async function sendLink(cfg, tabId, body, browserFallback = true) {
  let why = await ensureApp(cfg, tabId);
  if (!why) {
    try {
      await post(cfg, "/api/add", body);
      flashBadge("✓");
      return "sent";
    } catch (e) {
      why = "TDownload không nhận link: " + e.message;
    }
  }
  if (!browserFallback) {
    warn("Chưa gửi được sang TDownload", why);
    return "failed";
  }
  try {
    await browserDownload(body.url);
  } catch (e) {
    warn("Không tải được", why + "\nTrình duyệt cũng không tải được: " + e.message);
    return "failed";
  }
  warn("Đã chuyển cho trình duyệt tải", why);
  return "browser";
}

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
      // luồng HLS/DASH trình duyệt không tự tải được → không có đường lui
      const status = await sendLink(cfg, msg.tabId, {
        url: msg.url, referer: msg.pageUrl, pageUrl: msg.pageUrl, cookies: await cookiesFor(msg.url),
        userAgent: navigator.userAgent, filename: msg.filename || "", kind: msg.kind === "HLS" ? "hls" : "http",
      }, !["HLS", "DASH"].includes(msg.kind));
      reply({ ok: status !== "failed", status });
    } else if (msg.type === "sendAll") {
      const why = await ensureApp(cfg, msg.tab.id);
      if (why) {
        warn("Chưa gửi được sang TDownload", why);
        return reply({ ok: false, error: why });
      }
      await sendPageLinks(cfg, msg.tab, false);
      reply({ ok: true });
    } else if (msg.type === "openApp") {
      const why = await ensureApp(cfg, msg.tabId, true);
      if (why) warn("Chưa mở được TDownload", why);
      reply({ ok: !why, error: why });
    }
  })().catch((e) => reply({ ok: false, error: String(e) }));
  return true;
});

// ------------------------------------------------------------------ báo cho người dùng
const TITLE = "TDownload";
let badgeTimer;

function badge(text, color, ms) {
  clearTimeout(badgeTimer);
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  if (ms) badgeTimer = setTimeout(() => {
    chrome.action.setBadgeText({ text: "" });
    chrome.action.setTitle({ title: TITLE });
  }, ms);
}

function flashBadge(text) {
  badge(text, "#16a34a", 2500);
}

function setWaiting(on) {
  chrome.action.setTitle({ title: on ? "TDownload — đang mở ứng dụng…" : TITLE });
  if (on) badge("…", "#6b7280");
  else chrome.action.setBadgeText({ text: "" });
}

// Huy hiệu "!" + tiêu đề nút (luôn có) + thông báo hệ thống (rõ hơn, người dùng thấy ngay).
function warn(title, message) {
  badge("!", "#dc2626", 15000);
  chrome.action.setTitle({ title: `TDownload — ${title}\n${message}` });
  chrome.notifications.create({ type: "basic", iconUrl: "icons/128.png", title, message, priority: 1 },
    () => void chrome.runtime.lastError);
}
