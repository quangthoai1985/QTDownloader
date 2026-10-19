import { DEFAULTS, getCfg } from "./common.js";

const $ = (id) => document.getElementById(id);

const cfg = await getCfg();
$("port").value = cfg.port;
$("exts").value = cfg.exts;
$("minSize").value = cfg.minSizeKB;
$("exclude").value = cfg.excludeHosts;

$("save").onclick = async () => {
  const port = parseInt($("port").value, 10);
  await chrome.storage.sync.set({
    port: port >= 1024 && port <= 65535 ? port : DEFAULTS.port,
    exts: $("exts").value.trim() || DEFAULTS.exts,
    minSizeKB: Math.max(0, parseInt($("minSize").value, 10) || 0),
    excludeHosts: $("exclude").value.trim(),
  });
  $("msg").textContent = "Đã lưu ✓";
  setTimeout(() => ($("msg").textContent = ""), 2000);
};
