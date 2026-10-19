import { fmtSize, getCfg, nameFromUrl, ping } from "./common.js";

const $ = (id) => document.getElementById(id);

async function main() {
  const cfg = await getCfg();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = "";
  try { host = new URL(tab.url).hostname; } catch { /* trang nội bộ */ }

  const info = await ping(cfg);
  $("status").textContent = info ? `đã kết nối · ${info.active} đang tải` : "chưa mở app";
  $("status").className = "status " + (info ? "ok" : "bad");

  $("enabled").checked = cfg.enabled;
  $("enabled").onchange = (e) => chrome.storage.sync.set({ enabled: e.target.checked });

  $("host").textContent = host || "(không áp dụng)";
  const excluded = cfg.excludeHosts.split(/[\s,]+/).filter(Boolean);
  $("exclude").checked = !!host && excluded.includes(host);
  $("exclude").disabled = !host;
  $("exclude").onchange = (e) => {
    const set = new Set(excluded);
    e.target.checked ? set.add(host) : set.delete(host);
    chrome.storage.sync.set({ excludeHosts: [...set].join(" ") });
  };

  const key = `media:${tab.id}`;
  const media = (await chrome.storage.session.get(key))[key] || [];
  const ul = $("media");
  if (media.length) ul.innerHTML = "";
  for (const m of media) {
    const li = document.createElement("li");
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = m.kind;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = nameFromUrl(m.url) || m.url;
    name.title = m.url;
    const size = document.createElement("span");
    size.className = "size";
    size.textContent = fmtSize(m.size);
    const btn = document.createElement("button");
    btn.className = "primary";
    btn.textContent = "Tải";
    if (m.kind === "DASH") {
      btn.disabled = true;
      btn.title = "DASH (.mpd) chưa hỗ trợ ghép";
    }
    btn.disabled = btn.disabled || !info;
    btn.onclick = async () => {
      btn.disabled = true;
      const title = (tab.title || "video").replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 80);
      const r = await chrome.runtime.sendMessage({
        type: "sendMedia", url: m.url, kind: m.kind, pageUrl: tab.url,
        filename: m.kind === "HLS" ? `${title}.ts` : "",
      });
      btn.textContent = r && r.ok ? "Đã gửi ✓" : "Lỗi";
    };
    li.append(kind, name, size, btn);
    ul.append(li);
  }

  $("all").disabled = !info || !/^https?:/.test(tab.url || "");
  $("all").onclick = async () => {
    $("all").disabled = true;
    const r = await chrome.runtime.sendMessage({ type: "sendAll", tab: { id: tab.id, url: tab.url } });
    $("all").textContent = r && r.ok ? "Đã gửi danh sách sang TDownload ✓" : "Không gửi được";
  };
  $("options").onclick = (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); };
}

main();
