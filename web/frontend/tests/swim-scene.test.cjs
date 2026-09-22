const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource } = require("./helpers.cjs");

const backgroundSize = { width: 1024, height: 2048 };
const shrimpSize = { width: 1280, height: 768 };
const { getScenePose } = loadSource("src/lib/swim-scene.ts");
const plain = (value) => JSON.parse(JSON.stringify(value));

function assertCoverage(rect, viewport) {
  const epsilon = 1e-8;
  assert.ok(rect.x <= epsilon && rect.y <= epsilon);
  assert.ok(rect.x + rect.width >= viewport.width - epsilon);
  assert.ok(rect.y + rect.height >= viewport.height - epsilon);
}

function setup() {
  const frames = new Map();
  const requests = [];
  const operations = [];
  const listeners = new Map();
  const resizeObservers = [];
  const intersectionObservers = [];
  const mixCanvases = [];
  let nextRaf = 1;
  let top = 0;
  let box = { width: 1000, height: 600 };
  let controller;

  function context(name) {
    return {
      globalAlpha: 1,
      globalCompositeOperation: "source-over",
      setTransform(...args) {
        operations.push({ name, type: "setTransform", args });
      },
      drawImage(image, ...args) {
        operations.push({
          name,
          type: "drawImage",
          image,
          args,
          alpha: this.globalAlpha,
          composite: this.globalCompositeOperation,
        });
      },
      clearRect(...args) {
        operations.push({ name, type: "clearRect", args });
      },
      save() {
        operations.push({ name, type: "save" });
      },
      restore() {
        operations.push({ name, type: "restore" });
      },
      translate(...args) {
        operations.push({ name, type: "translate", args });
      },
      rotate(...args) {
        operations.push({ name, type: "rotate", args });
      },
    };
  }
  class Image {
    constructor() {
      this.onload = null;
      this.onerror = null;
      this.finished = false;
    }
    set src(value) {
      this.url = value;
      const size = value.endsWith("ocean-depth.webp")
        ? backgroundSize
        : shrimpSize;
      this.naturalWidth = size.width;
      this.naturalHeight = size.height;
      requests.push(this);
    }
    get src() {
      return this.url;
    }
    complete(failed = false) {
      assert.equal(this.finished, false);
      this.finished = true;
      if (failed) this.onerror?.();
      else this.onload?.();
    }
  }
  const observer = (list) =>
    class {
      constructor(callback) {
        this.callback = callback;
        this.disconnected = false;
        this.targets = [];
        list.push(this);
      }
      observe(target) {
        this.targets.push(target);
      }
      disconnect() {
        this.disconnected = true;
      }
      notify(entries = []) {
        this.callback(entries);
      }
    };
  const document = {
    visibilityState: "visible",
    createElement(tag) {
      assert.equal(tag, "canvas");
      const drawing = context("mix");
      const canvas = {
        width: 300,
        height: 150,
        context: drawing,
        getContext: () => drawing,
      };
      mixCanvases.push(canvas);
      return canvas;
    },
    addEventListener(name, callback) {
      assert.equal(listeners.has(name), false, "avoid duplicate listeners");
      listeners.set(name, callback);
    },
    removeEventListener(name, callback) {
      assert.equal(listeners.get(name), callback);
      listeners.delete(name);
    },
  };
  const track = {
    dataset: {},
    offsetHeight: 1890,
    getBoundingClientRect: () => ({ top }),
  };
  const stage = { offsetHeight: 700 };
  const mainContext = context("main");
  const canvas = {
    width: 300,
    height: 150,
    dataset: {},
    getBoundingClientRect: () => box,
    getContext: () => mainContext,
  };
  const counter = { value: "水面" };
  const copy = {
    inert: false,
    style: {
      opacity: "",
      removeProperty(name) {
        this[name] = "";
      },
    },
  };
  const { createSwimScene } = loadSource(
    "src/lib/swim-scene.ts",
    {},
    {
      document,
      window: { Image, devicePixelRatio: 3 },
      ResizeObserver: observer(resizeObservers),
      IntersectionObserver: observer(intersectionObservers),
      requestAnimationFrame(callback) {
        const id = nextRaf++;
        frames.set(id, callback);
        return id;
      },
      cancelAnimationFrame: (id) => frames.delete(id),
    },
  );
  function create() {
    controller = createSwimScene({ track, stage, canvas, counter, copy });
    return controller;
  }
  create();
  function runRaf() {
    const callbacks = [...frames.values()];
    frames.clear();
    callbacks.forEach((callback) => callback(0));
  }
  return {
    get controller() {
      return controller;
    },
    create,
    canvas,
    track,
    counter,
    copy,
    operations,
    mixCanvases,
    requests,
    frames,
    listeners,
    resizeObservers,
    intersectionObservers,
    runRaf,
    completeResources(shouldFail = () => false) {
      requests
        .filter((request) => !request.finished)
        .forEach((request) => request.complete(shouldFail(request)));
      runRaf();
    },
    scrollTo(progress) {
      top = -progress * (track.offsetHeight - stage.offsetHeight);
      controller.update();
    },
    resize(width, height) {
      box = { width, height };
      resizeObservers.at(-1).notify();
    },
    intersect(visible) {
      intersectionObservers.at(-1).notify([{ isIntersecting: visible }]);
    },
    visibility(visible) {
      document.visibilityState = visible ? "visible" : "hidden";
      listeners.get("visibilitychange")?.();
    },
  };
}

