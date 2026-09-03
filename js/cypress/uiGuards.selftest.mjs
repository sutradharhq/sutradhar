// Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
// Part of Sutradhar: https://github.com/sutradharhq/sutradhar
//
// Selftest for readFormState - the dimension expectEffect was blind to.
//
//   node js/cypress/uiGuards.selftest.mjs
//
// Runs the REAL shipped uiGuards.ts (compiled with esbuild, which this repo's
// CI already uses for the syntax job) against a minimal DOM stub. It is not a
// browser and does not pretend to be: it exercises exactly the DOM surface
// readFormState touches, which is enough to prove the digest sees form state
// and to fail when a future edit takes that back out.
//
// The load-bearing case is `identical text, different form state`. That is the
// defect this file exists for: the other three dimensions expectEffect watches
// (URL, body text, storage) cannot tell those two pages apart.
//
// Exits 0 when every case holds, 1 otherwise. An unavailable esbuild exits 2 -
// NOT 0: a check that could not run has not passed.

import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const work = mkdtempSync(join(tmpdir(), "uiguards-"));
const bundle = join(work, "uiGuards.mjs");

try {
  execFileSync(
    "npx",
    ["--yes", "esbuild", join(HERE, "uiGuards.ts"), "--format=esm", `--outfile=${bundle}`],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
} catch (err) {
  console.error("[uiGuards] CANNOT RUN: esbuild did not compile uiGuards.ts.");
  console.error("  This is not a pass and not a failure of the guard - nothing");
  console.error("  was checked. Install node/npx and retry.");
  console.error(String(err.stderr ?? err));
  rmSync(work, { recursive: true, force: true });
  process.exit(2);
}

const { readFormState } = await import(pathToFileURL(bundle).href);

// ── a DOM stub covering exactly what readFormState reads ────────────────────

function el(tag, props = {}) {
  const attrs = props.attrs ?? {};
  return {
    tagName: tag.toUpperCase(),
    type: props.type,
    value: props.value,
    checked: props.checked,
    disabled: props.disabled,
    selectedOptions: props.selectedOptions,
    isContentEditable: props.contentEditable === true,
    textContent: props.text ?? "",
    getAttribute: (n) => (n in attrs ? attrs[n] : null),
    _attrs: attrs,
  };
}

/** Matches the comma-separated `tag` / `[attr]` selector readFormState uses. */
function makeDoc(elements) {
  return {
    querySelectorAll(selector) {
      const terms = selector.split(",").map((t) => t.trim()).filter(Boolean);
      return elements.filter((e) =>
        terms.some((t) =>
          t.startsWith("[")
            ? t.slice(1, -1) in e._attrs
            : t.toUpperCase() === e.tagName,
        ),
      );
    },
    // what body.innerText would report - deliberately blind to form state
    _text: elements.map((e) => e.textContent).join(" ").trim(),
  };
}

let failures = 0;
const check = (name, ok, detail = "") => {
  if (ok) {
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name}${detail ? ` - ${detail}` : ""}`);
  }
};

// ── the cases ───────────────────────────────────────────────────────────────

console.log("\n[uiGuards] readFormState selftest\n");

// 1. THE DEFECT. Same rendered text, different form state.
{
  const before = makeDoc([
    el("label", { text: "Amount" }),
    el("input", { type: "text", value: "" }),
    el("button", { text: "Pay", disabled: true }),
  ]);
  const after = makeDoc([
    el("label", { text: "Amount" }),
    el("input", { type: "text", value: "250.00" }),
    el("button", { text: "Pay", disabled: false }),
  ]);
  check(
    "body text is IDENTICAL across the interaction (the blind spot)",
    before._text === after._text,
    `${before._text} vs ${after._text}`,
  );
  check(
    "readFormState tells the two apart",
    readFormState(before) !== readFormState(after),
  );
}

// 2. each dimension on its own
const one = (name, a, b) =>
  check(name, readFormState(makeDoc([a])) !== readFormState(makeDoc([b])));

one("value change", el("input", { value: "a" }), el("input", { value: "b" }));
one(
  "checkbox toggled",
  el("input", { type: "checkbox", checked: false }),
  el("input", { type: "checkbox", checked: true }),
);
one(
  "button enabled",
  el("button", { disabled: true }),
  el("button", { disabled: false }),
);
one(
  "aria-disabled toggled (component libraries use this, not the property)",
  el("div", { attrs: { "aria-disabled": "true" } }),
  el("div", { attrs: { "aria-disabled": "false" } }),
);
one(
  "aria-expanded toggled (a dropdown that opens)",
  el("div", { attrs: { "aria-expanded": "false" } }),
  el("div", { attrs: { "aria-expanded": "true" } }),
);
one(
  "select multiple - second selection added, .value alone would miss it",
  el("select", {
    value: "a",
    selectedOptions: [{ value: "a" }],
  }),
  el("select", {
    value: "a",
    selectedOptions: [{ value: "a" }, { value: "b" }],
  }),
);
one(
  "contenteditable text edited",
  el("div", {
    contentEditable: true,
    text: "before",
    attrs: { contenteditable: "" },
  }),
  el("div", {
    contentEditable: true,
    text: "after",
    attrs: { contenteditable: "" },
  }),
);

// 3. no false positives: an unchanged form must digest identically, or every
//    expectEffect assertion passes vacuously on noise.
{
  const build = () => [
    el("input", { type: "text", value: "steady" }),
    el("button", { text: "Save", disabled: false }),
  ];
  check(
    "an unchanged form digests identically (no false green)",
    readFormState(makeDoc(build())) === readFormState(makeDoc(build())),
  );
}

// 4. a page with no form controls must not crash and must digest empty
{
  const doc = makeDoc([el("p", { text: "nothing here" })]);
  check("a form-free page yields an empty digest", readFormState(doc) === "");
}

rmSync(work, { recursive: true, force: true });

console.log();
if (failures) {
  console.log(`[uiGuards] ${failures} case(s) FAILED\n`);
  process.exit(1);
}
console.log("[uiGuards] all cases passed\n");
