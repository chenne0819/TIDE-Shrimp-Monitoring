const test = require("node:test");
const assert = require("node:assert/strict");
const {
  loadSource,
  createHooks,
  elements,
  flush,
  deferred,
} = require("./helpers.cjs");

function recordingsHarness(overrides = {}) {
  const hooks = createHooks(),
    timers = new Map(),
    listeners = new Map();
  let nextTimer = 0,
    jobCalls = 0,
    pondCalls = 0;
  const current = {
    jobs: [],
    ponds: ["A-01"],
    processing: 0,
    failJobs: false,
    failPonds: false,
  };
  const components = {
    AppShell: () => null,
    FilterBar: () => null,
    JobTable: () => null,
    EmptyState: () => null,
    ErrorState: () => null,
    LoadingState: () => null,
  };
  const api = {
    errorMessage: (error) => error.message,
    getJobs: async (_filters, _offset, signal) => {
      jobCalls++;
      if (overrides.getJobs) return overrides.getJobs(signal);
      if (current.failJobs) throw new Error("temporary jobs failure");
      return { items: [...current.jobs], total: current.jobs.length };
    },
    getOverview: async () => {
      pondCalls++;
      if (current.failPonds) throw new Error("temporary ponds failure");
      return {
        available_ponds: [...current.ponds],
        summary: { processing: current.processing },
      };
    },
  };
  const { Recordings } = loadSource(
    "src/components/recordings.tsx",
    {
      react: hooks.react,
      "next/link": { default: () => null },
      "@/lib/api": api,
      "@/lib/demo": { filteredDemoJobs: () => [] },
      "./dashboard": { initialFilters: () => ({}) },
      "./app-shell": { AppShell: components.AppShell },
      "./filters": { FilterBar: components.FilterBar },
      "./job-table": { JobTable: components.JobTable },
      "./ui": components,
    },
    {
      window: {
        addEventListener: (name, fn) => listeners.set(name, fn),
        removeEventListener: (name, fn) => {
          if (listeners.get(name) === fn) listeners.delete(name);
        },
      },
      setTimeout: (fn, ms) => {
        timers.set(++nextTimer, { fn, ms });
        return nextTimer;
      },
      clearTimeout: (id) => timers.delete(id),
    },
  );
  const render = (demo = false) => hooks.render(Recordings, { demo });
  return {
    current,
    hooks,
    components,
    render,
    timers,
    listeners,
    get calls() {
      return { jobs: jobCalls, ponds: pondCalls };
    },
    async tick() {
      const [id, timer] = timers.entries().next().value;
      timers.delete(id);
      await timer.fn();
      await flush();
    },
    focus() {
      listeners.get("focus")?.();
    },
  };
}

test("an empty list polls after 15 seconds, discovers inbox work, and refreshes ponds", async () => {
  const h = recordingsHarness();
  h.render();
  await flush();
  assert.equal([...h.timers.values()][0].ms, 15000);
  h.current.jobs = [{ id: "new-inbox", status: "queued" }];
  h.current.ponds.push("B-02");
  await h.tick();
  const tree = h.render();
  assert.equal(
    elements(tree, (node) => node.type === h.components.JobTable)[0].props
      .jobs[0].id,
    "new-inbox",
  );
  assert.equal(
    elements(
      tree,
      (node) => node.type === h.components.FilterBar,
    )[0].props.ponds.join(","),
    "A-01,B-02",
  );
  assert.equal([...h.timers.values()][0].ms, 4000);
  h.current.jobs[0].status = "completed";
  await h.tick();
  assert.equal([...h.timers.values()][0].ms, 15000);
  h.hooks.cleanup();
  assert.equal(h.timers.size, 0);
  assert.equal(h.listeners.size, 0);
});

