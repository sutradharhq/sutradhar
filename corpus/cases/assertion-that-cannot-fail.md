---
case: assertion-that-cannot-fail
guard: dead_route_lint
rule: 3.7
scar: R2-4
expected: caught
---

`expect(res.status).to.not.eq(500)` passes on 404, 403, 401 and 400:
excluding one bad outcome tolerates every other one. R2-4 counts 44 of
them across a suite that stayed green for months. The defective twin
asserts the absence of a single failure; the clean twin asserts the
contract. Both twins hit only routes the table serves, so each exercises
exactly one finder. The route table is manifest data in the helper
fence below.

```json path=routes.json
{"routes": ["/units"]}
```

## defective

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/units").then((res) => {
    expect(res.status).to.not.eq(500);
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
