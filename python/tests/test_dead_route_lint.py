"""Tests for the dead-route / unfailable-assertion guard, red cases included."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.dead_route_lint import (
    find_dead_routes, find_unfailable_assertions, route_matches, selfcheck,
)

SPEC = '''
describe("x", () => {
  it("a", () => {
    cy.request({ url: `${BASE}/real/route` }).then((res) => {
      expect(res.status).to.not.eq(500);
    });
    cy.request({ url: `${BASE}/ghost/route` }).then((res) => {
      expect(res.status).to.eq(200);
    });
  });
});
'''

def _write(tmp_path, body=SPEC, name="a.cy.ts"):
    (tmp_path / name).write_text(body)
    return tmp_path


def test_flags_route_absent_from_the_api(tmp_path):
    d = find_dead_routes(_write(tmp_path), {"/real/route"})
    assert d == ["a.cy.ts:/ghost/route"], d


def test_served_route_is_clean(tmp_path):
    d = find_dead_routes(_write(tmp_path), {"/real/route", "/ghost/route"})
    assert d == []


def test_flags_the_unfailable_assertion(tmp_path):
    assert find_unfailable_assertions(_write(tmp_path)) == ["a.cy.ts:5"]


def test_strong_assertion_is_clean(tmp_path):
    body = 'expect(res.status).to.eq(200);\nexpect(res.status).to.be.oneOf([200, 204]);'
    assert find_unfailable_assertions(_write(tmp_path, body)) == []


def test_param_routes_match(tmp_path):
    body = 'cy.request({ url: `${BASE}/users/${id}` });'
    assert find_dead_routes(_write(tmp_path, body), {"/users/{id}"}) == []


def test_trailing_slash_is_not_a_false_positive():
    assert route_matches("/x", {"/x/"}) and route_matches("/x/", {"/x"})


def test_frontend_drill_url_is_not_treated_as_an_api_path(tmp_path):
    # The exact false positive found in the field: `drill_url` carries a SPA
    # route, not an API path. Flagging it sends you fixing a good route.
    body = "const card = { drill_url: '/instances?asset=dt_014' };"
    assert find_dead_routes(_write(tmp_path, body), {"/api/v2/items"}) == []


def test_selfcheck_passes():
    assert selfcheck()
