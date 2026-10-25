# Changelog — Perseus fork of HertzFlow Alpha Skill

Upstream base: hertzflow v1.2.16 (`ffcf579`, see UPSTREAM.md). Fork tag: `v1.2.16-pl.1`.


## Desk 01 operator rules enforced in the PDF gate (2026-10-26)
- New `scripts/preflight_pdf.py`; `build_pdf.py` runs it before (exit 3) and after (exit 4,
  output renamed `*.BLOCKED.pdf`) building. Named gates: ARKHAM_REQUIRED, DRY_RUN_FIRST,
  NO_CREDIT_CAP, SURF_VERIFY, FRAMES ("NEXT: Visual"), FANOUTS, BRIEF_SECTIONS, SOURCE_TAGS,
  TRACE; post: OVERFLOW, LINT_PRICE_TARGET, LINT_TRADE_WORDS, LINT_CLEAN_ON_GAP, REPORT_SECTIONS.
  `--waive NAME` is logged in `.work/preflight_pdf.json`.
- Live runs default to HF_BUDGET=0 (no credit cap); `--max-credits` on a live run is refused
  (HF_ALLOW_CAP=1 overrides). run_manifest records budget_on/max_credits; count-mode runs write
  `.work/dry_run.json` + `hertzflow-cache/dry_runs/<ca>.json` as dry-run evidence.
- build_pdf lays out the Style D default pack: cover (ticker, CA, chain, date, state tier, RISK),
  "HertzFlow (skill output only)" block, brief body, Visual frames + fan-outs, Arkham cross-check
  (side-by-side note), Limitations and what's left out, optional Requester question, Sources, NFA.
  Footer no longer says "Sources"/"Not financial advice" (keeps the order check meaningful).
- tests/test_preflight_pdf.py: a test for each gate.

## Unreleased (after v1.2.16-pl.1)
### Safety
- update_check is report-only; the npx auto-update path is gone.
- Pinned deps (`requirements.lock`, `tools.lock`: surf-cli 1.0.9, Python 3.13.5).
- Tests strip Surf/Arkham keys and put a fake `surf` first on PATH (cannot spend credits).
### Fixes
1. Persistent PAID_BALANCE_ZERO key ledger (key name + sha256 fingerprint, never the value, 24 h TTL) and a 0-credit preflight that aborts (exit 3) before any paid call when every pool key is known-empty.
2. rule_11 step 1: one transient retry, **hard cap 1 per process** (env `HF_R11_RETRY` can only lower it), never in dry-run/emulate, with the breaker open, or with the pool exhausted. Worst case **+8 credits/run** (≤2 SQL chunks × 4 cr). The error reason is kept as `_trace_error`.
3. rule_11 step 2: outflow ceiling = min(mint+14 d, today) when the mint is after listing (was an empty window). LIMIT-100 truncation is flagged (`outflows_truncated_at_100`). Same single SQL call, flat 4 cr: +0 credits.
4. Every stderr line carries a `[YYYY-MM-DD HH:MM:SS+06]` stamp; `.work/timing.json`.
5. Baseline commit with .bak files moved into history.
6. Decimals: RPC vs Alpha API cross-check, loud warning on mismatch or default-18; `meta.decimals_source`.
7. Explicit `_data_gaps`; 0 successful paid calls / breaker open → `chain_state=UNKNOWN`, risk `None` (was CLEAN 0/10).
8. `--symbol-hint` is refused with a reason.
9. `.work/run_manifest.json`: UTC+06 time, sha256 + size of every output, version, git head; `verify()`.
### Added
- `scripts/key_health.py` — 0-credit key report from the ledger (Surf has no free balance endpoint; rotation stays reactive).
- `rpcs.yaml` + `helpers/rpc_pool.py` — health-ordered free RPC fallback (decimals, role_classifier, supply_chain_overhang).
- `scripts/rpc_verify.py` → `.work/rpc_verify.json`; `scripts/surf_checklist.py` → short Surf checklist that skips what RPC proved.
- `helpers/arkham_xcheck.py` — Arkham cross-check, plan-only unless `--live`, flags 100-row cap truncation.
- `scripts/build_pdf.py` — one-script Style D PDF from skeleton + brief + frames (never overwrites).
- Smoke tests (`tests/smoke`, `HF_SMOKE=1`) and GitHub Actions CI.

### Arkham cross-check is mandatory (Desk 01 rule 2026-10-21)
- `helpers/arkham_xcheck.py` runs **live by default**; `--plan-only`, `HF_DRY_RUN=1` or `HF_API_MODE=count|emulate_zero_balance` only plan (0 Arkham calls).
- `.work/arkham_xcheck.json` keeps `labels` [A], `facts` [F] and `inferences` [I] separate; status `ok|partial|failed|plan_only`; per-call errors kept with reason; transfer pulls hitting the 100-row cap are flagged `truncated_at_cap` (lower bounds).
- Writes `.work/fanout/<SYM>-fan-N-<role>-<addr>.json` specs for `/workspace/style-refs/fanout.py` (render checked locally).
- `scripts/build_pdf.py` refuses (exit 3, "ARKHAM REQUIRED") when `arkham_xcheck.json` is missing, unreadable, `failed` or `plan_only`; the PDF always has an "Arkham cross-check" section, and errored calls show UNKNOWN with the reason.
- `scripts/surf_checklist.py` lists the Arkham [A] labels to confirm, the 100-cap truncated addresses and [I] inferences, or "ARKHAM REQUIRED" if the check is missing.

## Known open items
- Upstream zh copy test `test_zh_json_term_discipline_派发_vs_分发` is xfailed (zh copy drift; EN unaffected).
- zh render of a `_no_data` run uses the same jinja override (EN verified; zh not exercised).
- Dry-run cannot exercise rule_11 step 2 or the retry (step 1 returns no rows in count mode), so their credit effect is from code analysis, not measurement.