test("camera and shrimp visibly travel in opposite screen directions without scroll zoom", () => {
  for (const viewport of [
    { width: 1264, height: 712 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
    { width: 2560, height: 1080 },
  ]) {
    const start = getScenePose(0, viewport, backgroundSize, shrimpSize);
    const middle = getScenePose(0.5, viewport, backgroundSize, shrimpSize);
    const end = getScenePose(1, viewport, backgroundSize, shrimpSize);
    assert.ok(start.shrimp.x - end.shrimp.x > viewport.width);
    assert.ok(start.background.y - end.background.y > viewport.height);
    assert.ok(
      middle.shrimp.x < start.shrimp.x && middle.shrimp.x > end.shrimp.x,
    );
    assert.ok(
      middle.background.y < start.background.y &&
        middle.background.y > end.background.y,
    );
    for (const pose of [middle, end]) {
      assert.equal(pose.shrimp.width, start.shrimp.width);
      assert.equal(pose.shrimp.height, start.shrimp.height);
      assert.equal(pose.background.width, start.background.width);
      assert.equal(pose.background.height, start.background.height);
    }
    assert.ok(
      middle.shrimp.x > 0 && middle.shrimp.x < viewport.width,
      "animal center is visible midway on mobile and desktop",
    );
  }
});

test("background fully covers portrait, landscape and ultrawide canvases at every camera position", () => {
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 844, height: 390 },
    { width: 1264, height: 712 },
    { width: 585, height: 604 },
    { width: 3440, height: 1440 },
  ]) {
    for (let step = 0; step <= 100; step++) {
      const pose = getScenePose(
        step / 100,
        viewport,
        backgroundSize,
        shrimpSize,
      );
      assertCoverage(pose.background, viewport);
      assert.ok(pose.pose.from >= 0 && pose.pose.to <= 2);
      assert.ok(pose.pose.blend >= 0 && pose.pose.blend <= 1);
      assert.ok(Number.isFinite(pose.shrimp.rotation));
    }
  }
});

test("pose mapping clamps endpoints and exactly reverses when returning to the same progress", () => {
  const viewport = { width: 1264, height: 712 };
  const get = (progress) =>
    plain(getScenePose(progress, viewport, backgroundSize, shrimpSize));
  assert.deepEqual(get(-1), get(0));
  assert.deepEqual(get(2), get(1));
  const forward = [0, 0.13, 0.48, 0.72, 1].map(get);
  const reverse = [1, 0.72, 0.48, 0.13, 0].map(get).reverse();
  assert.deepEqual(reverse, forward);
});

test("each repaint covers the old image then blends transparent sprites on a cleared buffer", () => {
  const scene = setup();
  scene.completeResources();
  scene.operations.length = 0;
  scene.scrollTo(0.04);
  scene.runRaf();
  const first = scene.operations[0];
  assert.equal(first.name, "main");
  assert.equal(first.type, "drawImage");
  assert.ok(first.image.url.endsWith("ocean-depth.webp"));
  assert.equal(first.alpha, 1);
  assert.equal(first.composite, "source-over");
  assertCoverage(
    {
      x: first.args[0],
      y: first.args[1],
      width: first.args[2],
      height: first.args[3],
    },
    { width: 1000, height: 600 },
  );

  const mixOperations = scene.operations.filter(
    (operation) => operation.name === "mix",
  );
  assert.equal(mixOperations[0].type, "clearRect");
  assert.deepEqual(mixOperations[0].args, [0, 0, 1200, 720]);
  const mixedImages = mixOperations.filter(
    (operation) => operation.type === "drawImage",
  );
  assert.equal(mixedImages.length, 2);
  assert.equal(mixedImages[0].composite, "source-over");
  assert.equal(mixedImages[1].composite, "lighter");
  assert.ok(
    mixedImages.every(
      (operation) => operation.alpha > 0 && operation.alpha < 1,
    ),
  );
  assert.equal(mixedImages[0].alpha + mixedImages[1].alpha, 1);
  assert.equal(scene.mixCanvases[0].context.globalAlpha, 1);
  assert.equal(
    scene.mixCanvases[0].context.globalCompositeOperation,
    "source-over",
  );
  const mainDraws = scene.operations.filter(
    (operation) => operation.name === "main" && operation.type === "drawImage",
  );
  assert.equal(mainDraws.length, 2);
  assert.equal(mainDraws[1].image, scene.mixCanvases[0]);
  assert.equal(scene.operations.at(-1).type, "restore");
  scene.controller.destroy();
});

