type Size = { width: number; height: number };
type Options = {
  track: HTMLElement;
  stage: HTMLElement;
  canvas: HTMLCanvasElement;
  counter: HTMLOutputElement | null;
  copy?: HTMLElement | null;
};
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (value: number) => value * value * (3 - 2 * value);

/** Camera and animal travel independently; dimensions never depend on scroll zoom. */
export function getScenePose(
  progress: number,
  viewport: Size,
  background: Size,
  shrimp: Size,
) {
  const p = clamp(progress);
  const travel = clamp((p - 0.035) / 0.93);
  const camera = smooth(p);
  const scale = Math.max(
    viewport.width / background.width,
    (viewport.height * 2.4) / background.height,
  );
  const backgroundWidth = background.width * scale;
  const backgroundHeight = background.height * scale;
  const mobile = viewport.width < 761;
  const shrimpWidth = mobile
    ? viewport.width * 1.5
    : Math.min(viewport.width * 0.96, 1400);
  const shrimpHeight = (shrimpWidth * shrimp.height) / shrimp.width;
  const x =
    viewport.width * (0.88 - (mobile ? 1.8 : 1.5) * Math.pow(travel, 1.25));
  const y =
    viewport.height *
    (mobile ? 0.69 - 0.12 * travel : 0.54 + 0.09 * Math.sin(travel * Math.PI));
  const stroke = (p * 9) % 1;
  const pose = stroke < 0.5 ? stroke * 4 : (1 - stroke) * 4;
  const from = Math.min(1, Math.floor(pose));
  return {
    progress: p,
    background: {
      x: -(backgroundWidth - viewport.width) * (0.3 + 0.18 * camera),
      y: -(backgroundHeight - viewport.height) * camera,
      width: backgroundWidth,
      height: backgroundHeight,
    },
    shrimp: {
      x,
      y,
      width: shrimpWidth,
      height: shrimpHeight,
      rotation: -0.04 + 0.11 * Math.sin(travel * Math.PI * 1.6),
    },
    pose: { from, to: from + 1, blend: pose - from },
    label:
      p < 0.22 ? "水面" : p < 0.5 ? "潛入水下" : p < 0.82 ? "蝦隻游動" : "池底",
  };
}

export function createSwimScene({
  track,
  stage,
  canvas,
  counter,
  copy,
}: Options) {
  delete track.dataset.sceneError;
  const context = canvas.getContext("2d", { alpha: false });
  const mix = document.createElement("canvas");
  const mixContext = mix.getContext("2d");
  const assets: Array<HTMLImageElement | null> = [null, null, null, null];
  const loading: HTMLImageElement[] = [];
  let disposed = false;
  let inView = true;
  let raf = 0;
  let progress = 0;
  let lastPainted = -1;
  let resizeNeeded = true;
  let width = 0;
  let height = 0;

  function active() {
    return !disposed && inView && document.visibilityState === "visible";
  }
  function schedule() {
    if (!raf && active()) raf = requestAnimationFrame(render);
  }
  function update() {
    if (disposed) return;
    const distance = Math.max(1, track.offsetHeight - stage.offsetHeight);
    progress = clamp(-track.getBoundingClientRect().top / distance);
    canvas.dataset.targetProgress = progress.toFixed(4);
    schedule();
  }
  function render() {
    raf = 0;
    const background = assets[0];
    const fallback = assets.slice(1).find(Boolean);
    if (!active() || !context || !mixContext || !background || !fallback)
      return;
    if (lastPainted === progress && !resizeNeeded) return;
    if (resizeNeeded) {
      const box = canvas.getBoundingClientRect();
      width = box.width;
      height = box.height;
      if (!width || !height) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      mix.width = Math.min(1200, fallback.naturalWidth);
      mix.height = Math.round(
        (mix.width * fallback.naturalHeight) / fallback.naturalWidth,
      );
      resizeNeeded = false;
    }
    const pose = getScenePose(
      progress,
      { width, height },
      { width: background.naturalWidth, height: background.naturalHeight },
      { width: fallback.naturalWidth, height: fallback.naturalHeight },
    );
    const bg = pose.background;
    context.drawImage(background, bg.x, bg.y, bg.width, bg.height);

    // Add premultiplied sprite colors on a transparent buffer. A normal source-over
    // crossfade would make the animal translucent where the poses overlap.
    mixContext.clearRect(0, 0, mix.width, mix.height);
    mixContext.globalCompositeOperation = "source-over";
    mixContext.globalAlpha = 1 - pose.pose.blend;
    mixContext.drawImage(
      assets[pose.pose.from + 1] || fallback,
      0,
      0,
      mix.width,
      mix.height,
    );
    mixContext.globalCompositeOperation = "lighter";
    mixContext.globalAlpha = pose.pose.blend;
    mixContext.drawImage(
      assets[pose.pose.to + 1] || fallback,
      0,
      0,
      mix.width,
      mix.height,
    );
    mixContext.globalAlpha = 1;
    mixContext.globalCompositeOperation = "source-over";
    context.save();
    context.translate(pose.shrimp.x, pose.shrimp.y);
    context.rotate(pose.shrimp.rotation);
    context.drawImage(
      mix,
      -pose.shrimp.width / 2,
      -pose.shrimp.height / 2,
      pose.shrimp.width,
      pose.shrimp.height,
    );
    context.restore();
    lastPainted = progress;
    canvas.dataset.ready = "true";
    canvas.dataset.progress = progress.toFixed(4);
    canvas.dataset.cameraY = bg.y.toFixed(1);
    canvas.dataset.shrimpX = pose.shrimp.x.toFixed(1);
    canvas.dataset.pose = `${pose.pose.from}:${pose.pose.to}`;
    if (counter) counter.value = pose.label;
    if (copy) {
      copy.style.opacity = String(clamp((0.32 - progress) / 0.2));
      copy.inert = progress >= 0.32;
    }
  }
  const paths = [
    "ocean-depth.webp",
    "shrimp-01.webp",
    "shrimp-02.webp",
    "shrimp-03.webp",
  ];
  let failures = 0;
  paths.forEach((path, index) => {
    const image = new window.Image();
    image.decoding = "async";
    loading.push(image);
    image.onload = () => {
      if (disposed) return;
      assets[index] = image;
      lastPainted = -1;
      schedule();
    };
    image.onerror = () => {
      if (disposed) return;
      failures++;
      if (index === 0 || (failures === 3 && !assets.slice(1).some(Boolean)))
        track.dataset.sceneError = "true";
    };
    image.src = `/images/swim/${path}`;
  });
  const resize = new ResizeObserver(() => {
    resizeNeeded = true;
    update();
  });
  resize.observe(stage);
  resize.observe(canvas);
  const intersection = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    if (active()) update();
    else if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  });
  intersection.observe(track);
  const onVisibility = () => {
    if (active()) update();
    else if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };
  document.addEventListener("visibilitychange", onVisibility);
  return {
    update,
    destroy() {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      resize.disconnect();
      intersection.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      loading.forEach((image) => {
        image.onload = null;
        image.onerror = null;
      });
      assets.fill(null);
      mix.width = 0;
      mix.height = 0;
      delete canvas.dataset.ready;
      if (copy) {
        copy.style.removeProperty("opacity");
        copy.inert = false;
      }
    },
  };
}
