"""Print eval_model.py JSON reports side by side. usage: python vision/tools/summarize_eval.py a.json [b.json ...]"""
import json
import sys

for f in sys.argv[1:]:
    d = json.load(open(f))
    print(f"== {f}  ({d['model']})")
    for k, v in d["per_gauge"].items():
        print(f"  {k}")
        for m in ("stage_a", "stage_b", "fused"):
            print(f"    {m:8s} {v[m]}")
        print(f"    uncertain frames {v['fused_uncertain_frames']}, worst fused {v['fused_worst(err,true,A,B)']}, "
              f"stage B {v['stage_b_ms_median']} ms")
    print("  real photos:", d["real_photos"])
