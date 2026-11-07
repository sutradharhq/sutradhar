---
case: assertion-not-equal-spelling
guard: dead_route_lint
rule: 3.7
scar: R2-4
expected: caught
---

Chai spells the same weak assertion two ways, and the guard's
weak-assertion pattern matches only one of them: `not.to.equal` with the
negation before `to`, as in `expect(res.status).not.to.equal(500)`. The
other order, `to.not.equal`, is not in the pattern, so this case pins the
spelling the pattern does match. R2-4 counts 44 exclusions of a single
failure across a suite that stayed green for months. The defective twin
asserts the absence of one failure and so passes on every other wrong
answer; the clean twin asserts the contract with `.to.eq(200)`. Both twins
hit only routes the table serves, so each exercises exactly one finder.
The route table is manifest data in the helper fence below.

```json path=routes.json
{"routes": ["/units"]}
```

## defective

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/units").then((res) => {
    expect(res.status).not.to.equal(500);
  });
});
```

## clean

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/units").then((res) => {
    expect(res.status).to.eq(200);
  });
});
```
