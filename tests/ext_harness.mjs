// Chạy extension/background.js thật trong Node với API chrome giả, kiểm luồng "app chưa chạy".
// Dùng bởi tests/test_integration.py; chạy tay: node tests/ext_harness.mjs
import assert from "node:assert/strict";
import http from "node:http";

// ------------------------------------------------------------------ "app" giả: chỉ nghe cổng khi được "mở"
const free = http.createServer();
await new Promise((r) => free.listen(0, "127.0.0.1", r));
const PORT = free.address().port;
await new Promise((r) => free.close(r));

let app = null;
let addFails = false;
const added = [];
function launchApp() {
  app = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      if (req.url === "/api/add") added.push(JSON.parse(body));
      if (req.url === "/api/add" && addFails) res.statusCode = 500;
      res.setHeader("Connection", "close");     // không để socket keep-alive treo lúc thoát (Node/Windows)
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(req.url === "/api/ping" ? { app: "TDownload", active: 0, protocol: true } : { ok: true }));
    });
  });
  app.listen(PORT, "127.0.0.1");
}
async function stopApp() {
  app.closeAllConnections();
  await new Promise((r) => app.close(r));
  app = null;
}

// ------------------------------------------------------------------ chrome.* giả
const calls = [];
const on = {};
let local = {};
let launchOnOpen = false;
const ev = (name) => ({ addListener: (fn) => (on[name] = fn) });
const rec = (name, impl = () => undefined) => async (...a) => { calls.push([name, ...a]); return impl(...a); };
const called = (name) => calls.filter((c) => c[0] === name);

globalThis.chrome = {
  runtime: { onInstalled: ev("installed"), onMessage: ev("message"), lastError: undefined },
  contextMenus: { onClicked: ev("menu"), removeAll: (cb) => cb && cb(), create: () => {} },
  downloads: { onCreated: ev("created"), download: rec("download", () => 1), cancel: rec("cancel"), erase: rec("erase") },
  webRequest: { onHeadersReceived: ev("headers") },
  tabs: {
    onUpdated: ev("updated"), onRemoved: ev("removed"),
    create: rec("tabs.create", (o) => {
      if (launchOnOpen && o.url.startsWith("tdownload://")) setTimeout(launchApp, 300);   // giả lập Windows mở app
      return { id: 99 };
    }),
    get: async (id) => ({ id, url: "" }),
    remove: rec("tabs.remove"),
  },
  storage: {
    sync: { get: async (d) => ({ ...d, port: PORT }) },
    local: { get: async (d) => ({ ...d, ...local }), set: async (o) => Object.assign(local, o) },
    session: { get: async () => ({}), set: async () => {}, remove: async () => {} },
  },
  action: { setBadgeText: () => {}, setBadgeBackgroundColor: () => {}, setTitle: rec("setTitle") },
  notifications: { create: rec("notify", (_o, cb) => cb && cb()) },
  cookies: { getAll: async () => [] },
};

await import("../extension/background.js");

function reset(state) {
  calls.length = 0;
  added.length = 0;
  local = state;
  launchOnOpen = false;
}
const menuLink = (url) => on.menu({ menuItemId: "td-link", linkUrl: url, pageUrl: "https://trang.vn/" }, { id: 7 });
const message = (msg) => new Promise((r) => on.message(msg, {}, r));
let passed = 0;

// 1. App tắt, app từng báo chưa bật tdownload:// → trình duyệt tải ngay, có thông báo, không mở tab
reset({ protocol: false });
await menuLink("https://h.vn/a.zip");
assert.deepEqual(called("download").map((c) => c[1].url), ["https://h.vn/a.zip"]);
assert.equal(called("tabs.create").length, 0);
assert.equal(called("notify").length, 1);
assert.match(called("notify")[0][1].message, /Cho phép trình duyệt mở TDownload/);
passed++;

// 2. Giao thức đã đăng ký: mở tdownload:// ở tab tạm → app lên → gửi link sang app, đóng tab tạm
reset({ protocol: null });
launchOnOpen = true;
await menuLink("https://h.vn/b.zip");
assert.equal(called("tabs.create")[0][1].url, "tdownload://open?minimized=1");
assert.equal(called("tabs.create")[0][1].openerTabId, 7);
assert.deepEqual(added.map((a) => a.url), ["https://h.vn/b.zip"]);
assert.equal(called("download").length, 0);
assert.deepEqual(called("tabs.remove").map((c) => c[1]), [99]);
assert.equal(local.protocol, true);                 // nhớ lại cho lần sau
await stopApp();
passed++;

// 3. Chưa biết trạng thái, mở không được → chờ rồi trình duyệt tải, đóng tab tạm
reset({ protocol: null });
const t0 = Date.now();
await menuLink("https://h.vn/c.zip");
assert.ok(Date.now() - t0 >= 9000, "phải chờ app khởi động");
assert.deepEqual(called("download").map((c) => c[1].url), ["https://h.vn/c.zip"]);
assert.deepEqual(called("tabs.remove").map((c) => c[1]), [99]);
assert.equal(called("notify")[0][1].title, "Đã chuyển cho trình duyệt tải");
passed++;

// 4. Luồng HLS từ popup khi app tắt → không đưa cho trình duyệt (không tải được), báo lỗi
reset({ protocol: false });
const r = await message({ type: "sendMedia", url: "https://h.vn/x.m3u8", kind: "HLS", pageUrl: "https://h.vn/", tabId: 7 });
assert.deepEqual(r, { ok: false, status: "failed" });
assert.equal(called("download").length, 0);
assert.equal(called("notify")[0][1].title, "Chưa gửi được sang TDownload");
passed++;

// 5. App chạy nhưng không nhận link → trình duyệt tải; onCreated của chính lượt tải đó không bắt lại (không lặp)
reset({ protocol: true });
launchApp();
addFails = true;
await new Promise((r) => setTimeout(r, 200));
await menuLink("https://h.vn/d.zip");
assert.deepEqual(called("download").map((c) => c[1].url), ["https://h.vn/d.zip"]);
assert.equal(called("notify")[0][1].title, "Đã chuyển cho trình duyệt tải");
await on.created({ id: 5, url: "https://h.vn/d.zip", filename: "d.zip", state: "in_progress" });
assert.equal(called("cancel").length, 0);
assert.equal(added.length, 1);                      // chỉ lần gửi từ menu
await stopApp();
passed++;

console.log(`ext_harness: ${passed}/5 kịch bản qua`);
await new Promise((r) => setTimeout(r, 200));   // để socket đóng hẳn rồi mới thoát (bộ hẹn giờ huy hiệu 15 s)
process.exit(0);
