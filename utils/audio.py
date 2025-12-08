"""
Audio and MIDI processing utilities.
"""

import os
import numpy as np
import audioread
import librosa
from mido import MidiFile

from utils.vad import (
    note_detection_with_onset_offset_regress, 
    pedal_detection_with_onset_offset_regress
)
from utils import config


def create_folder(fd):
    """Create folder if it doesn't exist."""
    if not os.path.exists(fd):
        os.makedirs(fd)
        
        
def get_filename(path):
    """Get filename without extension from path."""
    path = os.path.realpath(path)
    na_ext = path.split('/')[-1]
    na = os.path.splitext(na_ext)[0]
    return na


def note_to_freq(piano_note):
    """Convert MIDI note number to frequency."""
    return 2 ** ((piano_note - 39) / 12) * 440


def float32_to_int16(x):
    """Convert float32 audio to int16."""
    assert np.max(np.abs(x)) <= 1.
    return (x * 32767.).astype(np.int16)


def int16_to_float32(x):
    """Convert int16 audio to float32."""
    return (x / 32767.).astype(np.float32)
    

def pad_truncate_sequence(x, max_len):
    """Pad or truncate sequence to specified length."""
    if len(x) < max_len:
        return np.concatenate((x, np.zeros(max_len - len(x))))
    else:
        return x[0:max_len]


def read_midi(midi_path):
    """Parse MIDI file.

    Args:
        midi_path: str

    Returns:
        midi_dict: dict with 'midi_event' and 'midi_event_time' keys
    """
    midi_file = MidiFile(midi_path)
    ticks_per_beat = midi_file.ticks_per_beat

    assert len(midi_file.tracks) == 2

    microseconds_per_beat = midi_file.tracks[0][0].tempo
    beats_per_second = 1e6 / microseconds_per_beat
    ticks_per_second = ticks_per_beat * beats_per_second

    message_list = []
    ticks = 0
    time_in_second = []

    for message in midi_file.tracks[1]:
        message_list.append(str(message))
        ticks += message.time
        time_in_second.append(ticks / ticks_per_second)

    midi_dict = {
        'midi_event': np.array(message_list), 
        'midi_event_time': np.array(time_in_second)
    }

    return midi_dict


