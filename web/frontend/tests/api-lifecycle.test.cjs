const test = require("node:test");
const assert = require("node:assert/strict");
const {
  loadSource,
  createHooks,
  elements,
  flush,
  deferred,
} = require("./helpers.cjs");
const response = (body, status = 200) =>
  new Response(JSON.stringify(body), { status });
const session = (token = "fresh-token", limit = 1024) => ({
  csrf_token: token,
  max_upload_bytes: limit,
});

function setup(fetch = async () => response(session())) {
  const requests = [];
  class XHR {
    constructor() {
      this.upload = {};
      this.headers = {};
      this.aborts = 0;
      this.sent = false;
      requests.push(this);
    }
    open(method, url) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(name, value) {
      this.headers[name] = value;
    }
    send(data) {
      this.data = data;
      this.sent = true;
    }
    abort() {
      this.aborts++;
      this.onabort?.();
    }
    complete(body = { id: "job-created" }, status = 202) {
      this.status = status;
      this.responseText = JSON.stringify(body);
      this.onload();
    }
  }
  return {
    requests,
    api: loadSource("src/lib/api.ts", {}, { fetch, XMLHttpRequest: XHR }),
  };
}
function video(size = 4) {
  const form = new FormData();
  form.append("file", new Blob(["x".repeat(size)]), "video.mp4");
  return form;
}

test("every POST fetches a fresh no-store session and sends its CSRF token", async () => {
  const calls = [];
  let tokens = 0;
  const { api } = setup(async (url, options) => {
    calls.push({ url, options });
    return response(
      url.endsWith("/session")
        ? session(`token-${++tokens}`)
        : { id: "result" },
    );
  });
  await api.retryJob("first");
  await api.retryJob("second");
  await api.getJob("third");
  assert.equal(calls.length, 5);
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(calls[2].options.cache, "no-store");
  assert.equal(calls[1].options.headers.get("X-Tide-CSRF"), "token-1");
  assert.equal(calls[3].options.headers.get("X-Tide-CSRF"), "token-2");
  assert.equal(calls[4].options.headers.has("X-Tide-CSRF"), false);
});

test("aborting api POST bootstrap prevents a write even if its session resolves late", async () => {
  const pending = deferred(),
    calls = [];
  const { api } = setup((url, options) => {
    calls.push({ url, options });
    return pending.promise;
  });
  const controller = new AbortController();
  const request = api.api("/jobs/one/retry", {
    method: "POST",
    signal: controller.signal,
  });
  const rejected = assert.rejects(
    request,
    (error) => error.name === "AbortError",
  );
  controller.abort();
  pending.resolve(response(session()));
  await rejected;
  assert.equal(calls.length, 1);
});

test("cancel upload during bootstrap never creates or sends XHR after a late token", async () => {
  const pending = deferred();
  let signal;
  const { api, requests } = setup((_url, options) => {
    signal = options.signal;
    return pending.promise;
  });
  const operation = api.uploadJob(video(), () => {});
  const rejected = assert.rejects(
    operation.promise,
    (error) => error.outcome === "not-sent",
  );
  assert.equal(operation.cancel(), true);
  await rejected;
  assert.equal(signal.aborted, true);
  pending.resolve(response(session()));
  await flush();
  assert.equal(requests.length, 0);
});

test("failed session and oversize video both stop before any upload", async () => {
  for (const getResponse of [
    () => response({ detail: "Forbidden" }, 403),
    () => response(session("size-token", 3)),
  ]) {
    const { api, requests } = setup(async () => getResponse());
    await assert.rejects(
      api.uploadJob(video(4), () => {}).promise,
      (error) => error.outcome === "not-sent",
    );
    assert.equal(requests.length, 0);
  }
});

