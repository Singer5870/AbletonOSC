from ableton.v2.control_surface import ControlSurface
from _Framework.EncoderElement import EncoderElement
import Live

from . import abletonosc

import importlib
import traceback
import logging
import logging.handlers
import os

logger = logging.getLogger("abletonosc")

class Manager(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)

        # SetControl: "warning" by default; every listener change at "info" filled
        # the log to 4.4 GB. Raise it with /live/api/set/log_level while debugging.
        self.log_level = "warning"

        self.handlers = []
        self.midi_mappings = {}
        # Discrete mute/solo/arm — applied in receive_midi (not Live.MidiMap)
        self.midi_button_mappings = {}

        try:
            self.osc_server = abletonosc.OSCServer()
            self.parameter_smoother = abletonosc.ParameterSmoother()
            self.schedule_message(0, self.tick)

            self.start_logging()
            self.init_api()

            self.show_message("AbletonOSC: Listening for OSC on port %d" % abletonosc.OSC_LISTEN_PORT)
            logger.info("Started AbletonOSC on address %s" % str(self.osc_server._local_addr))
            logger.info(
                "Control path: continuous params use Live.MidiMap (MIDI CCs); "
                "OSC is for rebind/state only — do not use /set/volume for faders"
            )
        except OSError as msg:
            self.show_message("AbletonOSC: Couldn't bind to port %d (%s)" % (abletonosc.OSC_LISTEN_PORT, msg))
            logger.info("Couldn't bind to port %d (%s)" % (abletonosc.OSC_LISTEN_PORT, msg))


    def start_logging(self):
        """
        Start logging to a local logfile (logs/abletonosc.log),
        and relay error messages via OSC.
        """
        module_path = os.path.dirname(os.path.realpath(__file__))
        log_dir = os.path.join(module_path, "logs")
        if not os.path.exists(log_dir):
            os.mkdir(log_dir, 0o755)
        log_path = os.path.join(log_dir, "abletonosc.log")
        self.log_file_handler = logging.handlers.RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=2)
        self.log_file_handler.setLevel(self.log_level.upper())
        formatter = logging.Formatter('(%(asctime)s) [%(levelname)s] %(message)s')
        self.log_file_handler.setFormatter(formatter)
        logger.addHandler(self.log_file_handler)

        class LiveOSCErrorLogHandler(logging.StreamHandler):
            def emit(handler, record):
                message = record.getMessage()
                message = message[message.index(":") + 2:]
                try:
                    self.osc_server.send("/live/error", (message,))
                except OSError:
                    # If the connection is dead, silently ignore errors as there's not much more we can do
                    pass
        self.live_osc_error_handler = LiveOSCErrorLogHandler()
        self.live_osc_error_handler.setLevel(logging.ERROR)
        logger.addHandler(self.live_osc_error_handler)

    def stop_logging(self):
        logger.removeHandler(self.log_file_handler)
        logger.removeHandler(self.live_osc_error_handler)

    def init_api(self):
        def test_callback(params):
            self.show_message("Received OSC OK")
            self.osc_server.send("/live/test", ("ok",))
        def reload_callback(params):
            self.reload_imports()
        def get_log_level_callback(params):
            return (self.log_level,)
        def set_log_level_callback(params):
            log_level = params[0]
            assert log_level in ("debug", "info", "warning", "error", "critical")
            self.log_level = log_level
            self.log_file_handler.setLevel(self.log_level.upper())
        def show_message_callback(params):
            self.show_message(params[0])

        self.osc_server.add_handler("/live/test", test_callback)
        self.osc_server.add_handler("/live/api/reload", reload_callback)
        self.osc_server.add_handler("/live/api/get/log_level", get_log_level_callback)
        self.osc_server.add_handler("/live/api/set/log_level", set_log_level_callback)
        self.osc_server.add_handler("/live/api/show_message", show_message_callback)

        with self.component_guard():
            self.handlers = [
                abletonosc.SongHandler(self),
                abletonosc.ApplicationHandler(self),
                abletonosc.ClipHandler(self),
                abletonosc.ClipSlotHandler(self),
                abletonosc.TrackHandler(self),
                abletonosc.DeviceHandler(self),
                abletonosc.ViewHandler(self),
                abletonosc.SceneHandler(self),
                abletonosc.MidiMapHandler(self),
            ]

    def clear_api(self):
        self.osc_server.clear_handlers()
        for handler in self.handlers:
            handler.clear_api()

    def tick(self):
        """
        Process incoming OSC, then advance continuous parameter smoothing.
        """
        OSC_PROCESS_PASSES = abletonosc.constants.OSC_PROCESS_PASSES
        OSC_TICK_INTERVAL = abletonosc.constants.OSC_TICK_INTERVAL

        logger.debug("Tick...")
        for _ in range(max(1, OSC_PROCESS_PASSES)):
            self.osc_server.process()
        if hasattr(self, "parameter_smoother"):
            self.parameter_smoother.advance()
        self.schedule_message(OSC_TICK_INTERVAL, self.tick)

    def reload_imports(self):
        try:
            importlib.reload(abletonosc.smoothing)
            importlib.reload(abletonosc.constants)
            importlib.reload(abletonosc.application)
            importlib.reload(abletonosc.clip)
            importlib.reload(abletonosc.clip_slot)
            importlib.reload(abletonosc.device)
            importlib.reload(abletonosc.handler)
            importlib.reload(abletonosc.midimap)
            importlib.reload(abletonosc.osc_server)
            importlib.reload(abletonosc.scene)
            importlib.reload(abletonosc.song)
            importlib.reload(abletonosc.track)
            importlib.reload(abletonosc.view)
            importlib.reload(abletonosc)
        except Exception as e:
            exc = traceback.format_exc()
            logging.warning(exc)

        # Always re-init API even if clear fails — never leave an empty handler table.
        try:
            self.clear_api()
        except Exception:
            logging.warning("clear_api during reload failed:\n%s" % traceback.format_exc())
            try:
                self.osc_server.clear_handlers()
            except Exception:
                pass
            self.handlers = []

        try:
            self.parameter_smoother = abletonosc.ParameterSmoother()
            if not hasattr(self, "midi_mappings") or self.midi_mappings is None:
                self.midi_mappings = {}
            if not hasattr(self, "midi_button_mappings") or self.midi_button_mappings is None:
                self.midi_button_mappings = {}
            self.midi_mappings.clear()
            self.midi_button_mappings.clear()
            self.init_api()
            self.request_rebuild_midi_map()
            logger.info("Reloaded code")
            self.show_message("AbletonOSC: Reloaded")
        except Exception:
            logging.error("init_api during reload failed:\n%s" % traceback.format_exc())
            self.show_message("AbletonOSC: Reload failed — reselect Control Surface")

    def disconnect(self):
        self.show_message("Disconnecting...")
        logger.info("Disconnecting...")
        self.stop_logging()
        self.osc_server.shutdown()
        super().disconnect()

    def receive_midi(self, midi_bytes):
        """
        Handle discrete button CCs (mute/solo/arm). Continuous CCs are claimed by
        Live.MidiMap and do not arrive here.
        """
        if midi_bytes and len(midi_bytes) >= 3:
            status = midi_bytes[0] & 0xF0
            channel = midi_bytes[0] & 0x0F
            if status == 0xB0:  # control change
                cc = int(midi_bytes[1])
                value = int(midi_bytes[2])
                binding = self.midi_button_mappings.get((channel, cc))
                if binding is not None:
                    action, track_index = binding
                    try:
                        track = self.song.tracks[int(track_index)]
                        on = value >= 64
                        if action == "mute":
                            track.mute = on
                        elif action == "solo":
                            track.solo = on
                        elif action == "arm":
                            if track.can_be_armed:
                                track.arm = on
                    except Exception:
                        logger.warning(
                            "MIDI button ch=%d cc=%d failed:\n%s"
                            % (channel, cc, traceback.format_exc())
                        )
                    return
        super().receive_midi(midi_bytes)

    def build_midi_map(self, midi_map_handle):
        """
        Called by Live to build the MIDI map.

        Direct MidiMap bindings update parameters in Live's C++ core (same path as
        Launch Control scripts) — not on the AbletonOSC OSC tick.
        """
        logger.info(
            "Building MIDI map (%d continuous, %d buttons)..."
            % (len(self.midi_mappings), len(self.midi_button_mappings))
        )

        for channel, cc in list(self.midi_mappings.keys()):
            parameter = self.midi_mappings.get((channel, cc))
            if parameter is None:
                continue
            try:
                Live.MidiMap.map_midi_cc(
                    midi_map_handle,
                    parameter,
                    channel,
                    cc,
                    Live.MidiMap.MapMode.absolute,
                    True,  # avoid_takeover — SetControl is authoritative while moving
                )
                logger.debug(
                    "Mapped CC %d on channel %d to parameter %s" % (cc, channel, parameter.name)
                )
            except Exception:
                logger.warning(
                    "Failed to map CC %d ch %d: %s" % (cc, channel, traceback.format_exc())
                )
