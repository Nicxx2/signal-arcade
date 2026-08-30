import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const cdpPort = process.env.SIGNAL_ARCADE_CAPTURE_CDP_PORT ?? "9333";
const password = process.env.SIGNAL_ARCADE_CAPTURE_PASSWORD;
const outputDirectory = process.env.SIGNAL_ARCADE_CAPTURE_OUTPUT;

if (!password || !outputDirectory) {
  throw new Error("capture password and output directory are required");
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const targets = await fetch(`http://127.0.0.1:${cdpPort}/json/list`).then((response) => response.json());
const pageTarget = targets.find((target) => target.type === "page");
if (!pageTarget?.webSocketDebuggerUrl) throw new Error("headless Chrome page target was not found");

const socket = new WebSocket(pageTarget.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id) return;
  const waiter = pending.get(message.id);
  if (!waiter) return;
  pending.delete(message.id);
  if (message.error) waiter.reject(new Error(`${waiter.method}: ${message.error.message}`));
  else waiter.resolve(message.result ?? {});
});

function send(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, { method, resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression, returnByValue = true) {
  const result = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "page evaluation failed");
  return result.result?.value;
}

async function waitFor(expression, timeoutMilliseconds = 15_000) {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() < deadline) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await wait(150);
  }
  throw new Error(`timed out waiting for ${expression}`);
}

async function setViewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
}

async function clickButton(label) {
  const clicked = await evaluate(`(() => {
    const button = [...document.querySelectorAll("button")]
      .find((item) => item.textContent.trim() === ${JSON.stringify(label)});
    if (!button) return false;
    button.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`button not found: ${label}`);
  await wait(700);
}

async function preparePage() {
  await evaluate(`(() => {
    window.scrollTo(0, 0);
    document.querySelectorAll(".token-card, .decision-row, .decision-board-row, .leaderboard-row, .fill-row")
      .forEach((element) => {
        if (/\\b(fuck|fucking|shit|bitch|cunt)\\b/i.test(element.textContent || "")) {
          element.style.display = "none";
          element.dataset.readmeHidden = "true";
        }
      });
    document.querySelectorAll("[role=dialog]").forEach((dialog) => {
      dialog.style.display = "none";
    });
  })()`);
  await evaluate("document.fonts?.ready ?? Promise.resolve()");
  await wait(350);
}

async function captureViewport(filename) {
  await preparePage();
  const visibleProfanity = await evaluate(`(() => {
    const viewportHeight = window.innerHeight;
    return [...document.querySelectorAll("body *")].some((element) => {
      if (element.children.length > 0) return false;
      const rect = element.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= viewportHeight || rect.width === 0 || rect.height === 0) return false;
      return /\\b(fuck|fucking|shit|bitch|cunt)\\b/i.test(element.textContent || "");
    });
  })()`);
  if (visibleProfanity) throw new Error(`refusing to capture visible profanity in ${filename}`);
  const { data } = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(outputDirectory, filename), Buffer.from(data, "base64"));
}

async function captureElement(selector, filename, maximumHeight = 1_200) {
  await evaluate(`(() => {
    const header = document.querySelector("header");
    if (!header) return;
    header.dataset.readmeOriginalStyle = header.getAttribute("style") ?? "";
    header.style.position = "static";
    header.style.top = "auto";
  })()`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)})?.scrollIntoView({block:"start"})`);
  await wait(350);
  const clip = await evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {
      x: Math.max(0, rect.left + window.scrollX),
      y: Math.max(0, rect.top + window.scrollY),
      width: Math.min(document.documentElement.scrollWidth, rect.width),
      height: Math.min(${maximumHeight}, rect.height),
      scale: 1,
    };
  })()`);
  if (!clip) throw new Error(`element not found: ${selector}`);
  const text = await evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? ""`);
  if (/\b(fuck|fucking|shit|bitch|cunt)\b/i.test(text)) {
    throw new Error(`refusing to capture profanity in ${filename}`);
  }
  const { data } = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: true,
    clip,
  });
  await writeFile(path.join(outputDirectory, filename), Buffer.from(data, "base64"));
  await evaluate(`(() => {
    const header = document.querySelector("header");
    if (!header) return;
    const original = header.dataset.readmeOriginalStyle ?? "";
    if (original) header.setAttribute("style", original);
    else header.removeAttribute("style");
    delete header.dataset.readmeOriginalStyle;
  })()`);
}

await mkdir(outputDirectory, { recursive: true });
await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
await send("Network.setExtraHTTPHeaders", {
  headers: {
    Authorization: `Basic ${Buffer.from(`signal-arcade:${password}`).toString("base64")}`,
  },
});
await setViewport(1440, 920);
await send("Page.navigate", { url: "http://127.0.0.1:8765/" });
await waitFor("document.readyState === 'complete'");
await waitFor("document.querySelector('main') && document.body.innerText.includes('Paper equity')");
await wait(1_000);

await clickButton("Arena");
await captureViewport("01-arena-overview.png");

await clickButton("Decisions");
await waitFor("document.body.innerText.includes('Best signals first')");
await captureViewport("02-decision-board.png");

await clickButton("Results");
await clickButton("Seasons");
await waitFor("document.body.innerText.includes('Is the strategy improving each season?')");
await captureViewport("03-season-progress.png");

await clickButton("Learning");
await waitFor("document.body.innerText.includes('Learning')");
await captureViewport("04-learning-lab.png");

await clickButton("Replay");
await waitFor("document.body.innerText.includes('The score is net of the friction.')");
await captureViewport("08-replay-receipts.png");

await clickButton("Settings");
await waitFor("document.body.innerText.includes('Data providers')");
await evaluate(`(() => {
  const section = document.querySelector(".provider-manager");
  const button = section && [...section.querySelectorAll("button")]
    .find((item) => item.textContent.trim() === "Show");
  button?.click();
})()`);
await wait(500);
await captureElement(".provider-manager", "05-data-providers.png", 900);

await evaluate(`(() => {
  const section = document.querySelector(".ai-model-manager");
  const button = section && [...section.querySelectorAll("button")]
    .find((item) => item.textContent.trim() === "Show");
  button?.click();
})()`);
await wait(500);
await captureElement(".ai-model-manager", "06-local-ai.png", 1_050);

await setViewport(430, 932, true);
await clickButton("Arena");
await captureViewport("07-mobile-arena.png");

socket.close();
console.log("Captured 8 Signal Arcade README screenshots.");
