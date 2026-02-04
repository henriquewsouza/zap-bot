import unittest
from zap_bot.team_balance import build_team_message, generate_partitions

# A fake member class to simulate discord.Member objects
class FakeMember:
    def __init__(self, member_id, display_name=None):
        self.id = member_id
        self.display_name = display_name or f"User{member_id}"

    @property
    def mention(self):
        return f"<@{self.id}>"

class TestBotFunctions(unittest.TestCase):
    def setUp(self):
        self.levels = {
            1: 10,
            2: 20,
            3: 30,
            4: 40,
            11: 15,
            12: 25,
        }

    def tearDown(self):
        pass

    def test_build_team_message(self):
        # Create two teams of fake members.
        member1 = FakeMember(1)
        member2 = FakeMember(2)
        member3 = FakeMember(3)
        member4 = FakeMember(4)
        team1 = [member1, member2]  # Levels: 10 and 20 (Total: 30)
        team2 = [member3, member4]  # Levels: 30 and 40 (Total: 70)

        message = build_team_message(
            team1,
            team2,
            get_level=lambda m: self.levels[m.id],
            get_mention=lambda m: m.mention,
        )

        self.assertIn("**Team 1:**", message)
        self.assertIn("**Total Skill:** 30 vs 70", message)
        self.assertIn("**Team 2:**", message)
        self.assertIn("**Difference:** 40", message)

    def test_generate_partitions(self):
        # Create 6 fake members for testing partitions.
        members = []
        for mid in [1, 2, 3, 4, 11, 12]:
            members.append(FakeMember(mid))

        partitions = generate_partitions(members, get_level=lambda m: self.levels[m.id])
        self.assertGreater(len(partitions), 0)
        # Ensure sorted by diff ascending
        diffs = [p.diff for p in partitions]
        self.assertEqual(diffs, sorted(diffs))

if __name__ == '__main__':
    unittest.main()