test("list and pond failures recover automatically without a manual page reload", async () => {
  const h = recordingsHarness();
  h.current.failJobs = true;
  h.current.failPonds = true;
  h.render();
  await flush();
  assert.equal([...h.timers.values()][0].ms, 15000);
  assert.equal(
    elements(h.render(), (node) => node.type === h.components.ErrorState)
      .length,
    1,
  );
  h.current.failJobs = false;
  h.current.failPonds = false;
  h.current.jobs = [{ id: "recovered", status: "completed" }];
  h.current.ponds = ["Recovered"];
  await h.tick();
  const tree = h.render();
  assert.equal(
    elements(tree, (node) => node.type === h.components.ErrorState).length,
    0,
  );
  assert.equal(
    elements(tree, (node) => node.type === h.components.FilterBar)[0].props
      .ponds[0],
    "Recovered",
  );
  h.hooks.cleanup();
});

test("focus refreshes immediately and coalesces focus events during an in-flight load", async () => {
  const pending = deferred();
  const h = recordingsHarness({ getJobs: () => pending.promise });
  h.render();
  h.focus();
  h.focus();
  assert.equal(h.calls.jobs, 1);
  pending.resolve({ items: [], total: 0 });
  await flush();
  assert.equal([...h.timers.values()][0].ms, 0);
  await h.tick();
  assert.equal(h.calls.jobs, 2);
  h.focus();
  await flush();
  assert.equal(h.calls.jobs, 3);
  assert.equal(h.timers.size, 1);
  h.hooks.cleanup();
});

test("unmount aborts the fetch and ignores late results without scheduling new work", async () => {
  const pending = deferred();
  let signal;
  const h = recordingsHarness({
    getJobs: (requestSignal) => {
      signal = requestSignal;
      return pending.promise;
    },
  });
  h.render();
  const before = JSON.stringify(h.hooks.states);
  h.hooks.cleanup();
  pending.resolve({
    items: [{ id: "too-late", status: "completed" }],
    total: 1,
  });
  await flush();
  assert.equal(signal.aborted, true);
  assert.equal(JSON.stringify(h.hooks.states), before);
  assert.equal(h.timers.size, 0);
});

test("demo recordings make no requests or polling subscriptions", () => {
  const h = recordingsHarness();
  h.render(true);
  assert.equal(h.calls.jobs, 0);
  assert.equal(h.calls.ponds, 0);
  assert.equal(h.timers.size, 0);
  assert.equal(h.listeners.size, 0);
});

test("clear-all remounts date fields even when their controlled dates were already empty", () => {
  const parent = createHooks();
  let filters = { pond: "A-01" };
  const DateMarker = () => null;
  const { FilterBar } = loadSource("src/components/filters.tsx", {
    react: parent.react,
    "./date-field": { DateField: DateMarker },
  });
  const parentRender = () =>
    parent.render(FilterBar, {
      filters,
      onChange: (next) => {
        filters = next;
      },
      ponds: ["A-01"],
    });
  const first = parentRender();
  const before = elements(first, (node) => node.type === DateMarker);
  const child = createHooks();
  const { DateField, isValidDate } = loadSource(
    "src/components/date-field.tsx",
    { react: child.react },
  );
  let field = child.render(DateField, before[0].props);
  elements(field, (node) => node.type === "input")[0].props.onChange({
    target: { value: "2026-02-30" },
  });
  field = child.render(DateField, before[0].props);
  assert.equal(
    elements(field, (node) => node.type === "input")[0].props.value,
    "2026-02-30",
  );
  elements(
    first,
    (node) => node.type === "button" && node.props.className === "clear-filter",
  )[0].props.onClick();
  const after = elements(parentRender(), (node) => node.type === DateMarker);
  assert.notEqual(after[0].key, before[0].key);
  assert.notEqual(after[1].key, before[1].key);
  // React discards child hook state on a changed key. Recreate that instance.
  const resetChild = createHooks();
  const resetComponent = loadSource("src/components/date-field.tsx", {
    react: resetChild.react,
  }).DateField;
  const reset = resetChild.render(resetComponent, after[0].props);
  const input = elements(reset, (node) => node.type === "input")[0];
  assert.equal(input.props.value, "");
  assert.equal(input.props["aria-invalid"], false);
  assert.equal(isValidDate("2025-02-29"), false);
  assert.equal(isValidDate("2024-02-29"), true);
});
