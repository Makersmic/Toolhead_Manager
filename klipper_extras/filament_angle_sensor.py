# Filament travel from an AS5600 angle sensor on an analog pin.
#
# Part of the Rhino Tool Manager (github.com/Makersmic/Toolhead_Manager); install.sh links it into
# klippy/extras/. Wiring and design: docs/proposal-filament-encoder.md, docs/filament-encoder-wiring.pdf.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
from . import filament_switch_sensor

SAMPLE_TIME = 0.001
SAMPLE_COUNT = 8
CHECK_TIME = 0.250        # how often commanded and measured travel are compared while printing
SAVED_VAR = 'filament_encoder_%s_circumference'


class FilamentAngleSensor:
    """[filament_angle_sensor name]

    The AS5600 gives the wheel's angle as 0..VCC over one turn. Each sample (every report_time) is taken as
    a fraction of a turn; the difference to the previous sample is wrapped into -0.5..+0.5 turns and summed,
    so travel is continuous across the wrap. Turns x wheel_circumference is millimetres of filament.

    While printing, every detection_length of commanded extrusion must see at least min_travel_ratio of it
    measured; if not, Klipper's own runout helper fires (pause_on_runout, runout_gcode), exactly like
    [filament_motion_sensor]. SET_FILAMENT_SENSOR and QUERY_FILAMENT_SENSOR work as for any filament sensor.
    Nothing is compared when not printing.
    """
    cmd_CALIBRATE_help = "Extrude LENGTH mm and work out the wheel circumference from what the encoder saw"
    cmd_RESET_help = "Zero the encoder's travel counters"

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split()[-1]
        self.extruder_name = config.get('extruder', 'extruder')
        self.circumference = config.getfloat('wheel_circumference', above=0.)
        self.detection_length = config.getfloat('detection_length', 7., above=0.)
        self.min_ratio = config.getfloat('min_travel_ratio', 0.25, minval=0., maxval=1.)
        self.invert = config.getboolean('invert', False)
        report_time = config.getfloat('report_time', 0.1, minval=0.02, maxval=1.)
        ppins = self.printer.lookup_object('pins')
        self.mcu_adc = ppins.setup_pin('adc', config.get('adc_pin'))
        # No range check: every value in 0..100 % is a legitimate angle.
        self.mcu_adc.setup_adc_sample(report_time, SAMPLE_TIME, SAMPLE_COUNT,
                                      minval=0., maxval=1., range_check_count=0)
        self.mcu_adc.setup_adc_callback(self._adc_callback)
        self.runout_helper = filament_switch_sensor.RunoutHelper(config)
        # State
        self.last_turns = None
        self.angle = 0.
        self.measured = 0.            # mm since the last reset (job start, RESET or CALIBRATE)
        self.commanded_start = None   # extruder position at the last reset
        self.window_pos = None        # extruder position where the current window started
        self.window_measured = 0.
        self.last_window = (0., 0.)   # (commanded, measured) of the last completed window
        self.extruder = None
        self.estimated_print_time = None
        self.printing = False
        self.check_timer = None
        self.printer.register_event_handler('klippy:connect', self._handle_connect)
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('idle_timeout:printing', self._handle_printing)
        self.printer.register_event_handler('idle_timeout:ready', self._handle_not_printing)
        self.printer.register_event_handler('idle_timeout:idle', self._handle_not_printing)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command('FILAMENT_ENCODER_CALIBRATE', 'SENSOR', self.name,
                                   self.cmd_CALIBRATE, desc=self.cmd_CALIBRATE_help)
        gcode.register_mux_command('FILAMENT_ENCODER_RESET', 'SENSOR', self.name,
                                   self.cmd_RESET, desc=self.cmd_RESET_help)

    # ---- Klipper events
    def _handle_connect(self):
        # A circumference saved by FILAMENT_ENCODER_CALIBRATE SAVE=1 wins over the config's value.
        sv = self.printer.lookup_object('save_variables', None)
        if sv is None:
            return
        try:
            saved = float(sv.allVariables.get(SAVED_VAR % self.name, 0.))
        except (TypeError, ValueError):
            saved = 0.
        if saved > 0.:
            self.circumference = saved
            logging.info("filament_angle_sensor %s: wheel_circumference %.4f from variables",
                         self.name, saved)

    def _handle_ready(self):
        self.extruder = self.printer.lookup_object(self.extruder_name)
        self.estimated_print_time = self.printer.lookup_object('mcu').estimated_print_time
        self.check_timer = self.reactor.register_timer(self._check_event)

    def _handle_printing(self, print_time):
        self.printing = True
        self._reset()
        self.reactor.update_timer(self.check_timer, self.reactor.NOW)

    def _handle_not_printing(self, print_time):
        self.printing = False
        self.reactor.update_timer(self.check_timer, self.reactor.NEVER)

    # ---- the measurement
    def _adc_callback(self, read_time, read_value):
        turns = 1. - read_value if self.invert else read_value
        if self.last_turns is not None:
            d = turns - self.last_turns
            if d > 0.5:
                d -= 1.
            elif d < -0.5:
                d += 1.
            self.measured += d * self.circumference
        self.last_turns = turns
        self.angle = turns * 360.

    def _extruder_pos(self, eventtime):
        if self.extruder is None:
            return 0.
        return self.extruder.find_past_position(self.estimated_print_time(eventtime))

    def _reset(self, eventtime=None):
        if eventtime is None:
            eventtime = self.reactor.monotonic()
        pos = self._extruder_pos(eventtime)
        self.measured = 0.
        self.commanded_start = pos
        self.window_pos = pos
        self.window_measured = 0.
        self.last_window = (0., 0.)

    def _check_event(self, eventtime):
        pos = self._extruder_pos(eventtime)
        if self.window_pos is None:
            self.window_pos, self.window_measured = pos, self.measured
        commanded = pos - self.window_pos
        if commanded < 0.:
            # A retract took the extruder behind the window's start: the window starts again here, so a
            # retract and its unretract never count as a jam.
            self.window_pos, self.window_measured = pos, self.measured
        elif commanded >= self.detection_length:
            moved = self.measured - self.window_measured
            self.last_window = (commanded, moved)
            self.runout_helper.note_filament_present(eventtime, moved >= self.min_ratio * commanded)
            self.window_pos, self.window_measured = pos, self.measured
        return eventtime + CHECK_TIME

    # ---- status and commands
    def get_status(self, eventtime):
        st = dict(self.runout_helper.get_status(eventtime))
        commanded = 0.
        if self.commanded_start is not None:
            commanded = self._extruder_pos(eventtime) - self.commanded_start
        c, m = self.last_window
        slip = 0. if c <= 0. else max(0., min(100., 100. * (1. - m / c)))
        st.update({'angle': round(self.angle, 1), 'measured_mm': round(self.measured, 2),
                   'commanded_mm': round(commanded, 2), 'slip_pct': round(slip, 1),
                   'wheel_circumference': round(self.circumference, 4), 'printing': self.printing})
        return st

    def cmd_RESET(self, gcmd):
        self._reset()
        gcmd.respond_info("Filament encoder %s: counters zeroed" % (self.name,))

    def cmd_CALIBRATE(self, gcmd):
        length = gcmd.get_float('LENGTH', 100., above=0.)
        speed = gcmd.get_float('SPEED', 5., above=0.)       # mm/s
        save = gcmd.get_int('SAVE', 0)
        toolhead = self.printer.lookup_object('toolhead')
        gcode = self.printer.lookup_object('gcode')
        toolhead.wait_moves()
        self._reset()
        # Through the normal G1, so the hotend must be at temperature (Klipper refuses a cold extrude).
        gcode.run_script_from_command(
            "SAVE_GCODE_STATE NAME=_filament_encoder_cal\nM83\nG1 E%.3f F%.1f\n"
            "RESTORE_GCODE_STATE NAME=_filament_encoder_cal" % (length, speed * 60.))
        toolhead.wait_moves()
        self.reactor.pause(self.reactor.monotonic() + 0.5)   # the last samples
        moved = self.measured
        if moved <= 0.1 * length:
            raise gcmd.error("Filament encoder %s saw %.1f mm for %.0f mm commanded. Is the wheel turning "
                             "with the filament, and the magnet 0.5-3 mm from the chip?" % (self.name, moved, length))
        new = self.circumference * length / moved
        gcmd.respond_info("Filament encoder %s: %.0f mm commanded, %.1f mm seen with circumference %.4f. "
                          "Circumference that matches: %.4f%s" % (
                              self.name, length, moved, self.circumference, new,
                              " (saved)" if save else ". Repeat with SAVE=1 to keep it."))
        if save:
            gcode.run_script_from_command("SAVE_VARIABLE VARIABLE=%s VALUE=%.4f" % (SAVED_VAR % self.name, new))
            self.circumference = new
            self._reset()


def load_config_prefix(config):
    return FilamentAngleSensor(config)
