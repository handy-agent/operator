# Tool descriptions

What the agents see for each tool (app/tools.py). One per `##` section, named like the tool.

## check_availability
Check {{BUSINESS_OWNER}}'s free time slots on a given day (YYYY-MM-DD) before proposing scheduling to the lead. Does NOT confirm anything — a proposed time still needs {{BUSINESS_OWNER}}'s approval before it can be sent, same as an estimate.

## estimate_travel
Estimate (approximate) travel distance from {{BUSINESS_OWNER}}'s base to the job location, for internal pricing/scheduling use only — never share the origin/address with the lead, only the computed distance if relevant.

## get_messages
Fetch the full message history for the current lead's Thumbtack thread.

## hold_for_operator
Use INSTEAD of send_message when the lead's message needs {{BUSINESS_OWNER}}'s decision (price, time, anything to confirm). {{BUSINESS_OWNER}} is asked right away via your note. If he answers soon, you'll get his instruction and reply with the real answer; if not, fallback_text (e.g. "Let me check and get back to you on that.") is sent automatically later.

## pause_lead
Stop automatic replies on this lead (the operator said to stop / take over).

## propose_estimate
Calculate a suggested price for {{BUSINESS_OWNER}} from the pricing catalog. Run it as soon as the job is known (rough without a link/photos) and again after every new or changed detail from the lead. Writes a DRAFT only (replaces the previous one) — never sends it; {{BUSINESS_OWNER}} approves the price. Find subservice_id with search_catalog first.

## record_lead_detail
Save a clarified detail on the current lead's record. field is one of: name, phone, service, location, item_link (product link), preferred_day.

## resume_lead
Turn automatic replies back on for this lead (the operator said to continue / take it back).

## search_catalog
Find the pricing catalog subservice for a job, by keywords (e.g. 'raised garden bed assembly').

## send_message
Send a text message to the lead on their Thumbtack thread. Never include a price or a confirmed date/time unless {{BUSINESS_OWNER}} approved it — prices only go through when they match what {{BUSINESS_OWNER}} gave in his instruction this turn.
