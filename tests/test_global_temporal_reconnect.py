import unittest
from unittest.mock import patch
from app.global_temporal_reconnect import GlobalTemporalLinker


class GlobalTemporalTests(unittest.TestCase):
    def linker(self):
        m={'threshold':.9,'ambiguity_margin':.15,'max_prediction_residual_heights':1.5}
        link=GlobalTemporalLinker(m)
        link.memory['9']={'first':-1.,'last':0.,'canonical':'9',
            'history':[{'time':0.,'box':[0,0,10,20],'descriptor':None}],'decided':True}
        return link

    @patch('app.global_temporal_reconnect.temporal_score',return_value=.99)
    @patch('app.global_temporal_reconnect.sequence_features',return_value=[0.]*14)
    @patch('app.global_temporal_reconnect.descriptor',return_value=None)
    def test_confirm_third_observation_and_reactivation_collision(self,*_):
        link=self.linker()
        row=[[0,0,10,20,1]]
        for t in (.2,.4):
            mapping,events=link.update(t,None,row)
            self.assertEqual(events,[])
            self.assertEqual(mapping,{'1':'1'})
        mapping,events=link.update(.6,None,row)
        self.assertEqual(mapping,{'1':'9'})
        self.assertEqual(events[0]['birth_time'],.2)
        self.assertEqual(events[0]['time'],.6)
        mapping,_=link.update(.8,None,row+[[20,0,30,20,9]])
        self.assertEqual(len(set(mapping.values())),2)

    @patch('app.global_temporal_reconnect.temporal_score',return_value=.99)
    @patch('app.global_temporal_reconnect.sequence_features',return_value=[0.]*14)
    @patch('app.global_temporal_reconnect.descriptor',return_value=None)
    def test_simultaneous_competing_births_abstain(self,*_):
        link=self.linker()
        for t in (.2,.4,.6):
            mapping,events=link.update(t,None,[[0,0,10,20,1],[20,0,30,20,2]])
        self.assertEqual(events,[])
        self.assertEqual(mapping,{'1':'1','2':'2'})


if __name__=='__main__':
    unittest.main()
