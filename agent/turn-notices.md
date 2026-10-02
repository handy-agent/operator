# Turn notices

Short texts the code adds to a turn's prompt (app/agent.py). One per `##` section; `{{...}}` is filled by code.

## lead-id
Current lead_id/session_id: {{LEAD_ID}}

## operator-instruction
Instruction from the operator (via the private channel):
{{TEXT}}

## lead-messages
New lead message(s):
{{TEXT}}

## paused
(This lead is paused: {{BUSINESS_OWNER}} is talking to the lead himself. You can't message the lead now. Answer {{BUSINESS_OWNER}} here — e.g. suggest wording he can send himself. Nothing goes to the lead until he resumes.)

## latest-price
(Latest price suggestion: ${{SUGGESTED}} — {{PRICE_TEXT}})

## first-message
(Nothing has been sent to this lead yet: your next message to them is the first one, so open with the greeting and end with the sign-off.)

## session-rebuilt
(Session rebuilt after inactivity. Recent history:
{{HISTORY}}

{{TEXT}})

## estimate-request
lead_id: {{LEAD_ID}}
Saved details: {{SAVED}}
Previous estimate: {{PREVIOUS}}

Conversation:
{{CONVERSATION}}

## lookup-request
Lead's description: {{DESCRIPTION}}
