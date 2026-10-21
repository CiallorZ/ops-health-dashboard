// Measure horizontal overflow and the certificate panel state on the live page.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

function parseArgs(argv) {
  const args = {
    cdp: "http://127.0.0.1:9223",
    width: 1440,
    height: 900,
    mobile: false,
    report: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--url") {
      args.url = value;
      index += 1;
    } else if (key === "--cdp") {
      args.cdp = value;
      index += 1;
    } else if (key === "--width") {
      args.width = Number(value);
      index += 1;
    } else if (key === "--height") {
      args.height = Number(value);
      index += 1;
    } else if (key === "--report") {
      args.report = value;
      index += 1;
    } else if (key === "--mobile") {
      args.mobile = true;
    }
  }
  if (!args.url) throw new Error("--url is required");
  return args;
}

class CdpClient {
  constructor(webSocketUrl) {
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket = new WebSocket(webSocketUrl);
  }

  async connect() {
    await new Promise((resolvePromise, reject) => {
      this.socket.addEventListener("open", resolvePromise, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      const handlers = this.listeners.get(message.method) ?? [];
      for (const handler of handlers.splice(0)) handler(message.params);
    });
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolvePromise, reject) => {
      this.pending.set(id, { resolve: resolvePromise, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  waitForEvent(method, timeoutMs = 15000) {
    return new Promise((resolvePromise, reject) => {
      const handlers = this.listeners.get(method) ?? [];
      const timeout = setTimeout(() => {
        reject(new Error(`Timed out waiting for ${method}`));
      }, timeoutMs);
      handlers.push((params) => {
        clearTimeout(timeout);
        resolvePromise(params);
      });
      this.listeners.set(method, handlers);
    });
  }

  close() {
    this.socket.close();
  }
}

async function createTarget(cdp, url) {
  const response = await fetch(`${cdp}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  });
  if (!response.ok) {
    throw new Error(`Could not create browser target: HTTP ${response.status}`);
  }
  return response.json();
}

const args = parseArgs(process.argv.slice(2));
const target = await createTarget(args.cdp, "about:blank");
const client = new CdpClient(target.webSocketDebuggerUrl);
await client.connect();

try {
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: args.width,
    height: args.height,
    deviceScaleFactor: 1,
    mobile: args.mobile,
    screenWidth: args.width,
    screenHeight: args.height,
  });
  if (args.mobile) {
    await client.send("Emulation.setTouchEmulationEnabled", {
      enabled: true,
      maxTouchPoints: 5,
    });
  }
  const loaded = client.waitForEvent("Page.loadEventFired");
  await client.send("Page.navigate", { url: args.url });
  await loaded;
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 4000));

  const metrics = await client.send("Runtime.evaluate", {
    expression: `(() => {
      const overflowing = [];
      for (const node of document.querySelectorAll("*")) {
        const rect = node.getBoundingClientRect();
        if (rect.width > 0 && (rect.right > window.innerWidth + 1 || rect.left < -1)) {
          overflowing.push(node.tagName.toLowerCase() + "." + (node.className || "").toString().slice(0, 40));
        }
      }
      const panel = document.querySelector("#certificate-panel");
      const policy = document.querySelector(".config-panel");
      return {
        viewport: window.innerWidth,
        scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        connection: document.querySelector("#connection")?.dataset.state ?? null,
        tracked: document.querySelector("#certificate-tracked")?.textContent ?? null,
        nearest: document.querySelector("#certificate-nearest")?.textContent ?? null,
        counts: document.querySelector("#certificate-counts")?.textContent ?? null,
        window: document.querySelector("#certificate-window")?.textContent ?? null,
        certRows: document.querySelectorAll("#certificate-list .certificate-row").length,
        certText: (panel?.innerText ?? "").slice(0, 400),
        retentionText: (policy?.innerText ?? "").slice(0, 500),
        retentionState: document.querySelector("#retention-state")?.textContent ?? null,
        overflowCount: overflowing.length,
        overflowSample: overflowing.slice(0, 6),
      };
    })()`,
    returnByValue: true,
    awaitPromise: true,
  });
  const result = metrics.result.value;
  if (args.report) {
    const output = resolve(args.report);
    await mkdir(dirname(output), { recursive: true });
    await writeFile(output, JSON.stringify(result, null, 2), "utf8");
  }
  console.log(JSON.stringify(result, null, 2));
} finally {
  client.close();
  await fetch(`${args.cdp}/json/close/${target.id}`, { method: "PUT" }).catch(() => {});
}