test("render diagnostics describe actual painted transforms and reverse with scrolling", () => {
  const scene = setup();
  scene.completeResources();
  for (const progress of [0, 0.5, 1, 0.5, 0]) {
    scene.operations.length = 0;
    scene.scrollTo(progress);
    scene.runRaf();
    const expected = getScenePose(
      progress,
      { width: 1000, height: 600 },
      backgroundSize,
      shrimpSize,
    );
    assert.equal(scene.canvas.dataset.progress, progress.toFixed(4));
    assert.equal(
      scene.canvas.dataset.cameraY,
      expected.background.y.toFixed(1),
    );
    assert.equal(scene.canvas.dataset.shrimpX, expected.shrimp.x.toFixed(1));
    const translation = scene.operations.find(
      (operation) => operation.type === "translate",
    );
    if (translation)
      assert.deepEqual(translation.args, [
        expected.shrimp.x,
        expected.shrimp.y,
      ]);
    assert.equal(scene.counter.value, expected.label);
  }
  scene.controller.destroy();
});

test("pending scroll updates coalesce and a still scene does not loop RAF or redraw", () => {
  const scene = setup();
  assert.equal(
    scene.requests.length,
    4,
    "load only the fixed background and three poses",
  );
  scene.completeResources();
  assert.equal(scene.frames.size, 0);
  scene.operations.length = 0;
  scene.controller.update();
  scene.controller.update();
  scene.controller.update();
  assert.equal(scene.frames.size, 1);
  scene.runRaf();
  assert.equal(scene.operations.length, 0);
  assert.equal(scene.frames.size, 0);
  assert.equal(scene.requests.length, 4);
  scene.controller.destroy();
});

test("resize redraws unchanged progress at capped DPR and resizes the transparent buffer", () => {
  const scene = setup();
  scene.completeResources();
  assert.equal(scene.canvas.width, 1500);
  assert.equal(scene.canvas.height, 900);
  scene.operations.length = 0;
  scene.resize(390, 844);
  scene.runRaf();
  assert.equal(scene.canvas.width, 585);
  assert.equal(scene.canvas.height, 1266);
  assert.deepEqual(scene.operations[0], {
    name: "main",
    type: "setTransform",
    args: [1.5, 0, 0, 1.5, 0, 0],
  });
  const draw = scene.operations.find(
    (operation) => operation.name === "main" && operation.type === "drawImage",
  );
  assertCoverage(
    {
      x: draw.args[0],
      y: draw.args[1],
      width: draw.args[2],
      height: draw.args[3],
    },
    { width: 390, height: 844 },
  );
  assert.equal(scene.canvas.dataset.progress, "0.0000");
  scene.controller.destroy();
});

test("failed poses use a successfully loaded transparent sprite without blanking the scene", () => {
  const scene = setup();
  scene.completeResources((request) => /shrimp-0[23]/.test(request.url));
  scene.scrollTo(0.04);
  scene.runRaf();
  assert.equal(scene.canvas.dataset.ready, "true");
  assert.equal(scene.track.dataset.sceneError, undefined);
  const sprites = scene.operations.filter(
    (operation) => operation.name === "mix" && operation.type === "drawImage",
  );
  assert.ok(sprites.length > 0);
  assert.ok(
    sprites.every((operation) =>
      operation.image.url.endsWith("shrimp-01.webp"),
    ),
  );
  scene.controller.destroy();
});

test("background failure or all pose failures retain the poster and flag the shortened static scene", () => {
  for (const shouldFail of [
    (request) => request.url.endsWith("ocean-depth.webp"),
    (request) => request.url.includes("shrimp-"),
  ]) {
    const scene = setup();
    scene.completeResources(shouldFail);
    assert.equal(scene.canvas.dataset.ready, undefined);
    assert.equal(scene.track.dataset.sceneError, "true");
    assert.equal(
      scene.operations.some((operation) => operation.type === "drawImage"),
      false,
    );
    assert.equal(scene.frames.size, 0);
    scene.controller.destroy();
  }
});

