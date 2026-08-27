# Rules packs

The doctrine only helps if the agent writing your code is holding it. These
are the drop-in forms, sized for the places agents actually read rules from.

| File | What it is |
|---|---|
| [`CLAUDE-snippet.md`](CLAUDE-snippet.md) | The highest-leverage rules, condensed to about a page, each citing its doctrine number. For people who will not paste 15KB into a `CLAUDE.md`. |
| [`cursor.rules.md`](cursor.rules.md) | The same rules in directive form for a Cursor rules file. |

Both are the short form. The **full** operating rules are
[`agent/AGENTS.md`](../AGENTS.md) (~15KB, with the worked examples and the
commands), and the rule set with the incident behind each rule is
[`DOCTRINE.md`](../../DOCTRINE.md).

The two packs carry the same rules in two formats. If you edit one, edit the
other, or they drift and the citations stop agreeing.

## Install

**Claude Code.** Either append the snippet to your rules file:

```bash
cat agent/packs/CLAUDE-snippet.md >> CLAUDE.md
```

or take the full rules and the recurring loops:

```bash
cp agent/AGENTS.md AGENTS.sutradhar.md        # then reference it from CLAUDE.md
mkdir -p .claude/skills/robustness-loop .claude/skills/ops-drill
cp agent/skills/robustness-loop.md .claude/skills/robustness-loop/SKILL.md
cp agent/skills/ops-drill.md       .claude/skills/ops-drill/SKILL.md
```

`bash bootstrap.sh <your-repo> --layers agent` does all of this, and drops
this packs directory in alongside.

**Cursor.** Copy `cursor.rules.md` to `.cursorrules` at your repo root, or to
`.cursor/rules/sutradhar.mdc` with Cursor's `---` frontmatter added at the top
(`description:`, `alwaysApply: true`).

**Anything else** - Codex, Aider, Copilot, an in-house agent: `AGENTS.md` is
the format most of them read. Copy `agent/AGENTS.md` to `AGENTS.md` in your
repo root, or point your tool's rules file at it.

## Citing

Each pack ends with a line naming its source. Leave it there - a rule with no
provenance is a rule nobody can check the scar behind, and checking the scar
is the whole method (doctrine 8.1).
