#!/usr/bin/env python3
"""Export xlerobot-raw-v1 episodes to GR00T-compatible LeRobot v2."""
import argparse, json, shutil
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",default="collected_data/raw")
    parser.add_argument("--output",default="collected_data/lerobot_v2")
    parser.add_argument("--include-failures",action="store_true",help="also export episodes marked unsuccessful")
    args=parser.parse_args(); source=Path(args.input); out=Path(args.output)
    episodes=[]; tasks=[]; task_ids={}; global_index=0; names=None; fps=None
    (out/"meta").mkdir(parents=True,exist_ok=True); (out/"data/chunk-000").mkdir(parents=True,exist_ok=True)
    for camera in ("left","right"):(out/f"videos/chunk-000/observation.images.{camera}").mkdir(parents=True,exist_ok=True)
    for ep_path in sorted(source.glob("episode_*")):
        meta=json.loads((ep_path/"episode.json").read_text())
        if meta.get("format")!="xlerobot-raw-v1": continue
        if not meta.get("success",False) and not args.include_failures: continue
        names=meta["joint_names"]; fps=meta["fps"]; task=meta["task"]
        if task not in task_ids:
            task_ids[task]=len(task_ids); tasks.append({"task_index":task_ids[task],"task":task})
        rows=[]
        for line in (ep_path/"frames.jsonl").read_text().splitlines():
            frame=json.loads(line); rows.append({
                "observation.state":frame["observation_state"], "action":frame["action"],
                "timestamp":frame["timestamp"], "task_index":task_ids[task],
                "annotation.human.task_description":task_ids[task],
                "episode_index":len(episodes), "index":global_index,
                "next.reward":float(bool(meta["success"])), "next.done":False,
            }); global_index+=1
        if not rows: continue
        rows[-1]["next.done"]=True
        pq.write_table(pa.Table.from_pylist(rows),out/f"data/chunk-000/episode_{len(episodes):06d}.parquet")
        for camera in ("left","right"):
            shutil.copy2(ep_path/f"{camera}.mp4",out/f"videos/chunk-000/observation.images.{camera}/episode_{len(episodes):06d}.mp4")
        episodes.append({"episode_index":len(episodes),"tasks":[task],"length":len(rows),"success":meta["success"]})
    if not episodes: raise SystemExit("No completed raw episodes found")
    def jsonl(path,values): path.write_text("".join(json.dumps(v,ensure_ascii=False)+"\n" for v in values))
    jsonl(out/"meta/tasks.jsonl",tasks); jsonl(out/"meta/episodes.jsonl",episodes)
    info={"codebase_version":"v2.1","robot_type":"xlerobot","total_episodes":len(episodes),"total_frames":global_index,"fps":fps,"features":{"observation.state":{"dtype":"float32","shape":[len(names)],"names":names},"action":{"dtype":"float32","shape":[len(names)],"names":names},"observation.images.left":{"dtype":"video"},"observation.images.right":{"dtype":"video"}}}
    (out/"meta/info.json").write_text(json.dumps(info,ensure_ascii=False,indent=2)+"\n")
    split={"left_arm":{"start":0,"end":6},"right_arm":{"start":6,"end":12},"head":{"start":12,"end":14}}
    modality={"state":split,"action":split,"video":{"left":{"original_key":"observation.images.left"},"right":{"original_key":"observation.images.right"}},"annotation":{"human.task_description":{}}}
    (out/"meta/modality.json").write_text(json.dumps(modality,ensure_ascii=False,indent=2)+"\n")
    print(f"Exported {len(episodes)} episodes / {global_index} frames to {out}")
if __name__=="__main__": main()
