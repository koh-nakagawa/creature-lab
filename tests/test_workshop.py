from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workshop as w

class WorkshopTests(unittest.TestCase):
    def test_deadline_is_not_extended_by_selection(self):
        s=w.Session('test',100);s.choose(0,'body','slug',155)
        self.assertEqual(s.deadline,160);self.assertEqual(s.state(160)['step_key'],'head')
    def test_late_choice_cannot_change_previous_part(self):
        s=w.Session('test',100);old=s.config['body'];s.choose(0,'body','slug',161)
        self.assertEqual(s.config['body'],old);self.assertEqual(s.index,1)
    def test_early_next_and_double_click(self):
        s=w.Session('test',100);s.advance(0,110);s.advance(0,111)
        self.assertEqual(s.index,1);self.assertEqual(s.deadline,170)
    def test_background_time_advances_all_six(self):
        s=w.Session('test',100);state=s.state(461)
        self.assertEqual(state['phase'],'complete');self.assertEqual(state['completed_at'],460)
        self.assertEqual(len(state['selections']),6)
    def test_completed_selection_is_frozen(self):
        s=w.Session('test',100);s.state(460);old=dict(s.config)
        s.choose(5,'expression','surprise',470);self.assertEqual(s.config,old)
    def test_automatic_values_override_manual_sliders(self):
        a=w.automatic_config({'size':40,'roundness':1.2,'tail_length':1.4,'eye_size':1.15,'eyes':'three'})
        b=w.automatic_config({'size':25,'roundness':.8,'tail_length':.6,'eye_size':.8,'eyes':'three'})
        self.assertEqual(a,b);self.assertEqual(a['size'],32);self.assertEqual(a['eye_size'],.85)
    def test_no_back_or_surface_step(self):
        s=w.Session('test',100)
        with self.assertRaises(ValueError):s.choose(0,'back','smooth',101)
        self.assertEqual(w.STEP_KEYS,('body','head','limbs','tail','eyes','expression'))
    def test_size_fit_stays_within_printable_bounds(self):
        self.assertEqual(w.next_size(32,300),None);self.assertEqual(w.next_size(25,800),None)
        self.assertGreaterEqual(w.next_size(32,450),25);self.assertLess(w.next_size(32,450),32)

if __name__=='__main__':unittest.main(verbosity=2)
