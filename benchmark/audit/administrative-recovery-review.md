# Administrative recovery policy review

Policy accepted **with explicit administrative accounting and replacement-cohort wording**. No API calls or process changes were made by the reviewer.

## Evidence independently inspected

- collector-interruptions.json records two client-final-record gaps after collector exit 143/SIGTERM, with unknown signal source. Both gateway records end at approximately 18:45:36 Asia/Shanghai with status 499. This supports collector-side interruption; it does not identify who sent SIGTERM or prove an upstream-provider failure.
- The affected matched trial is record_conflicts-r0. Three attempt IDs are excluded from the chosen replacement cohort: original Go first, interrupted Go repair, interrupted GOAT first. All remain in the raw/journal evidence.
- Saved run_core.before-recovery.py hash exactly matches original freeze-core.before-recovery.json: `1fb32c72e4dd9f6e48b243ae58fa030b48c67f7ad56b3d54e64a000fc38b7782`.
- Source diff only adds tolerant JSONL reading and administrative attempt filtering during resume. System/task prompts, parameters and validation policy are unchanged. Client, grader, worker and contract-bank hashes still match the original freeze.
- Regenerated first-call messages hash `5c3dc7207929e7e02d1861019af10b4d825b19ca7928ab9a6914a0c9d33ab207` matches both original provider starts.
- Interruption manifest at review: `a5680fa2e6c73cc0c1927034f29a9c2f29b251d326a477e74cca9194976f0a5a`.
- The original completed Go first was a real strict evaluator failure: `ValueError: dunder attribute access not permitted`, 0/44 checks. It must remain visible as a **restriction failure**, not be relabeled an algorithm error or erased as if never attempted. The common model prompt does not explicitly enumerate the dunder gate; that limitation belongs in the quality breakdown.

## Required accounting

1. Repeat the entire provider pair in fresh sessions with the same first-call messages/settings and the same one-repair policy. This avoids replacing only the censored side. Calendar time/cache can differ and should remain visible.
2. Keep original raw completed attempts and journal-only starts in all-attempt totals. Exclude the three designated IDs only from chosen primary workflow/grade selection. Do not overwrite, fabricate or normalize the original evidence into a successful terminal response.
3. Preserve three separate counts: raw unreturned attempts=2, administratively resolved gaps=2, unresolved unreturned gaps=0 after the documented classification. Gateway status/time may be a separate provenance field; it is not the missing client response or an uncensored completion latency.
4. Gateway in/out/cache zero fields on the interrupted streams are not proof of zero tokens or zero charge. Usage and charge remain unknown. Known-usage cost totals need an explicit unknown-administrative-attempt count.
5. Collection completion can mean **the planned evaluable cohort is complete after a documented matched-pair replacement**. It must not mean all original requests have client terminal records. Use unresolved gaps, pending grades/diagnostics and planned cohort counts to gate completion; retain resolved administrative gaps as permanent evidence.
6. Include a sensitivity result removing the recovered trial pair entirely, plus the original Go first restriction failure in the excluded-attempt table/all-attempt quality breakdown. This makes any improvement caused by replacing a genuine failed first response reviewable.
7. Preserve original and recovery freeze manifests, exclusion-manifest hash, original/replacement attempt links and reason. A completed workflow that contains an excluded ID must not be reused by resume merely because its trial ID exists. The present affected pair had no completed original workflow, so this generic resume edge does not affect the current recovery.

These rules distinguish an administrative measurement failure from provider availability and retain the user's actual consumption uncertainty. They do not authorize deleting unfavorable results or claiming universal quality from the recovered cohort.

## Independent ingestion acceptance

Executed check_recovery.py against analysis revision `b14fa6e34081b329782a950ab46bdd28b8fafc5e38b91ca82c5157e0dec583b2` using a fully synthetic complete cohort. All 209 returned attempts were retained together with two administrative gaps; raw missing=2, administrative resolved=2, unresolved=0 allowed planned evaluable completion. Adding one unexplained start correctly blocked completion. Deliberately appending an excluded old failing grade/workflow after a fresh replacement did not override primary selection. The original restriction failure, measured time and usage remained visible; gateway zero tokens stayed unknown. Dropping the recovered pair produced 35 pairs across 12 task clusters. See administrative-recovery-results.json. No provider calls or generated model execution were involved.
