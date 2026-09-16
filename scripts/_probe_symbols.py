import onnxruntime as ort
import numpy as np
sess = ort.InferenceSession('models/tinytts.onnx', providers=['CPUExecutionProvider'])
def try_x(val):
    x = np.zeros((1, 1), dtype=np.int64); x[0,0] = val
    feeds = {'x': x, 'x_lengths': np.array([1],dtype=np.int64), 'sid': np.array([0],dtype=np.int64),
             'tone': np.zeros((1,1),dtype=np.int64), 'language': np.zeros((1,1),dtype=np.int64),
             'bert': np.zeros((1,1024,1),dtype=np.float32), 'ja_bert': np.zeros((1,768,1),dtype=np.float32),
             'noise_scale': np.array([0.667],dtype=np.float32), 'noise_scale_w': np.array([0.8],dtype=np.float32),
             'length_scale': np.array([1.0],dtype=np.float32)}
    try:
        sess.run(None, feeds)
        return True
    except Exception:
        return False
lo, hi = 0, 1
while try_x(hi) and hi < 4060:
    lo = hi; hi *= 2
while hi - lo > 1:
    mid = (lo + hi) // 2
    if try_x(mid): lo = mid
    else: hi = mid
print('RESULT n_symbols =', lo + 1)
