import json
from pathlib import Path
from app.reviewed_identity_swap import correct_frame


def test_confirmed_swap_is_bijective_bounded_and_geometry_preserving():
    answer=json.loads((Path(__file__).parent/'fixtures/reviewed_swap_563_748.json').read_text(encoding='utf-8'))
    rows=[[10,20,30,60,563],[50,20,70,60,748],[80,20,90,60,99]]
    corrected,applied=correct_frame(35.4,rows,answer)
    assert applied and [r[4] for r in corrected]==[748,563,99]
    assert [r[:4] for r in corrected]==[r[:4] for r in rows]
    assert rows[0][4]==563
    for t in (35.2,35.8):assert correct_frame(t,rows,answer)==(rows,False)
    assert correct_frame(35.4,rows[:1],answer)==(rows[:1],False)
    assert correct_frame(35.4,rows+[rows[0]],answer)==(rows+[rows[0]],False)
