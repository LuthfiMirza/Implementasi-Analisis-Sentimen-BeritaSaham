import unittest
from research_bsjp_mcas_exit import candidate

class ActivationTests(unittest.TestCase):
    def test_opening_range_cannot_activate_inside_first_minute(self):
        bars=[dict(time='09:00',open=312,high=326,low=294,close=304),dict(time='09:01',open=304,high=310,low=300,close=308),dict(time='09:15',open=308,high=308,low=308,close=308)]
        self.assertEqual(candidate(284,bars,'BREAK1_TRAIL2','OHLC'),(308,'09:15','deadline'))

    def test_hard_stop_still_applies_before_activation(self):
        bars=[dict(time='09:00',open=284,high=286,low=260,close=270),dict(time='09:15',open=300,high=300,low=300,close=300)]
        self.assertEqual(candidate(284,bars,'BREAK1_TRAIL2','OHLC')[0],274)

    def test_wait_two_minutes_does_not_use_high_from_first_minute(self):
        bars=[dict(time='09:00',open=300,high=340,low=290,close=300),dict(time='09:02',open=300,high=304,low=290,close=294),dict(time='09:15',open=300,high=300,low=300,close=300)]
        self.assertEqual(candidate(284,bars,'WAIT2_TRAIL2','OHLC')[0],296)

if __name__=='__main__':unittest.main()
