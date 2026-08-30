# FIX-01 Governance Correction — Cleanup Inspection (no edits performed)

Status: **inspection only**, per `FIX01_GOVERNANCE_CORRECTION_CLEAN_BASELINE.md`'s mandatory
sequence, step 1 ("INSPECT 068e8fa") only. Nothing in `starter/`, `demo/`, `evaluator/`,
`docs/`, or `data/` has been modified. A dry-run revert was executed and then fully undone
(see §3) solely to test feasibility — it left the working tree unchanged.

---

## 1. Confirming the correction doc's enumeration against the actual diff

The correction doc lists 5 items that must not remain in the clean FIX-01 baseline. Diffing
`068e8fa` against its parent `9b5fc2f` directly (not from memory) confirms all 5, and only
these 5, exist in that commit:

| # | Item (per correction doc) | Confirmed in diff? | Location |
|---|---|---|---|
| 1 | expanded `BUDGET_RE` | ✅ | `starter/agent.py`, one line changed |
| 2 | expanded `NO_PREFERENCE_PHRASES` | ✅ | `starter/agent.py`, one set literal extended |
| 3 | `known_slot_count()` | ✅ | `starter/agent.py`, new method added |
| 4 | dynamic interactive-demo recommendation display | ✅ | `demo/interactive.py`, depends on item 3 |
| 5 | the "0.73 → 0.675" production-code comment | ✅ | `starter/agent.py`, comment-only, zero executable-code change |

**No additional out-of-scope changes were found beyond these 5.** `068e8fa`'s full stat is
`demo/interactive.py | 7 ++, starter/agent.py | 25 ++` — two files only, and both diffs are
fully accounted for by the 5 items above. Nothing in this commit touches
intent-override logic, retrieval/BM25 weighting, the FTS5 schema, `ASK_ORDER`, or
`_parse_message`'s override branch.

Item 5 is worth flagging precisely: it is a **comment-only** addition — no executable line
changed as part of that hunk. Per the correction's epistemic-correction section, the
"0.73 → 0.675" figure inside that comment is classified here as:

```
UNVERIFIED HISTORICAL CLAIM
```

No experiment artifact, alternate code path, or reproducible command exists for it. It is
not used as a premise anywhere in this document or in the prior pre-patch verification.

---

## 2. Confirming no later commit touches these files

```
git log --oneline 068e8fa..HEAD
  c6461c4  added markdowns for Claude
```

Only one commit exists after `068e8fa`, and its full stat is:
```
markdowns/handover2.md                    | 289 ++
markdowns/probes/probe_compound.py        |  29 ++
markdowns/probes/probe_override_batch.py  |  60 ++
markdowns/probes/probe_override_single.py |  55 ++
```

Zero overlap with `starter/agent.py` or `demo/interactive.py`. Current `HEAD`
(`c6461c4`) is confirmed byte-identical to `068e8fa` for both files
(`git diff 068e8fa c6461c4 -- starter/agent.py demo/interactive.py` → empty), and the
working tree is clean (no uncommitted edits to either file).

**Conclusion**: there is no "later relevant edit" risk the correction doc warned about.
Nothing built on top of the 5 out-of-scope changes, and nothing else needs to be preserved
within those two files beyond what predates `068e8fa`.

---

## 3. Feasibility check — dry-run only, fully undone

Tested whether reverting the entire commit `068e8fa` applies cleanly (rather than needing
manual hunk-by-hunk surgery), since 100% of that commit's diff is confirmed out-of-scope
and nothing later depends on it:

```bash
git revert --no-commit --no-edit 068e8fa
```

Result: applied cleanly, no conflicts —
```
M  demo/interactive.py
M  starter/agent.py
```

This was then **fully reverted**, leaving the working tree exactly as it was before the
test (confirmed via `git status --short`, showing only the pre-existing untracked
`markdowns/fix01_prepatch_verification.md`, itself unrelated to this test). No commit was
created; no file was left modified.

**Conclusion**: a full revert of `068e8fa` — rather than manual removal of 5 separate
hunks — is a clean, low-risk, exact way to restore `starter/agent.py` and
`demo/interactive.py` to their pre-`068e8fa` (i.e. `9b5fc2f`) state, since:
- every line `068e8fa` changed is on the correction doc's removal list, and
- no subsequent commit touches either file.

This is offered as the proposed mechanism for step 2 of the mandatory sequence
("SURGICALLY REMOVE OUT-OF-SCOPE CHANGES") — not yet executed.

---

## 4. What has NOT been done

- `068e8fa` has not been reverted for real (no commit created, no file left modified).
- The "restored FIX-01 baseline" has not been proven with a real evaluator run yet
  (mandatory sequence step 3, "PROVE RESTORED BASELINE" — requires the revert to actually
  happen first).
- The 30-session override probe has not been re-run against a restored baseline.
- No FIX-01 implementation (provenance-aware override replacement) has begun.

## 5. Proposed next step (awaiting go-ahead)

1. Commit the revert of `068e8fa` for real (`git revert --no-edit 068e8fa`), restoring
   `starter/agent.py` and `demo/interactive.py` to pre-`068e8fa` semantics while leaving
   `markdowns/` and all other files untouched.
2. Record new SHA256 hashes for both files post-revert.
3. Run `python3 -m unittest tests.test_evaluator`.
4. Run `python3 -m evaluator.local_evaluator` twice, confirm determinism.
5. Re-run the 30-session override probe against the restored baseline.
6. Report all of the above as the "RESTORED FIX-01 BASELINE" state, distinct from
   "CURRENT-HEAD PRE-CLEANUP" (already recorded in
   [`fix01_prepatch_verification.md`](fix01_prepatch_verification.md)) — per the
   correction doc's required three-way distinction (pre-cleanup / restored baseline /
   post-FIX-01).
7. Only then begin the provenance-aware Intent Override implementation itself.

No further action taken in this pass.
