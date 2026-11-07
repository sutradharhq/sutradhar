---
case: route-with-query-ghost
guard: dead_route_lint
rule: 3.7
scar: R2-4
expected: caught
---

The guard normalises a spec URL by stripping the query string before
comparing it against the route table. `/ghost?x=1` strips to `/ghost`,
which the table does not serve, so the defective twin is flagged however
strong its assertion. `/units?x=1` strips to the live `/units`, so the
clean twin stays silent. Both twins assert the contract with `.to.eq(200)`,
keeping the weak-assertion finder out of the pair. The route table is
manifest data in the helper fence below.

```json path=routes.json
{"routes": ["/units"]}
```

## defective

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/ghost?x=1").then((res) => {
    expect(res.status).to.eq(200);
  });
});
```

## clean

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/units?x=1").then((res) => {
    expect(res.status).to.eq(200);
  });
});
```
