import fs from "fs";
import path from "path";

/*
  Every lazily loaded page really does export a component.

  `React.lazy(() => import("./Thing"))` needs `Thing` to have a default
  export. Get that wrong -- a page that only exports a named component, or an
  import path with a typo -- and nothing complains: webpack builds it, the
  route registers, `render` is a function, and the page throws only when
  somebody visits it. Nothing else in the suite opens these pages, so this
  reads every `*.routes.jsx`, follows each import, and checks what comes back.
*/
const PAGES_DIR = path.join(__dirname, "..", "pages");

function routeModules(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return routeModules(full);
    }
    return entry.name.endsWith(".routes.jsx") ? [full] : [];
  });
}

function lazyImportsIn(file) {
  const source = fs.readFileSync(file, "utf8");
  const found = source.match(/import\(\s*\/\* webpackChunkName: "[^"]+" \*\/\s*"([^"]+)"\s*\)/g) || [];
  return found.map((match) => match.match(/"(\.[^"]+)"\s*\)$/)[1]);
}

const cases = routeModules(PAGES_DIR).flatMap((file) =>
  lazyImportsIn(file).map((relative) => [
    path.relative(PAGES_DIR, file),
    relative,
    path.resolve(path.dirname(file), relative),
  ])
);

describe("lazily loaded pages", () => {
  test("there are some, so this test is not vacuously passing", () => {
    expect(cases.length).toBeGreaterThan(20);
  });

  test.each(cases)("%s imports %s, which exports a component", (routesFile, relative, resolved) => {
    // eslint-disable-next-line import/no-dynamic-require, global-require
    const imported = require(resolved);
    expect(typeof imported.default).toBe("function");
  });
});