test("progress rounding never completes transport; only upload.onload disables cancel", async () => {
  const phases = [],
    progress = [];
  const { api, requests } = setup();
  const operation = api.uploadJob(
    video(),
    (value) => progress.push(value),
    (phase) => phases.push(phase),
  );
  await flush();
  const xhr = requests[0];
  assert.equal(xhr.sent, true);
  assert.equal(xhr.headers["X-Tide-CSRF"], "fresh-token");
  xhr.upload.onprogress({ lengthComputable: true, loaded: 4999, total: 5000 });
  assert.equal(progress.at(-1), 99);
  assert.equal(phases.at(-1), "transferring");
  xhr.upload.onload();
  assert.equal(progress.at(-1), 100);
  assert.equal(phases.at(-1), "awaiting-response");
  assert.equal(operation.cancel(), false);
  assert.equal(xhr.aborts, 0);
  xhr.complete();
  assert.equal((await operation.promise).id, "job-created");
  assert.equal(phases.at(-1), "finished");
});

test("cancel during transport and network loss report uncertain server outcomes", async () => {
  for (const failure of ["cancel", "network"]) {
    const { api, requests } = setup();
    const operation = api.uploadJob(video(), () => {});
    await flush();
    const rejected = assert.rejects(
      operation.promise,
      (error) =>
        error.outcome === "unknown" && error.message.includes("先查看影像記錄"),
    );
    if (failure === "cancel") assert.equal(operation.cancel(), true);
    else {
      requests[0].upload.onload();
      requests[0].onerror();
    }
    await rejected;
    assert.equal(requests[0].aborts, failure === "cancel" ? 1 : 0);
    assert.equal(operation.cancel(), false);
  }
});

test("5xx and malformed successful responses stay uncertain; 4xx is a rejection", async () => {
  for (const [status, body, outcome] of [
    [503, { detail: "Unavailable" }, "unknown"],
    [202, {}, "unknown"],
    [422, { detail: "Invalid video" }, "rejected"],
  ]) {
    const { api, requests } = setup();
    const operation = api.uploadJob(video(), () => {});
    await flush();
    const rejected = assert.rejects(
      operation.promise,
      (error) => error.outcome === outcome,
    );
    requests[0].complete(body, status);
    await rejected;
  }
});

function uploadComponentHarness() {
  const hooks = createHooks(),
    pending = deferred(),
    navigations = [],
    operation = { phase: null, cancels: 0 };
  const api = setup().api;
  const { Upload } = loadSource("src/components/upload.tsx", {
    react: hooks.react,
    "next/link": { default: () => null },
    "next/navigation": {
      useRouter: () => ({ push: (path) => navigations.push(path) }),
    },
    "@/lib/api": {
      ...api,
      uploadJob: (_data, _progress, phase) => {
        operation.phase = phase;
        return {
          promise: pending.promise,
          cancel: () => {
            operation.cancels++;
            return false;
          },
        };
      },
    },
    "./app-shell": { AppShell: () => null },
    "./date-field": { DateField: () => null },
  });
  const render = () => hooks.render(Upload, { demo: false });
  let tree = render();
  elements(
    tree,
    (node) => node.type === "input" && node.props.type === "file",
  )[0].props.onChange({ target: { files: [new File(["video"], "one.mp4")] } });
  tree = render();
  const submitted = elements(
    tree,
    (node) => node.type === "form",
  )[0].props.onSubmit({ preventDefault() {} });
  return { hooks, api, pending, navigations, operation, render, submitted };
}

test("leaving upload while response is pending never redirects back to the job", async () => {
  const harness = uploadComponentHarness();
  harness.operation.phase("awaiting-response");
  harness.hooks.cleanup();
  harness.pending.resolve({ id: "already-created" });
  await harness.submitted;
  assert.equal(harness.navigations.length, 0);
});

test("uncertain upload outcome offers recordings and blocks immediate duplicate submission", async () => {
  const harness = uploadComponentHarness();
  harness.pending.reject(
    new harness.api.UploadError("請先查看影像記錄", "unknown"),
  );
  await harness.submitted;
  const tree = harness.render();
  assert.equal(
    elements(
      tree,
      (node) => node.type === "button" && node.props.type === "submit",
    )[0].props.disabled,
    true,
  );
  assert.ok(
    elements(tree, (node) => node.props?.href === "/recordings").length > 0,
  );
});
