const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, createHooks } = require("./helpers.cjs");
const { panelBounds, clampPanelWidth, panelKeyboardWidth } = loadSource(
  "src/lib/assistant-panel.ts",
);

test("panel width leaves room for the canvas and remains bounded for narrow or invalid containers", () => {
  assert.equal(clampPanelWidth(600, 1000), 600);
  assert.equal(clampPanelWidth(10000, 1000), 632);
  assert.equal(clampPanelWidth(-300, 1000), 320);
  assert.equal(clampPanelWidth(NaN, 1000), 440);
  for (const size of [0, 200, 390, 800, 1400, NaN, -10]) {
    const bounds = panelBounds(size);
    assert.ok(bounds.min >= 0 && bounds.max >= bounds.min);
    assert.ok(bounds.max <= 760);
    const value = clampPanelWidth(10000, size);
    assert.ok(value <= bounds.max);
  }
});

test("keyboard arrows move the handle in the expected direction and Home/End respect limits", () => {
  assert.equal(panelKeyboardWidth("ArrowLeft", 440, 1000), 456);
  assert.equal(panelKeyboardWidth("ArrowRight", 440, 1000), 424);
  assert.equal(panelKeyboardWidth("ArrowLeft", 440, 1000, true), 504);
  assert.equal(panelKeyboardWidth("Home", 440, 1000), 320);
  assert.equal(panelKeyboardWidth("End", 440, 1000), 632);
  assert.equal(panelKeyboardWidth("Enter", 440, 1000), null);
});

function setup({ saved = null, blocked = false } = {}) {
  const hooks = createHooks();
  let containerWidth = 1000;
  let observer;
  let disconnected = false;
  const writes = [];
  let layoutAssigned = false;
  const element = { getBoundingClientRect: () => ({ width: containerWidth }) };
  const { useAssistantPanelResize } = loadSource(
    "src/lib/assistant-panel.ts",
    {
      react: {
        ...hooks.react,
        useRef(initial) {
          const ref = hooks.react.useRef(initial);
          if (!layoutAssigned) {
            ref.current = element;
            layoutAssigned = true;
          }
          return ref;
        },
      },
    },
    {
      window: {
        localStorage: {
          getItem: () => {
            if (blocked) throw new Error("disabled");
            return saved;
          },
          setItem: (key, value) => {
            if (blocked) throw new Error("disabled");
            writes.push([key, value]);
          },
        },
      },
      ResizeObserver: class {
        constructor(callback) {
          observer = callback;
        }
        observe(target) {
          assert.equal(target, element);
        }
        disconnect() {
          disconnected = true;
        }
      },
    },
  );
  const render = () => hooks.render(useAssistantPanelResize);
  render();
  return {
    render,
    writes,
    resize(value) {
      containerWidth = value;
      observer();
      return render();
    },
    cleanup() {
      hooks.cleanup();
      assert.equal(disconnected, true);
    },
  };
}

test("restored width clamps on resize but the preferred desktop width survives mobile layout", () => {
  const h = setup({ saved: "580" });
  assert.equal(h.render().separatorProps["aria-valuenow"], 580);
  assert.equal(h.resize(390).separatorProps["aria-valuenow"], 187);
  assert.equal(h.resize(1000).separatorProps["aria-valuenow"], 580);
  assert.equal(h.writes.length, 0);
  h.cleanup();
});

test("viewport resize during drag releases capture without persisting the mobile clamp as desktop preference", () => {
  const h = setup({ saved: "580" });
  let captured = null;
  const target = {
    focus() {},
    setPointerCapture: (id) => {
      captured = id;
    },
    hasPointerCapture: (id) => captured === id,
    releasePointerCapture: () => {
      captured = null;
    },
  };
  const event = (clientX = 700) => ({
    pointerId: 1,
    isPrimary: true,
    button: 0,
    clientX,
    currentTarget: target,
    preventDefault() {},
  });
  h.render().separatorProps.onPointerDown(event());
  h.render().separatorProps.onPointerMove(event(670));
  assert.equal(h.render().separatorProps["aria-valuenow"], 610);
  // ResizeObserver also delivers an initial or height-only callback; it must
  // not reset an in-progress drag when its width is unchanged.
  assert.equal(h.resize(1000).separatorProps["aria-valuenow"], 610);
  assert.equal(h.resize(390).dragging, false);
  assert.equal(captured, null);
  h.render().separatorProps.onLostPointerCapture(event());
  assert.equal(h.writes.length, 0);
  assert.equal(h.resize(1000).separatorProps["aria-valuenow"], 580);
  h.cleanup();
});

test("blocked or corrupt storage cannot prevent pointer and keyboard resizing", () => {
  for (const options of [
    { saved: "nonsense" },
    { saved: "-100" },
    { saved: "" },
    { blocked: true },
  ]) {
    const h = setup(options);
    let prevented = 0;
    h.render().separatorProps.onKeyDown({
      key: "ArrowLeft",
      shiftKey: false,
      preventDefault: () => prevented++,
    });
    assert.equal(h.render().separatorProps["aria-valuenow"], 456);
    assert.equal(prevented, 1);
    h.cleanup();
  }
});

test("pointer drag captures the pointer, ignores other pointers, and saves only when finished", () => {
  const h = setup();
  let captured = null;
  let released = null;
  let focused = false;
  const target = {
    focus: () => {
      focused = true;
    },
    setPointerCapture: (id) => {
      captured = id;
    },
    hasPointerCapture: (id) => captured === id,
    releasePointerCapture: (id) => {
      released = id;
      captured = null;
    },
  };
  const event = (extra = {}) => ({
    pointerId: 1,
    isPrimary: true,
    button: 0,
    clientX: 700,
    currentTarget: target,
    preventDefault() {},
    ...extra,
  });
  h.render().separatorProps.onPointerDown(event());
  assert.equal(captured, 1);
  assert.equal(focused, true);
  assert.equal(h.render().dragging, true);
  h.render().separatorProps.onPointerMove(
    event({ pointerId: 2, clientX: 300 }),
  );
  assert.equal(h.render().separatorProps["aria-valuenow"], 440);
  h.render().separatorProps.onPointerMove(event({ clientX: 610 }));
  assert.equal(h.render().separatorProps["aria-valuenow"], 530);
  assert.equal(h.writes.length, 0);
  h.render().separatorProps.onPointerUp(event());
  assert.equal(h.render().dragging, false);
  assert.equal(released, 1);
  assert.equal(h.writes.at(-1)[1], "530");
  h.render().separatorProps.onLostPointerCapture(event());
  assert.equal(h.writes.length, 1);
  h.cleanup();
});

test("cancellation stops a touch drag and nonprimary or secondary-button presses are ignored", () => {
  const h = setup();
  const target = {
    focus() {},
    setPointerCapture() {},
    hasPointerCapture: () => false,
  };
  const event = (extra = {}) => ({
    pointerId: 1,
    isPrimary: true,
    button: 0,
    clientX: 700,
    currentTarget: target,
    preventDefault() {},
    ...extra,
  });
  h.render().separatorProps.onPointerDown(event({ button: 2 }));
  h.render().separatorProps.onPointerDown(event({ isPrimary: false }));
  assert.equal(h.render().dragging, false);
  h.render().separatorProps.onPointerDown(event({ pointerType: "touch" }));
  h.render().separatorProps.onPointerCancel(event());
  assert.equal(h.render().dragging, false);
  h.render().separatorProps.onPointerMove(event({ clientX: 600 }));
  assert.equal(h.render().separatorProps["aria-valuenow"], 440);
  h.cleanup();
});
