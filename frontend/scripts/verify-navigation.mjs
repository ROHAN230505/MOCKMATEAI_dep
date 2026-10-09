/**
 * Verification for the navigation model (`src/components/layout/navigation.tsx`).
 *
 *   npm run verify:nav
 *
 * Two failures here are invisible on screen and only show up in use, which is
 * exactly the kind worth a harness:
 *
 *  - A **duplicate go-to key** makes one destination permanently unreachable by
 *    keyboard. Both rows still render, both tooltips still promise the shortcut,
 *    and only the first one ever wins.
 *  - A **route that does not exist** in the router sends the user to the 404
 *    page from the product's own navigation.
 *
 * The model is parsed as text rather than imported: it is a `.tsx` module full
 * of JSX, and Node's type stripping will not render that. Reading the literals
 * is enough for both checks and keeps the harness dependency-free, in the same
 * style as the other six.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const nav = fs.readFileSync(path.join(here, "..", "src", "components", "layout", "navigation.tsx"), "utf8");
const app = fs.readFileSync(path.join(here, "..", "src", "App.tsx"), "utf8");

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const items = [...nav.matchAll(/to:\s*"([^"]+)"[\s\S]*?label:\s*"([^"]+)"[\s\S]*?hint:\s*"([^"]+)"/g)].map(
  (m) => ({ to: m[1], label: m[2], hint: m[3] }),
);
const routes = new Set([...app.matchAll(/path="([^"]+)"/g)].map((m) => m[1]));

console.log("\nnavigation model\n");
check("the model was parsed", items.length > 0, `${items.length} destinations`);

const seen = new Map();
const duplicates = [];
for (const item of items) {
  if (seen.has(item.hint)) duplicates.push(`"${item.hint}" on ${seen.get(item.hint)} and ${item.label}`);
  else seen.set(item.hint, item.label);
}
check("every go-to key is unique", duplicates.length === 0, duplicates.join("; "));

const unreachable = items.filter((item) => {
  if (routes.has(item.to)) return false;
  // A parameterised route covers its children: `/settings/:section` serves
  // `/settings/profile`, so a literal miss is not automatically a broken link.
  return ![...routes].some((route) => {
    if (!route.includes(":")) return false;
    const pattern = new RegExp(`^${route.replace(/:[^/]+/g, "[^/]+")}$`);
    return pattern.test(item.to);
  });
});
check(
  "every destination resolves to a route",
  unreachable.length === 0,
  unreachable.map((item) => `${item.label} -> ${item.to}`).join("; "),
);

for (const item of items) {
  check(`${item.label.padEnd(16)} g ${item.hint}`, true, item.to);
}

console.log(
  failures === 0 ? "\nall navigation checks passed\n" : `\n${failures} navigation check(s) FAILED\n`,
);
process.exitCode = failures === 0 ? 0 : 1;
