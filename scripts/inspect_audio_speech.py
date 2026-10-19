from faster_whisper import WhisperModel
import soundfile as sf
import numpy as np

model = WhisperModel('base', device='cpu', compute_type='int8')
raw, sr = sf.read('data/sources/src_0Gi5Z51KdUE/restoration_cut/source_asmr.wav')
mono = raw.mean(axis=1).astype(np.float32)
segs, info = model.transcribe(mono, language='en')
segs = list(segs)
print(f'Detected {len(segs)} speech segments in raw audio:')
for s in segs:
    print(f'  [{s.start:.2f}s - {s.end:.2f}s]: "{s.text}"')

# Also calculate RMS of segments with speech vs segments WITHOUT speech
speech_mask = np.zeros(len(mono), dtype=bool)
for s in segs:
    i0 = max(0, int(s.start * sr))
    i1 = min(len(mono), int(s.end * sr))
    speech_mask[i0:i1] = True

non_speech = mono[~speech_mask]
speech_only = mono[speech_mask]

rms_non_speech = np.sqrt(np.mean(non_speech**2)) if len(non_speech) > 0 else 0
rms_speech = np.sqrt(np.mean(speech_only**2)) if len(speech_only) > 0 else 0

print(f"Non-speech (pure ASMR) duration: {len(non_speech)/sr:.1f}s, RMS: {rms_non_speech:.4f}")
print(f"Speech duration: {len(speech_only)/sr:.1f}s, RMS: {rms_speech:.4f}")
