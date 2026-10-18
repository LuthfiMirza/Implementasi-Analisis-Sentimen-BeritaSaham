"""Execution edge cases; synthetic fixtures validate code, not strategy returns."""
import unittest
from audit_bsjp_exit import simulate, down, up, pnl

class ExecutionTests(unittest.TestCase):
    def bars(self,o,h,l,c):
        return [dict(time='09:00',open=o,high=h,low=l,close=c),dict(time='09:15',open=c,high=c,low=c,close=c)]

    def test_gap_is_not_filled_at_unavailable_stop(self):
        self.assertEqual(simulate(284,self.bars(250,260,240,252),'TRAIL2_ENTRY','OHLC')[0],250)

    def test_intrabar_order_changes_trailing_result(self):
        bars=self.bars(312,316,294,304)
        self.assertEqual(simulate(284,bars,'TRAIL2_OPEN','OHLC')[0],308)
        self.assertEqual(simulate(284,bars,'TRAIL2_OPEN','OLHC')[0],304)

    def test_stop_cannot_use_future_candle_high(self):
        bars=self.bars(100,101,97,98)
        bars.insert(1,dict(time='09:05',open=98,high=150,low=98,close=145))
        self.assertEqual(simulate(100,bars,'TRAIL2_ENTRY','OLHC')[0],98)

    def test_deadline_uses_open_not_future_high(self):
        bars=self.bars(100,100,100,100)
        bars[-1]['high']=130
        self.assertEqual(simulate(100,bars,'TP2.5_SL3','OHLC'),(100,'09:15','time_exit'))

    def test_rounding_and_fees(self):
        self.assertEqual(down(326*.98),318)
        self.assertEqual(up(284*1.025),292)
        self.assertAlmostEqual(pnl(284,312,703)[0],1883618.2)

if __name__=='__main__':
    unittest.main()
