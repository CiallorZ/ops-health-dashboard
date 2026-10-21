import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

function parseArgs(argv) {
  const args = {
    cdp: "http://127.0.0.1:9223",
    width: 1440,
    height: 900,
    mobile: false,
    waitFor: "",
    captureHeight: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--url") {
      args.url = value;
      index += 1;
    } else if (key === "--output") {
      args.output = value;
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
    } else if (key === "--capture-height") {
      args.captureHeight = Number(value);
      index += 1;
    } else if (key === "--mobile") {
      args.mobile = true;
    } else if (key === "--wait-for") {
      args.waitFor = value;
      index += 1;
    }
  }
  if (!args.url || !args.output) {
    throw new Error("--url and --output are required");
  }
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

  waitForEvent(method, timeoutMs = 10000) {
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
  const response = await fetch(
    `${cdp}/json/new?${encodeURIComponent(url)}`,
    { method: "PUT" },
  );
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

  if (args.waitFor) {
    await client.send("Runtime.evaluate", {
      expression: args.waitFor,
      awaitPromise: true,
      returnByValue: true,
    });
  }
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 1200));

  const metrics = await client.send("Runtime.evaluate", {
    expression: `({
      width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
      viewport: window.innerWidth,
      state: document.querySelector("#connection")?.dataset.state ?? null
    })`,
    returnByValue: true,
  });
  const page = metrics.result.value;
  const captureHeight = args.captureHeight
    ? Math.min(page.height, args.captureHeight)
    : page.height;
  const screenshot = await client.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
    fromSurface: true,
    clip: {
      x: 0,
      y: 0,
      width: args.width,
      height: captureHeight,
      scale: 1,
    },
  });
  const output = resolve(args.output);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, Buffer.from(screenshot.data, "base64"));
  console.log(JSON.stringify({
    output,
    width: args.width,
    height: captureHeight,
    fullPageHeight: page.height,
    scrollWidth: page.width,
    viewport: page.viewport,
    connectionState: page.state,
  }));
} finally {
  client.close();
  await fetch(`${args.cdp}/json/close/${target.id}`, { method: "PUT" }).catch(() => {});
}
