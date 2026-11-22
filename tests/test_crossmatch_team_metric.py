import numpy as np
from scripts.research_crossmatch_team_metric import score


def test_scoring_separates_missing_and_unmatched_and_obeys_gate():
    centres=np.asarray([[1.,0.],[0.,1.]])
    rows=[((np.asarray([1.,0.]),centres),0,0),
          ((np.asarray([0.,1.]),centres),0,1),
          ((np.asarray([.5,.5]),centres),1,None),
          ((np.asarray([1.,0.]),centres),None,0)]
    scored=score(rows,'learned',0,.2)
    assert scored=={'matched':3,'correct':1,'wrong':1,'unknown':1,'unmatched_detection':1,'unmatched_assigned':1}
    swapped=score(rows,'learned',1,.2)
    assert swapped['correct']==1 and swapped['wrong']==1
