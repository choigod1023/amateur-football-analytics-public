"""Write a new offline scene result; never overwrite human answers or live output."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.reviewed_scene import reviewed_scene
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace');p.add_argument('video');p.add_argument('answer');p.add_argument('output');a=p.parse_args()
    result=reviewed_scene(a.trace,a.video,json.loads(Path(a.answer).read_text(encoding='utf-8')))
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print({key:{'tracks':len(result[key]['tracks']),'joins':result[key]['joins'],'dropped':result[key]['dropped']} for key in ('before','after')})
