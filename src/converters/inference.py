"""
Piano converter engine using ONNX model.
"""

import numpy as np
from librosa.filters import mel as librosa_mel_fn
from librosa import stft, power_to_db

from utils.audio import RegressionPostProcessor, write_events_to_midi
from utils import config


def append_to_dict(dict, key, value):
    if key in dict.keys():
        dict[key].append(value)
    else:
        dict[key] = [value]
 

def output_to_dict(note_output, pedal_output):
    full_output_dict = {
        'reg_onset_output': note_output[0], 
        'reg_offset_output': note_output[1], 
        'frame_output': note_output[2], 
        'velocity_output': note_output[3],
        'reg_pedal_onset_output': pedal_output[0], 
        'reg_pedal_offset_output': pedal_output[1],
        'pedal_frame_output': pedal_output[2]
    }
    return full_output_dict


def forward(model, x, batch_size, setProgressBarValue, setProgressBarVisibility,
            setProgressBarFullValue, logUpdate=print, frames_per_second=100):
    """Forward data to model in mini-batch."""
    sample_rate = 16000
    window_size = 2048
    hop_size = sample_rate // frames_per_second
    mel_bins = 229
    fmin = 30
    fmax = sample_rate // 2

    window = 'hann'
    center = True
    pad_mode = 'reflect'
    ref = 1.0
    amin = 1e-10
    top_db = None

    logmel = librosa_mel_fn(
        sr=sample_rate, n_fft=window_size, n_mels=mel_bins,
        fmin=fmin, fmax=fmax
    ).T

    output_dict = {}
    
    pointer = 0
    total_segments = int(np.ceil(len(x) / batch_size))
    setProgressBarFullValue(total_segments)
    setProgressBarVisibility(True)
    
    while True:
        logUpdate('Segment {} / {}'.format(pointer, total_segments))
        setProgressBarValue(pointer)
        if pointer >= len(x):
            break

        batch_waveform = x[pointer:pointer + batch_size]
        pointer += batch_size

        batch_waveform = stft(
            y=batch_waveform, n_fft=window_size,
            hop_length=hop_size, win_length=window_size, window=window,
            center=center, pad_mode=pad_mode,
        )
        
        mel_spectrogram = np.dot(
            np.abs(np.transpose(batch_waveform, axes=(0, 2, 1))) ** 2, logmel
        )
        logmel_spectrogram = power_to_db(
            mel_spectrogram, ref=ref, amin=amin, top_db=top_db
        )
        batch_waveform = np.expand_dims(logmel_spectrogram, axis=1)

        # Run ONNX inference
        outputs = model.run(None, {'input': batch_waveform.astype(np.float32)})
        note_stacked = outputs[0]
        pedal_stacked = outputs[1]
        
        note_output = [note_stacked[i] for i in range(4)]
        pedal_output = [pedal_stacked[i] for i in range(3)]
        batch_output_dict = output_to_dict(note_output, pedal_output)

        for key in batch_output_dict.keys():
            append_to_dict(output_dict, key, batch_output_dict[key])

    for key in output_dict.keys():
        output_dict[key] = np.concatenate(output_dict[key], axis=0)

    setProgressBarVisibility(False)
    return output_dict


class PianoConverter:
    """Piano converter using ONNX model."""
    
    def __init__(self, model, checkpoint_path=None, segment_samples=16000*10):
        self.segment_samples = segment_samples
        self.frames_per_second = config.frames_per_second
        self.classes_num = config.classes_num
        # Thresholds for note detection
        # onset_threshold: sensitivity for detecting note starts
        # offset_threshold: sensitivity for detecting note ends (lower = more sensitive)
        # frame_threshold: when sound energy falls below this, note ends
        self.onset_threshold = 0.3
        self.offset_threshod = 0.1   # Low threshold to detect note endings
        self.frame_threshold = 0.5   # Higher = notes end when sound fades
        self.pedal_offset_threshold = 0.2
        self.model = model

    def transcribe(self, audio, midi_path, setProgressBarValue,
                   setProgressBarVisibility, setProgressBarFullValue, logUpdate=print):
        """Transcribe audio to MIDI."""
        audio = audio[None, :]

        audio_len = audio.shape[1]
        pad_len = int(np.ceil(audio_len / self.segment_samples)) \
            * self.segment_samples - audio_len

        audio = np.concatenate((audio, np.zeros((1, pad_len))), axis=1)

        segments = self.enframe(audio, self.segment_samples)

        output_dict = forward(
            self.model, segments, batch_size=1,
            setProgressBarValue=setProgressBarValue,
            setProgressBarFullValue=setProgressBarFullValue,
            setProgressBarVisibility=setProgressBarVisibility,
            logUpdate=logUpdate,
            frames_per_second=self.frames_per_second
        )

        for key in output_dict.keys():
            output_dict[key] = self.deframe(output_dict[key])[0:audio_len]

        post_processor = RegressionPostProcessor(
            self.frames_per_second, 
            classes_num=self.classes_num, 
            onset_threshold=self.onset_threshold, 
            offset_threshold=self.offset_threshod, 
            frame_threshold=self.frame_threshold, 
            pedal_offset_threshold=self.pedal_offset_threshold
        )

        (est_note_events, est_pedal_events) = \
            post_processor.output_dict_to_midi_events(output_dict)

        if midi_path:
            write_events_to_midi(
                start_time=0, note_events=est_note_events, 
                pedal_events=est_pedal_events, midi_path=midi_path
            )
            logUpdate('Write out to {}'.format(midi_path))

        transcribed_dict = {
            'output_dict': output_dict, 
            'est_note_events': est_note_events,
            'est_pedal_events': est_pedal_events
        }

        return transcribed_dict

    def enframe(self, x, segment_samples):
        """Enframe long sequence to short segments."""
        assert x.shape[1] % segment_samples == 0
        batch = []

        pointer = 0
        while pointer + segment_samples <= x.shape[1]:
            batch.append(x[:, pointer:pointer + segment_samples])
            pointer += segment_samples // 2

        batch = np.concatenate(batch, axis=0)
        return batch

    def deframe(self, x):
        """Deframe predicted segments to original sequence."""
        if x.shape[0] == 1:
            return x[0]
        else:
            x = x[:, 0:-1, :]
            (N, segment_samples, classes_num) = x.shape
            assert segment_samples % 4 == 0

            y = []
            y.append(x[0, 0:int(segment_samples * 0.75)])
            for i in range(1, N - 1):
                y.append(x[i, int(segment_samples * 0.25):int(segment_samples * 0.75)])
            y.append(x[-1, int(segment_samples * 0.25):])
            y = np.concatenate(y, axis=0)
            return y

