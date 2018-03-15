# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging

from dgt.iface import DgtDisplayIface
from dgt.util import ClockSide
from dgt.board import DgtBoard

from dgt.api import Message
from utilities import MsgDisplay


class DgtCn(DgtDisplayIface):

    """Handle the DgtXL/3000 communication."""

    def __init__(self, dgtboard: DgtBoard):
        super(DgtCn, self).__init__(dgtboard)
        MsgDisplay.show(Message.DGT_CLOCK_VERSION(main=2, sub=2, dev='i2c', text=None))

    def display_text_on_clock(self, message):
        """Display a text on the dgtxl/3k/rev2."""
        print('text ', message.l)
        return True

    def display_move_on_clock(self, message):
        """Display a move on the dgtxl/3k/rev2."""
        print('move ', message.move)
        return True

    def display_time_on_clock(self, message):
        """Display the time on the dgtxl/3k/rev2."""
        if self.get_name() not in message.devs:
            logging.debug('ignored endText - devs: %s', message.devs)
            return True
        print('time ', message.devs)
        return True

    def light_squares_on_revelation(self, uci_move: str):
        """Light the Rev2 leds."""
        return True

    def clear_light_on_revelation(self):
        """Clear the Rev2 leds."""
        return True

    def _resume_clock(self, side):
        print('rsume')
        return True

    def stop_clock(self, devs: set):
        """Stop the dgtxl/3k."""
        print('stop ', devs)
        return True

    def start_clock(self, side: ClockSide, devs: set):
        """Start the dgtxl/3k."""
        print('start', devs)
        return True

    def set_clock(self, time_left: int, time_right: int, devs: set):
        print('set  ', devs)
        return True

    def get_name(self):
        """Get name."""
        return 'i2c'
