const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");

function loadSource(relative, stubs = {}, globals = {}) {
  const filename = path.resolve(__dirname, "..", relative);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const sandbox = {
    exports: {},
    require: (name) =>
      name in stubs
        ? stubs[name]
        : name === "@phosphor-icons/react"
          ? new Proxy({}, { get: () => () => null })
          : require(name),
    process: { env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" } },
    URLSearchParams,
    FormData,
    Blob,
    Headers,
    Response,
    AbortController,
    DOMException,
    Intl,
    Date,
    Error,
    TypeError,
    Number,
    setTimeout,
    clearTimeout,
    ...globals,
  };
  vm.runInNewContext(code, sandbox, { filename });
  return sandbox.exports;
}

function createHooks() {
  const states = [],
    refs = [],
    effects = [];
  let stateIndex = 0,
    refIndex = 0,
    effectIndex = 0,
    pending = [];
  const react = {
    useState(initial) {
      const index = stateIndex++;
      if (!(index in states))
        states[index] = typeof initial === "function" ? initial() : initial;
      return [
        states[index],
        (next) => {
          states[index] =
            typeof next === "function" ? next(states[index]) : next;
        },
      ];
    },
    useRef(initial) {
      const index = refIndex++;
      return (refs[index] ||= { current: initial });
    },
    useId: () => "test-date",
    useMemo: (factory) => factory(),
    useCallback: (callback) => callback,
    useEffect(callback, dependencies) {
      const index = effectIndex++;
      if (
        !effects[index] ||
        !dependencies ||
        dependencies.some(
          (value, i) => !Object.is(value, effects[index].dependencies?.[i]),
        )
      ) {
        pending.push(() => {
          effects[index]?.cleanup?.();
          effects[index] = { dependencies, cleanup: callback() };
        });
      }
    },
  };
  return {
    react,
    states,
    render(component, props) {
      stateIndex = 0;
      refIndex = 0;
      effectIndex = 0;
      pending = [];
      const result = component(props);
      pending.forEach((run) => run());
      return result;
    },
    cleanup() {
      effects.forEach((effect) => effect.cleanup?.());
    },
  };
}

function elements(node, predicate) {
  if (!node || typeof node !== "object") return [];
  const matches = predicate(node) ? [node] : [];
  for (const child of React.Children.toArray(node.props?.children))
    matches.push(...elements(child, predicate));
  return matches;
}
const flush = () => new Promise(setImmediate);
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
module.exports = { loadSource, createHooks, elements, flush, deferred };
