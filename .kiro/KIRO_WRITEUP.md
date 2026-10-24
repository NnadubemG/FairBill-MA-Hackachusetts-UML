# How we built FairBill MA with Kiro

**FairBill MA** helps Massachusetts patients understand a hospital bill. You upload it, confirm the lines,
and it compares each line to real Massachusetts hospital prices. Lines that stand out are flagged as
"may be worth asking about," each with its reason and data source. Then it drafts a polite letter.

**In one line:** four people, four parallel Kiro sessions, 11 specs (85 tasks, all done), 5 steering
files, 2 hooks, 900+ tests including Hypothesis property tests that caught 7 real bugs.

---

## 1. Tools: Kiro IDE, four sessions in parallel

We used the **Kiro IDE**. Each teammate ran their own session against one shared repo: contracts and
checks engine, AI features, data and analysis, web and infra. We used **Autopilot** for implementation
and **sub-agents** (context-gatherer) to read unfamiliar code before changing it. Near the end we had
Kiro split the remaining work into four self-contained prompts, one per session, each listing exactly
which files that session may touch. That let four sessions run without merge conflicts.

We did not use the Kiro CLI, Web, or Crew.

## 2. Specs vs. vibe coding

**How we structured specs.** Each spec had `requirements.md`, then `design.md` with every test case
listed before any task (e.g. pipeline: unit tests U1–U35 and properties P1–P7), then `tasks.md`.
Tasks were one or two small steps each. A contract change was proposed inside the spec as an additive
schema and announced to the team before any code.

| Spec | Tasks | Spec | Tasks |
|---|---|---|---|
| pipeline | 16 | backend-explain | 7 |
| backend-extract | 9 | compare | 7 |
| backend-letter | 9 | core-checks / v2 | 6 + 6 |
| evals | 9 | compare-charts | 6 |
| synthetic-bills | 6 | reference | 4 |

**What specs gave us**
- **Mistakes caught before code.** Writing the extraction spec showed the plan relied on a
  `confidence` field that didn't exist in the shared `LineItem` contract. We added a wrapper instead of
  breaking everyone's schema.
- **Tests were decided up front**, so "done" meant something. Every task ended green.
- **Work survived context resets.** A new session could pick up at the next unchecked task.

**Vibe coding:** we used it for integration work: the runnable server, the web app, deploy files, and
finding data. It was faster, but it caused more rework. For example, a test written afterward caught a
path-traversal gap in static file serving. **Lesson:** spec anything with rules (flags, data, AI
safety). Vibe-code the glue.

## 3. Steering: the shared contract between four sessions

Five always-on files: `product.md`, `tech.md`, `structure.md`, `testing.md`, `team.md`.

**What made the biggest difference: hard rules that are easy to test.**
- *"Never invent numbers. Every price carries `data_source` and `data_year`."* Every session wrote
  `null` instead of a guess. A lab code with no Medicare fee shows "—", never a made-up figure.
- *"Flags come from deterministic code. The LLM only extracts, rewrites, and drafts letters."* This
  became the architecture: `/core` holds the rules, and the model is kept out of all judgments.
- *A banned-word list* ("overcharged", "fraud", …) with an approved phrase: "may be worth asking about".
- `team.md` defined who owns which folders and how they connect. Four sessions built pieces that fit
  together on the first integration: a check fed one session's pipeline output into another session's
  checks engine across 360 bills and found 0 mismatches.

`testing.md` listed the required invariants. Kiro turned each one directly into a property test (§5).

## 4. Hooks: our rules enforced automatically

Both hooks are **script-based (no model credits)**.

| Hook | Trigger | What it does |
|---|---|---|
| Language + gitignore guard | `PreToolUse` on file writes | Blocks any write that puts banned wording into product code or UI text, or adds `.kiro` to `.gitignore`. A marker exempts LLM prompts that must list the words. |
| Test runner | `PostTaskExec` | Runs pytest after every spec task, so a task can't be marked done on a red suite. |

**Impact:** the language rule stopped depending on memory. LLM prompts that list the banned words on
purpose needed the explicit `language-guard: allow` marker. Testing the guard itself found a bug: it
stripped the dot from `.kiro/` paths.

## 5. Property-based testing (Hypothesis): 7 bugs unit tests missed

**What we tested with properties:** no banned words in any output; every number has a source and year;
an empty bill gives no flags; flags only point at real lines; input order never matters; same input
gives same output; missing reference data never produces a price flag. Pipeline properties checked that
a percentage is never turned into a dollar amount, min ≤ median ≤ max, and only curated codes pass
through.

| Bug a property found | Why unit tests missed it |
|---|---|
| A bill code of `FRAUD` was printed inside a flag | Nobody writes that example by hand |
| Checks engine crashed when one of two matching references had no year | Rare data combination |
| Letter printed `$-0.00` for an amount of −0.0 | Floating-point edge case |
| A date `2026-03-04` let "3" and "4" through as invented figures | Interaction between two checks |
| JSON with ` ``` ` inside a string broke the code-fence parser | Strange model output |
| Letter check rejected model text ending in a line break | Real model habit |
| **Properties that passed but never actually triggered the new flags (0 of 400 runs)** | Fixed with targeted input generators plus a test that fails if they stop triggering the flags |

The last row was the most valuable lesson: **check that a passing property is actually exercising the
code.**

## 6. MCP and Powers: honest status

We did **not** configure MCP servers or install Kiro Powers. Kiro's built-in web search and fetch did
the outside-world work instead:
- Found that BIDMC's price file follows the CMS naming pattern and downloaded it directly (27 MB).
  That gave us a second real hospital.
- Explored the CMS fee schedule API and found it doesn't expose payment amounts. We logged that as a
  gap instead of computing a figure. A teammate's session then downloaded the official CMS files and
  added parsers for them.
- Found that AWS changed the permissions for public Lambda Function URLs in Oct 2025. That fix went
  into our template before the first deploy.

**Next:** an AWS Documentation MCP server and the AWS Power for deploys, and a fetch MCP for crawling
hospital `cms-hpt.txt` files at scale.

**Third-party tools Kiro brought in:** Hypothesis (property tests), the Anthropic API (extraction,
explanations, letters), and AWS SAM + CloudFront (deploy).

## 7. Results

- **Working app:** upload → confirm → flags → letter, plus a hospital price comparison. Nothing is
  stored, and it works offline in demo mode.
- **Real data:** 7 Massachusetts hospitals, 19 procedures, 405 price records from public price files,
  plus the 2026 CMS Medicare fee schedule and quantity limits.
- **Tests:** 413 + 452 Python and 40 frontend tests passing.
- **Logged:** every notable catch is in `docs/kiro-log.md`, newest at the bottom.
