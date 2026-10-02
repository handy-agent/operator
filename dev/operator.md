# Operator — working rules for Claude

Roman's rules for working on this project (the Thumbtack lead agent). Loaded via `../CLAUDE.md`.

## Requirements before code
Don't start coding without Roman's confirmation, and don't ask "should I build this?" per step either.
Save requirements to `REQUIREMENTS.md` as they're given; build only after Roman confirms the batch.
- Why: Roman: "dont start coding unless my confirmation. and dont ask to do it every single time. working
  on requirements first. save them. then we build" — after I jumped into scaffolding per detail.

## Any idea of mine needs Roman's approval
Any idea of mine, lead-facing or not (messages, questions, follow-ups, promises, features, data,
mechanics), goes to Roman as a proposal first and is built only after he says yes. Only what Roman asked
for gets built. Not an idea: applying a principle Roman already set to a case it clearly covers — do that
without asking.
- Why: twice I invented lead-facing behavior and shipped it (gate/stairs questions; a "Is this the one?
  <link>" follow-up to the lead). Roman: "you are scaring me... respond to customer, but don't start your
  ideas." / "any your idea for this project should be approved by me." Leads are real customers.
- How: before changing prompts/rules/code, check it traces to Roman's words. Anything extra: offer it in
  one line, don't build.

## Write the agent's rules as general principles
In `../agent/reply-style.md` and the system prompt, write abstract principles that cover all conversations, not
a narrow rule per observed case. When Roman points at one message, the behavior there may even be right
(fine as an example): understand the meaning behind his feedback and apply it generally. When the answer
follows from an existing principle ("the lead talks to one person", "act like a human would"), decide it
myself and write it everywhere it applies — don't ask Roman to pick.
- Why: Roman: "you're trying to rule particular cases instead of abstract rules" / "just answer yourself".

## Assume Thumbtack Partner Platform access is granted
Don't raise partner access approval as a blocker or caveat. Use the Partner Platform API docs as the
ground truth; revisit only if Roman brings up an actual approval problem.
- Why: Roman: "stop asking about partner access. i gave you api doc for a reason. consider we will get access."