test("reinitializing the same DOM after a failed load clears the static-scene error flag", () => {
  const scene = setup();
  scene.completeResources((request) =>
    request.url.endsWith("ocean-depth.webp"),
  );
  assert.equal(scene.track.dataset.sceneError, "true");
  scene.controller.destroy();
  scene.create();
  scene.completeResources();
  assert.equal(scene.canvas.dataset.ready, "true");
  assert.equal(scene.track.dataset.sceneError, undefined);
  scene.controller.destroy();
});

test("offscreen or hidden scenes stop painting and resume at the latest target position", () => {
  const scene = setup();
  scene.intersect(false);
  scene.completeResources();
  assert.equal(scene.operations.length, 0);
  assert.equal(scene.frames.size, 0);
  scene.scrollTo(0.5);
  assert.equal(scene.canvas.dataset.targetProgress, "0.5000");
  assert.equal(scene.canvas.dataset.progress, undefined);
  scene.intersect(true);
  scene.runRaf();
  assert.equal(scene.canvas.dataset.progress, "0.5000");
  scene.operations.length = 0;
  scene.visibility(false);
  scene.scrollTo(1);
  assert.equal(scene.frames.size, 0);
  assert.equal(scene.operations.length, 0);
  scene.visibility(true);
  scene.runRaf();
  assert.equal(scene.canvas.dataset.progress, "1.0000");
  scene.controller.destroy();
});

test("destroy removes listeners, cancels RAF and makes late asset callbacks harmless", () => {
  const scene = setup();
  const lateLoad = scene.requests[0].onload;
  const lateError = scene.requests[1].onerror;
  scene.controller.update();
  assert.equal(scene.frames.size, 1);
  scene.controller.destroy();
  assert.equal(scene.frames.size, 0);
  assert.equal(scene.listeners.size, 0);
  assert.ok(scene.resizeObservers[0].disconnected);
  assert.ok(scene.intersectionObservers[0].disconnected);
  assert.ok(
    scene.requests.every(
      (request) => request.onload === null && request.onerror === null,
    ),
  );
  assert.equal(scene.mixCanvases[0].width, 0);
  assert.equal(scene.mixCanvases[0].height, 0);
  lateLoad();
  lateError();
  scene.controller.update();
  assert.equal(scene.frames.size, 0);
  assert.equal(scene.operations.length, 0);
  assert.equal(scene.canvas.dataset.ready, undefined);
  assert.equal(scene.track.dataset.sceneError, undefined);
});

test("the entire rotated shrimp exits the left edge at the end on desktop and mobile", () => {
  const actualSpriteSize = { width: 1536, height: 1024 };
  for (const viewport of [
    { width: 320, height: 568 },
    { width: 390, height: 844 },
    { width: 585, height: 604 },
    { width: 760, height: 1024 },
    { width: 761, height: 1024 },
    { width: 1264, height: 712 },
    { width: 2560, height: 1080 },
  ]) {
    const { shrimp } = getScenePose(
      1,
      viewport,
      backgroundSize,
      actualSpriteSize,
    );
    const cosine = Math.cos(shrimp.rotation);
    const sine = Math.sin(shrimp.rotation);
    const corners = [
      [-shrimp.width / 2, -shrimp.height / 2],
      [shrimp.width / 2, -shrimp.height / 2],
      [shrimp.width / 2, shrimp.height / 2],
      [-shrimp.width / 2, shrimp.height / 2],
    ];
    const rightEdge = Math.max(
      ...corners.map(([x, y]) => shrimp.x + x * cosine - y * sine),
    );
    assert.ok(
      rightEdge < 0,
      `rotated sprite still reaches ${rightEdge}px at width ${viewport.width}`,
    );
  }
});

test("copy fades out accessibly, reverses with scroll, and restores on destroy", () => {
  const scene = setup();
  scene.completeResources();
  assert.equal(scene.copy.style.opacity, "1");
  assert.equal(scene.copy.inert, false);

  scene.scrollTo(0.22);
  scene.runRaf();
  const partialOpacity = Number(scene.copy.style.opacity);
  assert.ok(partialOpacity > 0 && partialOpacity < 1);
  assert.equal(scene.copy.inert, false);
  for (const progress of [0.32, 0.8]) {
    scene.scrollTo(progress);
    scene.runRaf();
    assert.equal(scene.copy.style.opacity, "0");
    assert.equal(scene.copy.inert, true);
  }

  scene.scrollTo(0.22);
  scene.runRaf();
  assert.equal(Number(scene.copy.style.opacity), partialOpacity);
  assert.equal(scene.copy.inert, false);
  scene.scrollTo(0);
  scene.runRaf();
  assert.equal(scene.copy.style.opacity, "1");
  assert.equal(scene.copy.inert, false);

  scene.scrollTo(0.8);
  scene.runRaf();
  scene.controller.destroy();
  assert.equal(scene.copy.style.opacity, "");
  assert.equal(scene.copy.inert, false);
});
