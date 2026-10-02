# Tool results

What a tool tells the agent back when it needs to steer it (app/tools.py). One per `##` section;
`{{...}}` is filled by code. Plain statuses ("sent", "saved", errors naming an id) stay in code.

## lead-wrote-meanwhile
not sent: the lead just wrote while you were replying:
{{TEXTS}}
Rewrite your reply so it covers everything, then send it. If the new message changes nothing, send your reply again unchanged.

## price-blocked
error: this message looks like it contains a price. send_message cannot send a price {{BUSINESS_OWNER}} hasn't given you — use hold_for_operator to ask him instead.

## sign-off-repeated
error: the sign-off only goes on the very first message to a lead. Remove it and send again.

## held
held: {{BUSINESS_OWNER}} gets your note now. If he answers within {{SECONDS}}s you'll reply with his answer; otherwise the fallback text is sent automatically. Don't send anything else now.

## catalog-no-match
no match — this job isn't in the catalog. Don't estimate it; reply "unclear".

## estimate-drafted
{{LABEL}} {{ID}} (not sent, needs {{BUSINESS_OWNER}}'s approval): {{SUMMARY}}. It goes to {{BUSINESS_OWNER}} as the price suggestion.
