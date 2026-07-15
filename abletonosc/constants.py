#--------------------------------------------------------------------------------
# Constants used in AbletonOSC (SetControl fork — parameter smoothing)
#--------------------------------------------------------------------------------

OSC_LISTEN_PORT = 11000
OSC_RESPONSE_PORT = 11001

# Live ControlSurface schedule_message ticks (1 tick ≈ 100ms).
# Keep at 1 for stability; smoothing uses substeps below for faster parameter motion.
OSC_TICK_INTERVAL = 1

# How many times osc_server.process() runs each tick (drains UDP queue).
OSC_PROCESS_PASSES = 2

# Continuous parameter updates applied per tick (1 tick ≈ 100ms → 10 ≈ 100 Hz).
SMOOTHING_ENABLED = True
SMOOTH_STEPS_PER_TICK = 10
SMOOTH_STEP_FACTOR = 0.42  # fraction of remaining delta applied each substep
SMOOTH_EPSILON = 1e-6

# Object properties that are always applied immediately (toggles, enums, strings, triggers).
DISCRETE_OBJECT_PROPERTIES = {
    "track": {
        "arm",
        "mute",
        "solo",
        "fold_state",
        "current_monitoring_state",
        "color",
        "color_index",
        "name",
    },
    "song": {
        "arrangement_overdub",
        "back_to_arranger",
        "clip_trigger_quantization",
        "current_song_time",
        "is_ableton_link_enabled",
        "loop",
        "metronome",
        "midi_recording_quantization",
        "nudge_down",
        "nudge_up",
        "punch_in",
        "punch_out",
        "record_mode",
        "root_note",
        "scale_name",
        "session_record",
        "signature_denominator",
        "signature_numerator",
    },
    "clip_slot": {
        "has_stop_button",
    },
    "scene": {
        "color",
        "name",
    },
    "clip": {
        "color",
        "color_index",
        "launch_mode",
        "launch_quantization",
        "legato",
        "looping",
        "muted",
        "name",
        "pitch_coarse",
        "pitch_fine",
        "position",
        "ram_mode",
        "warp_mode",
        "warping",
    },
}

CONTINUOUS_OBJECT_PROPERTIES = {
    "song": {
        "tempo",
        "groove_amount",
        "loop_length",
        "loop_start",
    },
    "clip": {
        "end_marker",
        "gain",
        "loop_end",
        "loop_start",
        "start_marker",
        "velocity_amount",
    },
}
