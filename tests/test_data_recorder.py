import json
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from data_collection.recorder import EpisodeRecorder


class RecorderTests(unittest.TestCase):
    def test_complete_and_discard_episode(self):
        ok, jpg=cv2.imencode('.jpg',np.zeros((24,32,3),np.uint8)); self.assertTrue(ok)
        def snapshot():
            return {'observation_state':[1.0,2.0],'action':[1.5,2.5],
                    'following_error':[.5,.5],'camera_age_s':{'left':0,'right':0},
                    'images':{'left':jpg.tobytes(),'right':jpg.tobytes()}}
        with tempfile.TemporaryDirectory() as tmp:
            recorder=EpisodeRecorder(Path(tmp),['joint_a','joint_b'],snapshot,fps=10)
            recorder.start('pick block'); time.sleep(.25)
            result=recorder.finish(True)
            episode=Path(result['path'])
            self.assertTrue((episode/'left.mp4').exists())
            self.assertTrue((episode/'right.mp4').exists())
            rows=(episode/'frames.jsonl').read_text().splitlines()
            self.assertGreaterEqual(len(rows),2)
            self.assertEqual(json.loads(rows[0])['action'],[1.5,2.5])
            self.assertTrue(json.loads((episode/'episode.json').read_text())['success'])
            recorder.start('discard me'); time.sleep(.12); recorder.discard()
            self.assertEqual(len(list(Path(tmp).glob('episode_*'))),1)

if __name__=='__main__': unittest.main()
