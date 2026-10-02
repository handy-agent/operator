# What it does: Local chat simulator — you type as the lead, the real Operator agent replies.
#   Runs the same webhook handler as production, but with ConsoleMessagingClient, so nothing is sent
#   to Thumbtack. Each run is a new lead with ID "sim-<timestamp>" (records land in DynamoDB like real ones).
# When it runs: Manually, to see how Operator handles a conversation before going live.
# What calls it: sh/chat.sh.
import asyncio
import sys
import termios
from datetime import datetime

from dotenv import load_dotenv

from app.note import render_terminal
from app.webhooks import handle_thumbtack_event
from .common import DIM, color
from .console_client import ConsoleMessagingClient


async def main() -> None:
    load_dotenv()
    negotiation_id = f"sim-{datetime.now():%Y%m%d-%H%M%S}"
    client = ConsoleMessagingClient()
    print(f"Simulated lead {negotiation_id}. Type as the lead.\n"
          "  /out <text>  reply by hand as the operator (the agent does not run)\n"
          "  /quit or Ctrl+D  end\n")

    while True:
        _drop_typed_ahead_input()
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if text == "/quit":
            break
        if not text:
            continue
        if text.startswith("/out "):
            client.add_operator_message(text.removeprefix("/out ").strip())
            print("(sent by hand)\n")
            continue

        print(color("… agent working", DIM))
        message = client.add_lead_message(text)
        replies_before = sum(1 for m in client.messages if m.sender == "agent")
        result = await handle_thumbtack_event(
            {
                "negotiationID": negotiation_id,
                "messageID": f"{negotiation_id}:{message.message_id}",
                "from": "Customer",
                "text": text,
                "sentAt": message.sent_at,
                "customer": {"displayName": "Sim Customer"},
            },
            messaging_client=client,
        )
        if result.get("note_to_operator"):
            print(render_terminal(result["note_to_operator"]) + "\n")
        elif sum(1 for m in client.messages if m.sender == "agent") == replies_before:
            print(color("nothing sent", DIM) + "\n")
        if not result.get("handled"):
            print(color(f"not handled: {result.get('reason')}", DIM) + "\n")


def _drop_typed_ahead_input() -> None:
    # Keys pressed while the agent was thinking (e.g. an extra Enter) sit unechoed in the terminal
    # buffer and would be read as the next message, printing a doubled "Customer: Customer:" prompt.
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin, termios.TCIFLUSH)


if __name__ == "__main__":
    asyncio.run(main())
