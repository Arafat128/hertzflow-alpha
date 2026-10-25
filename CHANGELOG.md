# Changelog — Perseus fork of HertzFlow Alpha Skill

Upstream base: hertzflow v1.2.16 (`ffcf579`, see UPSTREAM.md). Fork tag: `v1.2.16-pl.1`.

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

## Known open items
- Upstream zh copy test `test_zh_json_term_discipline_派发_vs_分发` is xfailed (zh copy drift; EN unaffected).
- zh render of a `_no_data` run uses the same jinja override (EN verified; zh not exercised).
- Dry-run cannot exercise rule_11 step 2 or the retry (step 1 returns no rows in count mode), so their credit effect is from code analysis, not measurement.