def write_events_to_midi(start_time, note_events, pedal_events, midi_path):
    """Write out note events to MIDI file.

    Args:
        start_time: float
        note_events: list of dict with onset_time, offset_time, midi_note, velocity
        pedal_events: list of dict with onset_time, offset_time
        midi_path: str
    """
    from mido import Message, MidiFile, MidiTrack, MetaMessage
    
    ticks_per_beat = 384
    beats_per_second = 2
    ticks_per_second = ticks_per_beat * beats_per_second
    microseconds_per_beat = int(1e6 // beats_per_second)

    midi_file = MidiFile()
    midi_file.ticks_per_beat = ticks_per_beat

    # Track 0 - tempo and time signature
    track0 = MidiTrack()
    track0.append(MetaMessage('set_tempo', tempo=microseconds_per_beat, time=0))
    track0.append(MetaMessage('time_signature', numerator=4, denominator=4, time=0))
    track0.append(MetaMessage('end_of_track', time=1))
    midi_file.tracks.append(track0)

    # Track 1 - notes and pedals
    track1 = MidiTrack()
    message_roll = []

    for note_event in note_events:
        message_roll.append({
            'time': note_event['onset_time'], 
            'midi_note': note_event['midi_note'], 
            'velocity': note_event['velocity']
        })
        message_roll.append({
            'time': note_event['offset_time'], 
            'midi_note': note_event['midi_note'], 
            'velocity': 0
        })

    if pedal_events:
        for pedal_event in pedal_events:
            message_roll.append({
                'time': pedal_event['onset_time'], 
                'control_change': 64, 
                'value': 127
            })
            message_roll.append({
                'time': pedal_event['offset_time'], 
                'control_change': 64, 
                'value': 0
            })

    message_roll.sort(key=lambda note_event: note_event['time'])

    previous_ticks = 0
    for message in message_roll:
        this_ticks = int((message['time'] - start_time) * ticks_per_second)
        if this_ticks >= 0:
            diff_ticks = this_ticks - previous_ticks
            previous_ticks = this_ticks
            if 'midi_note' in message.keys():
                track1.append(Message(
                    'note_on', 
                    note=message['midi_note'], 
                    velocity=message['velocity'], 
                    time=diff_ticks
                ))
            elif 'control_change' in message.keys():
                track1.append(Message(
                    'control_change', 
                    channel=0, 
                    control=message['control_change'], 
                    value=message['value'], 
                    time=diff_ticks
                ))
    
    track1.append(MetaMessage('end_of_track', time=1))
    midi_file.tracks.append(track1)
    midi_file.save(midi_path)


class RegressionPostProcessor:
    """Postprocess model output probabilities to MIDI events."""
    
    def __init__(self, frames_per_second, classes_num, onset_threshold, 
                 offset_threshold, frame_threshold, pedal_offset_threshold):
        self.frames_per_second = frames_per_second
        self.classes_num = classes_num
        self.onset_threshold = onset_threshold
        self.offset_threshold = offset_threshold
        self.frame_threshold = frame_threshold
        self.pedal_offset_threshold = pedal_offset_threshold
        self.begin_note = config.begin_note
        self.velocity_scale = config.velocity_scale

    def output_dict_to_midi_events(self, output_dict):
        """Post process model outputs to MIDI events."""
        (est_on_off_note_vels, est_pedal_on_offs) = \
            self.output_dict_to_note_pedal_arrays(output_dict)

        est_note_events = self.detected_notes_to_events(est_on_off_note_vels)

        if est_pedal_on_offs is None:
            est_pedal_events = None
        else:
            est_pedal_events = self.detected_pedals_to_events(est_pedal_on_offs)

        return est_note_events, est_pedal_events

    def output_dict_to_note_pedal_arrays(self, output_dict):
        """Convert output dict to note and pedal arrays."""
        # Calculate binarized onset output from regression output
        (onset_output, onset_shift_output) = \
            self.get_binarized_output_from_regression(
                reg_output=output_dict['reg_onset_output'], 
                threshold=self.onset_threshold, neighbour=2)

        output_dict['onset_output'] = onset_output
        output_dict['onset_shift_output'] = onset_shift_output  

        # Calculate binarized offset output from regression output
        # Using neighbour=2 for more sensitive offset detection
        (offset_output, offset_shift_output) = \
            self.get_binarized_output_from_regression(
                reg_output=output_dict['reg_offset_output'], 
                threshold=self.offset_threshold, neighbour=2)

        output_dict['offset_output'] = offset_output
        output_dict['offset_shift_output'] = offset_shift_output

        if 'reg_pedal_offset_output' in output_dict.keys():
            (pedal_offset_output, pedal_offset_shift_output) = \
                self.get_binarized_output_from_regression(
                    reg_output=output_dict['reg_pedal_offset_output'], 
                    threshold=self.pedal_offset_threshold, neighbour=4)

            output_dict['pedal_offset_output'] = pedal_offset_output
            output_dict['pedal_offset_shift_output'] = pedal_offset_shift_output

        est_on_off_note_vels = self.output_dict_to_detected_notes(output_dict)

        if 'reg_pedal_onset_output' in output_dict.keys():
            est_pedal_on_offs = self.output_dict_to_detected_pedals(output_dict)
        else:
            est_pedal_on_offs = None    

        return est_on_off_note_vels, est_pedal_on_offs

    def get_binarized_output_from_regression(self, reg_output, threshold, neighbour):
        """Calculate binarized output from regression results."""
        binary_output = np.zeros_like(reg_output)
        shift_output = np.zeros_like(reg_output)
        (frames_num, classes_num) = reg_output.shape
        
        for k in range(classes_num):
            x = reg_output[:, k]
            for n in range(neighbour, frames_num - neighbour):
                if x[n] > threshold and self.is_monotonic_neighbour(x, n, neighbour):
                    binary_output[n, k] = 1
                    if x[n - 1] > x[n + 1]:
                        shift = (x[n + 1] - x[n - 1]) / (x[n] - x[n + 1]) / 2
                    else:
                        shift = (x[n + 1] - x[n - 1]) / (x[n] - x[n - 1]) / 2
                    shift_output[n, k] = shift

        return binary_output, shift_output

    def is_monotonic_neighbour(self, x, n, neighbour):
        """Detect if values are monotonic in both sides of x[n]."""
        monotonic = True
        for i in range(neighbour):
            if x[n - i] < x[n - i - 1]:
                monotonic = False
            if x[n + i] < x[n + i + 1]:
                monotonic = False
        return monotonic

    def output_dict_to_detected_notes(self, output_dict):
        """Postprocess output_dict to piano notes."""
        est_tuples = []
        est_midi_notes = []
        classes_num = output_dict['frame_output'].shape[-1]
 
        for piano_note in range(classes_num):
            est_tuples_per_note = note_detection_with_onset_offset_regress(
                frame_output=output_dict['frame_output'][:, piano_note], 
                onset_output=output_dict['onset_output'][:, piano_note], 
                onset_shift_output=output_dict['onset_shift_output'][:, piano_note], 
                offset_output=output_dict['offset_output'][:, piano_note], 
                offset_shift_output=output_dict['offset_shift_output'][:, piano_note], 
                velocity_output=output_dict['velocity_output'][:, piano_note], 
                frame_threshold=self.frame_threshold)
            
            est_tuples += est_tuples_per_note
            est_midi_notes += [piano_note + self.begin_note] * len(est_tuples_per_note)

        est_tuples = np.array(est_tuples)
        est_midi_notes = np.array(est_midi_notes)

        if len(est_tuples) == 0:
            return np.array([])
        else:
            onset_times = (est_tuples[:, 0] + est_tuples[:, 2]) / self.frames_per_second
            offset_times = (est_tuples[:, 1] + est_tuples[:, 3]) / self.frames_per_second
            velocities = est_tuples[:, 4]
            
            est_on_off_note_vels = np.stack(
                (onset_times, offset_times, est_midi_notes, velocities), axis=-1
            )
            est_on_off_note_vels = est_on_off_note_vels.astype(np.float32)
            return est_on_off_note_vels

    def output_dict_to_detected_pedals(self, output_dict):
        """Postprocess output_dict to piano pedals."""
        frames_num = output_dict['pedal_frame_output'].shape[0]
        
        est_tuples = pedal_detection_with_onset_offset_regress(
            frame_output=output_dict['pedal_frame_output'][:, 0], 
            offset_output=output_dict['pedal_offset_output'][:, 0], 
            offset_shift_output=output_dict['pedal_offset_shift_output'][:, 0], 
            frame_threshold=0.5)

        est_tuples = np.array(est_tuples)
        
        if len(est_tuples) == 0:
            return np.array([])
        else:
            onset_times = (est_tuples[:, 0] + est_tuples[:, 2]) / self.frames_per_second
            offset_times = (est_tuples[:, 1] + est_tuples[:, 3]) / self.frames_per_second
            est_on_off = np.stack((onset_times, offset_times), axis=-1)
            est_on_off = est_on_off.astype(np.float32)
            return est_on_off

    def detected_notes_to_events(self, est_on_off_note_vels):
        """Reformat detected notes to midi events."""
        midi_events = []
        for i in range(est_on_off_note_vels.shape[0]):
            midi_events.append({
                'onset_time': est_on_off_note_vels[i][0], 
                'offset_time': est_on_off_note_vels[i][1], 
                'midi_note': int(est_on_off_note_vels[i][2]), 
                'velocity': int(est_on_off_note_vels[i][3] * self.velocity_scale)
            })
        return midi_events

    def detected_pedals_to_events(self, pedal_on_offs):
        """Reformat detected pedal onset and offsets to events."""
        pedal_events = []
        for i in range(len(pedal_on_offs)):
            pedal_events.append({
                'onset_time': pedal_on_offs[i, 0], 
                'offset_time': pedal_on_offs[i, 1]
            })
        return pedal_events


def load_audio(path, sr=22050, mono=True, offset=0.0, duration=None,
               dtype=np.float32, res_type='kaiser_best', 
               backends=[audioread.ffdec.FFmpegAudioFile], ffmpeg_path=None):
    """Load audio using ffmpeg backend."""
    y = []
    with audioread.audio_open(
        os.path.realpath(path), backends=backends, ffmpeg_path=ffmpeg_path
    ) as input_file:
        sr_native = input_file.samplerate
        n_channels = input_file.channels

        s_start = int(np.round(sr_native * offset)) * n_channels

        if duration is None:
            s_end = np.inf
        else:
            s_end = s_start + (int(np.round(sr_native * duration)) * n_channels)

        n = 0

        for frame in input_file:
            frame = librosa.core.audio.util.buf_to_float(frame, dtype=dtype)
            n_prev = n
            n = n + len(frame)

            if n < s_start:
                continue

            if s_end < n_prev:
                break

            if s_end < n:
                frame = frame[:s_end - n_prev]

            if n_prev <= s_start <= n:
                frame = frame[(s_start - n_prev):]

            y.append(frame)

    if y:
        y = np.concatenate(y)

        if n_channels > 1:
            y = y.reshape((-1, n_channels)).T
            if mono:
                y = librosa.core.audio.to_mono(y)

        if sr is not None:
            y = librosa.core.audio.resample(y, orig_sr=sr_native, target_sr=sr, res_type=res_type)
        else:
            sr = sr_native

    y = np.ascontiguousarray(y, dtype=dtype)
    return (y, sr)

