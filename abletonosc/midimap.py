from .handler import AbletonOSCHandler
from typing import Tuple, Any


class MidiMapHandler(AbletonOSCHandler):
    """
    Map MIDI CCs onto Live via:
      - Live.MidiMap (C++ path) for continuous DeviceParameters (volume, pan, sends)
      - receive_midi button table for discrete track props (mute/solo/arm)

    SetControl owns hardware and mirrors motion as CCs into AbletonOSC's
    Control Surface MIDI Input (virtual port). OSC only rebinds targets.
    """

    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "midimap"
        self.midi_map_handle = None

    def init_api(self):
        if not hasattr(self.manager, "midi_button_mappings") or self.manager.midi_button_mappings is None:
            self.manager.midi_button_mappings = {}
        if not hasattr(self.manager, "midi_mappings") or self.manager.midi_mappings is None:
            self.manager.midi_mappings = {}

        def map_device_cc(params: Tuple[Any] = ()):
            track_index = int(params[0])
            device_index = int(params[1])
            parameter_index = int(params[2])
            channel = int(params[3])
            cc = int(params[4])

            parameter = self.song.tracks[track_index].devices[device_index].parameters[parameter_index]
            self._store_cc_mapping(channel, cc, parameter)
            self.manager.request_rebuild_midi_map()
            return (track_index, device_index, parameter_index, channel, cc)

        def map_track_volume(params: Tuple[Any] = ()):
            track_index = int(params[0])
            channel = int(params[1])
            cc = int(params[2])
            parameter = self.song.tracks[track_index].mixer_device.volume
            self._store_cc_mapping(channel, cc, parameter)
            self.manager.request_rebuild_midi_map()
            return (track_index, channel, cc)

        def map_track_panning(params: Tuple[Any] = ()):
            track_index = int(params[0])
            channel = int(params[1])
            cc = int(params[2])
            parameter = self.song.tracks[track_index].mixer_device.panning
            self._store_cc_mapping(channel, cc, parameter)
            self.manager.request_rebuild_midi_map()
            return (track_index, channel, cc)

        def map_mixer_volumes(params: Tuple[Any] = ()):
            """
            Map a contiguous page of track volumes (Live.MidiMap / C++).
            params: channel, first_cc, track_start, count
            """
            channel = int(params[0])
            first_cc = int(params[1])
            track_start = int(params[2])
            count = int(params[3])
            mapped = self._map_mixer_params(
                channel, first_cc, track_start, count, "volume"
            )
            self.manager.request_rebuild_midi_map()
            return (channel, first_cc, track_start, mapped)

        def map_mixer_panning(params: Tuple[Any] = ()):
            channel = int(params[0])
            first_cc = int(params[1])
            track_start = int(params[2])
            count = int(params[3])
            mapped = self._map_mixer_params(
                channel, first_cc, track_start, count, "panning"
            )
            self.manager.request_rebuild_midi_map()
            return (channel, first_cc, track_start, mapped)

        def map_mixer_mutes(params: Tuple[Any] = ()):
            """Discrete mute — MIDI CC via receive_midi (not Live.MidiMap)."""
            return self._map_mixer_buttons(params, "mute")

        def map_mixer_solos(params: Tuple[Any] = ()):
            return self._map_mixer_buttons(params, "solo")

        def map_mixer_arms(params: Tuple[Any] = ()):
            return self._map_mixer_buttons(params, "arm")

        def clear_maps(params: Tuple[Any] = ()):
            self.manager.midi_mappings.clear()
            self.manager.midi_button_mappings.clear()
            self.manager.request_rebuild_midi_map()
            return (0,)

        def clear_channel(params: Tuple[Any] = ()):
            channel = int(params[0])
            cc_deleted = 0
            for key in [k for k in self.manager.midi_mappings if k[0] == channel]:
                del self.manager.midi_mappings[key]
                cc_deleted += 1
            btn_deleted = 0
            for key in [k for k in self.manager.midi_button_mappings if k[0] == channel]:
                del self.manager.midi_button_mappings[key]
                btn_deleted += 1
            self.manager.request_rebuild_midi_map()
            return (channel, cc_deleted, btn_deleted)

        self.osc_server.add_handler("/live/midimap/map_cc", map_device_cc)
        self.osc_server.add_handler("/live/midimap/map_track_volume", map_track_volume)
        self.osc_server.add_handler("/live/midimap/map_track_panning", map_track_panning)
        self.osc_server.add_handler("/live/midimap/map_mixer_volumes", map_mixer_volumes)
        self.osc_server.add_handler("/live/midimap/map_mixer_panning", map_mixer_panning)
        self.osc_server.add_handler("/live/midimap/map_mixer_mutes", map_mixer_mutes)
        self.osc_server.add_handler("/live/midimap/map_mixer_solos", map_mixer_solos)
        self.osc_server.add_handler("/live/midimap/map_mixer_arms", map_mixer_arms)
        self.osc_server.add_handler("/live/midimap/clear", clear_maps)
        self.osc_server.add_handler("/live/midimap/clear_channel", clear_channel)
        self.logger.info(
            "MidiMap handlers ready "
            "(volumes/panning=Live.MidiMap, mute/solo/arm=MIDI buttons)"
        )

    def _map_mixer_params(
        self, channel: int, first_cc: int, track_start: int, count: int, prop: str
    ) -> int:
        mapped = 0
        num_tracks = len(self.song.tracks)
        for i in range(count):
            cc = first_cc + i
            if cc < 0 or cc > 127:
                break
            self.manager.midi_mappings.pop((channel, cc), None)
            self.manager.midi_button_mappings.pop((channel, cc), None)
            track_index = track_start + i
            if track_index < 0 or track_index >= num_tracks:
                continue
            parameter = getattr(self.song.tracks[track_index].mixer_device, prop)
            self._store_cc_mapping(channel, cc, parameter)
            mapped += 1
        return mapped

    def _map_mixer_buttons(self, params: Tuple[Any], action: str) -> Tuple:
        channel = int(params[0])
        first_cc = int(params[1])
        track_start = int(params[2])
        count = int(params[3])
        mapped = 0
        num_tracks = len(self.song.tracks)
        for i in range(count):
            cc = first_cc + i
            if cc < 0 or cc > 127:
                break
            # Buttons must not also be Live.MidiMap CCs
            self.manager.midi_mappings.pop((channel, cc), None)
            track_index = track_start + i
            if track_index < 0 or track_index >= num_tracks:
                self.manager.midi_button_mappings.pop((channel, cc), None)
                continue
            self.manager.midi_button_mappings[(channel, cc)] = (action, track_index)
            mapped += 1
            self.logger.info(
                "MidiButton: ch=%d cc=%d -> %s track %d" % (channel, cc, action, track_index)
            )
        return (channel, first_cc, track_start, mapped)

    def _store_cc_mapping(self, channel: int, cc: int, parameter) -> None:
        self.manager.midi_button_mappings.pop((int(channel), int(cc)), None)
        self.manager.midi_mappings[(int(channel), int(cc))] = parameter
        self.logger.info(
            "MidiMap: ch=%d cc=%d -> %s" % (channel, cc, getattr(parameter, "name", parameter))
        )
