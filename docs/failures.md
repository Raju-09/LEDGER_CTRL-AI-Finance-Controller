# Failures during this build

Honest log, not a retrospective template.

1. **Invoice due dates were +0–7 days while the date window was 3 days.** Exact controls were scoring ~0.83 and failing AUTO_CLOSE. Fix: tighten due dates in the generator; score invoices on `invoice_number`, not UTR-vs-INV.
2. **Ambiguous twins used a suffixed invoice number**, so the true invoice won by more than `tie_delta` and auto-closed. Fix: clone amount/date/vendor/**invoice_number**; only `invoice_id` differs.
3. **Orphans were labeled DUPLICATE** because consumed-target skipping left candidate lists empty, same as a missing counterpart. Fix: keep consumed candidates with `ALREADY_CONSUMED` and only then set DUPLICATE.
4. **Recall will never look “perfect”** if twins and orphans exist. That is intended. Do not “fix” recall by auto-closing ties.
5. **LLM outage** is a feature path: schema/timeout/missing key → `AI_UNAVAILABLE`, still ESCALATE.
