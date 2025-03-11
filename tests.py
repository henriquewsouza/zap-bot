import unittest
from mix_bot import (
    build_team_message,
    is_valid_partition,
    generate_valid_partitions,
    select_best_partition,
    user_levels,
)

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
        # Save the original user_levels and prepare test data.
        self.original_user_levels = user_levels.copy()
        user_levels.clear()
        # Set up some dummy user levels.
        # Regular users
        user_levels[1] = {"level": 10, "nickname": "User1"}
        user_levels[2] = {"level": 20, "nickname": "User2"}
        user_levels[3] = {"level": 30, "nickname": "User3"}
        user_levels[4] = {"level": 40, "nickname": "User4"}
        # Zapgod and JOTALHA with their specific IDs.
        self.zapgod_id = 291617683416285194
        self.jotalha_id = 692595982378074222
        user_levels[self.zapgod_id] = {"level": 50, "nickname": "Zapgod"}
        user_levels[self.jotalha_id] = {"level": 60, "nickname": "JOTALHA"}
        # Additional users to bring the total count up for partition testing.
        user_levels[11] = {"level": 15, "nickname": "User11"}
        user_levels[12] = {"level": 25, "nickname": "User12"}

    def tearDown(self):
        # Restore the original user_levels dictionary.
        user_levels.clear()
        user_levels.update(self.original_user_levels)

    def test_build_team_message(self):
        # Create two teams of fake members.
        member1 = FakeMember(1)
        member2 = FakeMember(2)
        member3 = FakeMember(3)
        member4 = FakeMember(4)
        team1 = [member1, member2]  # Levels: 10 and 20 (Total: 30)
        team2 = [member3, member4]  # Levels: 30 and 40 (Total: 70)

        message = build_team_message(team1, team2)

        self.assertIn("**Team 1:**", message)
        self.assertIn("Total Skill:** 30", message)
        self.assertIn("**Team 2:**", message)
        self.assertIn("Total Skill:** 70", message)
        self.assertIn("**Difference:** 40", message)

    def test_is_valid_partition_same_team(self):
        # When Zapgod and JOTALHA are in the same team, the partition should be invalid.
        zapgod = FakeMember(self.zapgod_id)
        jotalha = FakeMember(self.jotalha_id)
        other = FakeMember(1)

        team1 = [zapgod, jotalha]
        team2 = [other]
        self.assertFalse(is_valid_partition(team1, team2))

    def test_is_valid_partition_different_teams(self):
        # When Zapgod and JOTALHA are split between teams, the partition is valid.
        zapgod = FakeMember(self.zapgod_id)
        jotalha = FakeMember(self.jotalha_id)
        other = FakeMember(1)

        team1 = [zapgod, other]
        team2 = [jotalha]
        self.assertTrue(is_valid_partition(team1, team2))

    def test_generate_valid_partitions(self):
        # Create 10 fake members for testing partitions.
        members = []
        # Include Zapgod and JOTALHA.
        members.append(FakeMember(self.zapgod_id))
        members.append(FakeMember(self.jotalha_id))
        # Add eight additional members. We'll use some of the IDs already in user_levels and some new ones.
        additional_ids = [1, 2, 3, 4, 11, 12, 13, 14]
        for mid in additional_ids:
            if mid not in user_levels:
                user_levels[mid] = {"level": 20, "nickname": f"User{mid}"}
            members.append(FakeMember(mid))

        self.assertEqual(len(members), 10, "There should be exactly 10 members for testing.")

        partitions = generate_valid_partitions(members)
        # All partitions returned should satisfy the constraint.
        for diff, team1, team2 in partitions:
            self.assertTrue(is_valid_partition(team1, team2))
        self.assertGreater(len(partitions), 0, "At least one valid partition should be generated.")

    def test_select_best_partition(self):
        # Create dummy partitions: (difference, team1, team2)
        dummy_team1 = [FakeMember(1)]
        dummy_team2 = [FakeMember(2)]
        partition1 = (10, dummy_team1, dummy_team2)
        partition2 = (5, dummy_team1, dummy_team2)
        partition3 = (15, dummy_team1, dummy_team2)
        partitions = [partition1, partition2, partition3]

        best = select_best_partition(partitions)
        # The best partition should have the smallest difference (i.e., 5).
        self.assertEqual(best[0], 5)

if __name__ == '__main__':
    unittest.main()
