---
case: route-nested-prefix
guard: dead_route_lint
rule: 3.7
scar: R2-4
expected: caught
---

A spec aimed at a nested path under a live prefix is still aimed at
nothing when the full path is absent from the route table (R2-4: 28
references resolving to nothing). The defective twin hits
`/api/v1/ghost` with a strong assertion and is flagged; the clean twin
hits the served `/api/v1/units` with the same strong assertion and stays
silent. Neither twin carries a weak assertion, so each exercises exactly
one finder. The route table is manifest data in the helper fence below.

```json path=routes.json
{"routes": ["/api/v1/units"]}
```

## defective

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/api/v1/ghost").then((res) => {
    expect(res.status).to.eq(200);
  });
});
```

## clean

```ts path=cypress/e2e/units.cy.ts
it("loads units", () => {
  cy.request("/api/v1/units").then((res) => {
    expect(res.status).to.eq(200);
  });
});
```
