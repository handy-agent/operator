# What it does: Unit tests for ReplyScheduler — batching a burst of lead messages into one reply,
#   and a follow-up turn for messages that arrive while a reply is being written.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import unittest

from app.reply_timing import ReplyScheduler


class ReplySchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def test_burst_of_messages_gets_one_reply(self):
        turns = []

        async def run_turn(key, texts):
            turns.append((key, texts))

        scheduler = ReplyScheduler(run_turn, delay_min=0.05, delay_max=0.05, max_wait=1)
        scheduler.add("neg-1", "here's the link")
        await asyncio.sleep(0.02)
        scheduler.add("neg-1", "Friday works")
        await asyncio.sleep(0.2)

        self.assertEqual(turns, [("neg-1", ["here's the link", "Friday works"])])

    async def test_message_during_reply_gets_follow_up_turn(self):
        turns = []

        async def run_turn(key, texts):
            turns.append(texts)
            await asyncio.sleep(0.1)

        scheduler = ReplyScheduler(run_turn, delay_min=0.01, delay_max=0.01, max_wait=1)
        scheduler.add("neg-1", "first")
        await asyncio.sleep(0.05)
        scheduler.add("neg-1", "second")
        await asyncio.sleep(0.3)

        self.assertEqual(turns, [["first"], ["second"]])

    async def test_new_leads_first_message_is_answered_right_away(self):
        turns = []

        async def run_turn(key, texts):
            turns.append(texts)

        scheduler = ReplyScheduler(run_turn, delay_min=10, delay_max=10, max_wait=60)
        scheduler.add("neg-1", "need a dresser built", immediate=True)
        await asyncio.sleep(0.05)

        self.assertEqual(turns, [["need a dresser built"]])

    async def test_max_wait_caps_a_long_burst(self):
        turns = []

        async def run_turn(key, texts):
            turns.append(texts)

        scheduler = ReplyScheduler(run_turn, delay_min=0.1, delay_max=0.1, max_wait=0.15)
        for i in range(5):
            scheduler.add("neg-1", str(i))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

        self.assertEqual(turns[0][:3], ["0", "1", "2"])
        self.assertEqual(sum(len(t) for t in turns), 5)


if __name__ == "__main__":
    unittest.main()
