# Spindle RPM from a pulse input, on Klipper's own pulse counter.
#
# Part of the Rhino Tool Manager (github.com/Makersmic/Toolhead_Manager); install.sh links it into
# klippy/extras/. Wiring and design: docs/proposal-filament-encoder.md (stage 2),
# docs/spindle-tachometer-wiring.pdf.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from . import pulse_counter


class SpindleTachometer:
    """[spindle_tachometer name]: pin, pulses_per_rev, poll_interval, sample_time.

    Klipper's counter polls the pin every poll_interval and counts both edges, so poll_interval must be
    well under half a pulse period (a 14-pole outrunner read by one hall switch gives 7 pulses per turn:
    2.8 kHz at 24,000 RPM, so 0.0001 s). rpm = edges per second x 30 / pulses_per_rev, as the fan
    tachometer does it. Status only: nothing here can act on the spindle.
    """
    def __init__(self, config):
        printer = config.get_printer()
        pin = config.get('pin')
        self.ppr = config.getint('pulses_per_rev', 1, minval=1)
        poll = config.getfloat('poll_interval', 0.0001, above=0., maxval=0.01)
        sample = config.getfloat('sample_time', 0.5, above=0., maxval=5.)
        self.counter = pulse_counter.FrequencyCounter(printer, pin, sample, poll)

    def get_status(self, eventtime):
        edges = self.counter.get_frequency()
        return {'rpm': round(edges * 30. / self.ppr), 'edges_per_second': round(edges, 1),
                'pulses_per_rev': self.ppr}


def load_config_prefix(config):
    return SpindleTachometer(config)
