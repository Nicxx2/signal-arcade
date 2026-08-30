import "@testing-library/jest-dom/vitest";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class WebSocketStub {
  static OPEN = 1;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  close() {}
}

Object.assign(globalThis, {
  ResizeObserver: ResizeObserverStub,
  WebSocket: WebSocketStub,
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value() {},
});

const gradient = { addColorStop() {} } as unknown as CanvasGradient;
Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: () => ({
    scale() {},
    clearRect() {},
    createLinearGradient: () => gradient,
    beginPath() {},
    moveTo() {},
    lineTo() {},
    closePath() {},
    fill() {},
    stroke() {},
  }) as unknown as CanvasRenderingContext2D,
});
