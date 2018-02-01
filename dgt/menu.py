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

import os
import logging
from configobj import ConfigObj
from collections import OrderedDict

import chess
from timecontrol import TimeControl
from utilities import EvtObserver, DgtObserver, get_tags, version, write_picochess_ini
from dgt.util import TimeMode, TimeModeLoop, MainTop, MainTopLoop, Mode, ModeLoop, Language, LanguageLoop
from dgt.util import BeepLevel, BeepLoop, System, SystemLoop, Display, DisplayLoop, ClockIcons, Voice, VoiceLoop
from dgt.util import Info, InfoLoop, UpdtTop, UpdtTopLoop
from dgt.api import Dgt, Event
from dgt.translate import DgtTranslate


class MainMenuState(object):

    """Keep the current DgtMainMenu State."""

    TOP = 100000

    MODE = 200000
    MODE_TYPE = 210000  # normal, observe, ...

    POS = 300000
    POS_COL = 310000
    POS_REV = 311000
    POS_UCI = 311100
    POS_READ = 311110

    TIME = 400000
    TIME_BLITZ = 410000  # blitz, fischer, fixed
    TIME_BLITZ_CTRL = 411000  # time_control objs
    TIME_FISCH = 420000
    TIME_FISCH_CTRL = 421000
    TIME_FIXED = 430000
    TIME_FIXED_CTRL = 431000

    BOOK = 500000
    BOOK_NAME = 510000

    ENG = 600000
    ENG_NAME = 610000
    ENG_NAME_LEVEL = 611000

    SYS = 700000
    SYS_INFO = 710000
    SYS_INFO_VERS = 711000
    SYS_INFO_IP = 712000
    SYS_INFO_BATTERY = 713000
    SYS_SOUND = 720000
    SYS_SOUND_BEEP = 721000  # never, always, some
    SYS_LANG = 730000
    SYS_LANG_NAME = 731000  # de, en, ...
    SYS_VOICE = 750000
    SYS_VOICE_USER = 751000  # user
    SYS_VOICE_USER_MUTE = 751100  # on, off
    SYS_VOICE_USER_MUTE_LANG = 751110  # de, en, ...
    SYS_VOICE_USER_MUTE_LANG_SPEAK = 751111  # al, christina, ...
    SYS_VOICE_COMP = 752000  # computer
    SYS_VOICE_COMP_MUTE = 752100  # on, off
    SYS_VOICE_COMP_MUTE_LANG = 752110  # de, en, ...
    SYS_VOICE_COMP_MUTE_LANG_SPEAK = 752111  # al, christina, ...
    SYS_VOICE_SPEED = 753000  # vspeed
    SYS_VOICE_SPEED_FACTOR = 753100  # 0-7
    SYS_DISP = 760000
    SYS_DISP_CONFIRM = 761000
    SYS_DISP_CONFIRM_YESNO = 761100  # yes,no
    SYS_DISP_PONDER = 762000
    SYS_DISP_PONDER_INTERVAL = 762100  # 1-8
    SYS_DISP_CAPITAL = 763000
    SYS_DISP_CAPTIAL_YESNO = 763100  # yes, no
    SYS_DISP_NOTATION = 764000
    SYS_DISP_NOTATION_MOVE = 764100  # short, long


class UpdtMenuState(object):

    """Keep the current DgtUpdtMenu State."""

    TOP = 100000

    UPDATE = 200000
    UPDATE_RELEASE = 210000  # release names

    LOG = 300000


class DgtMenu(object):

    """Handle the Dgt Menu."""

    def __init__(self, disable_confirm: bool, ponder_interval: int,
                 user_voice: str, comp_voice: str, speed_voice: int, enable_capital_letters: bool,
                 disable_short_move: bool, log_file, engine_server, dgttranslate: DgtTranslate):
        super(DgtMenu, self).__init__()

        self.current_text = None  # save the current text
        self.mainmenu_system_display_confirm = disable_confirm
        self.mainmenu_system_display_ponderinterval = ponder_interval
        self.mainmenu_system_display_capital = enable_capital_letters
        self.mainmenu_system_display_notation = disable_short_move  # True = disable short move display => long display
        self.log_file = log_file
        self.remote_engine = bool(engine_server)
        self.dgttranslate = dgttranslate
        self.mainmenu_state = MainMenuState.TOP

        self.dgt_fen = '8/8/8/8/8/8/8/8'
        self.int_ip = None
        self.ext_ip = None
        self.flip_board = False

        self.mainmenu_position_whitetomove = True
        self.mainmenu_position_reverse = False
        self.mainmenu_position_uci960 = False

        self.mainmenu_top = MainTop.MODE
        self.mainmenu_mode = Mode.NORMAL

        self.mainmenu_engine_level = None
        self.engine_has_960 = False
        self.engine_has_ponder = False
        self.engine_restart = False
        self.mainmenu_engine_name = 0
        self.installed_engines = []

        self.mainmenu_book = 0
        self.all_books = []

        self.mainmenu_system = System.INFO
        self.mainmenu_system_sound = self.dgttranslate.beep

        langs = {'en': Language.EN, 'de': Language.DE, 'nl': Language.NL,
                 'fr': Language.FR, 'es': Language.ES, 'it': Language.IT}
        self.mainmenu_system_language = langs[self.dgttranslate.language]

        self.voices_conf = ConfigObj('talker' + os.sep + 'voices' + os.sep + 'voices.ini')
        self.mainmenu_system_voice = Voice.COMP
        self.mainmenu_system_voice_user_active = bool(user_voice)
        self.mainmenu_system_voice_comp_active = bool(comp_voice)
        try:
            (user_language_name, user_speaker_name) = user_voice.split(':')
            self.mainmenu_system_voice_user_lang = self.voices_conf.keys().index(user_language_name)
            self.mainmenu_system_voice_user_speak = self.voices_conf[user_language_name].keys().index(user_speaker_name)
        except (AttributeError, ValueError):  # None = "not set" throws an AttributeError
            self.mainmenu_system_voice_user_lang = 0
            self.mainmenu_system_voice_user_speak = 0
        try:
            (comp_language_name, comp_speaker_name) = comp_voice.split(':')
            self.mainmenu_system_voice_comp_lang = self.voices_conf.keys().index(comp_language_name)
            self.mainmenu_system_voice_comp_speak = self.voices_conf[comp_language_name].keys().index(comp_speaker_name)
        except (AttributeError, ValueError):  # None = "not set" throws an AttributeError
            self.mainmenu_system_voice_comp_lang = 0
            self.mainmenu_system_voice_comp_speak = 0

        self.mainmenu_system_voice_speedfactor = speed_voice

        self.mainmenu_system_display = Display.PONDER
        self.mainmenu_system_info = Info.VERSION

        self.mainmenu_time_mode = TimeMode.BLITZ

        self.mainmenu_time_fixed = 0
        self.mainmenu_time_blitz = 2  # Default time control: Blitz, 5min
        self.mainmenu_time_fisch = 0
        self.tc_fixed_list = [' 1', ' 3', ' 5', '10', '15', '30', '60', '90']
        self.tc_blitz_list = [' 1', ' 3', ' 5', '10', '15', '30', '60', '90']
        self.tc_fisch_list = [' 1  1', ' 3  2', ' 5  3', '10  5', '15 10', '30 15', '60 20', '90 30']
        self.tc_fixed_map = OrderedDict([
            ('rnbqkbnr/pppppppp/Q7/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=1)),
            ('rnbqkbnr/pppppppp/1Q6/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=3)),
            ('rnbqkbnr/pppppppp/2Q5/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=5)),
            ('rnbqkbnr/pppppppp/3Q4/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=10)),
            ('rnbqkbnr/pppppppp/4Q3/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=15)),
            ('rnbqkbnr/pppppppp/5Q2/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=30)),
            ('rnbqkbnr/pppppppp/6Q1/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=60)),
            ('rnbqkbnr/pppppppp/7Q/8/8/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FIXED, fixed=90))])
        self.tc_blitz_map = OrderedDict([
            ('rnbqkbnr/pppppppp/8/8/Q7/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=1)),
            ('rnbqkbnr/pppppppp/8/8/1Q6/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=3)),
            ('rnbqkbnr/pppppppp/8/8/2Q5/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=5)),
            ('rnbqkbnr/pppppppp/8/8/3Q4/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=10)),
            ('rnbqkbnr/pppppppp/8/8/4Q3/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=15)),
            ('rnbqkbnr/pppppppp/8/8/5Q2/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=30)),
            ('rnbqkbnr/pppppppp/8/8/6Q1/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=60)),
            ('rnbqkbnr/pppppppp/8/8/7Q/8/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.BLITZ, blitz=90))])
        self.tc_fisch_map = OrderedDict([
            ('rnbqkbnr/pppppppp/8/8/8/Q7/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=1, fischer=1)),
            ('rnbqkbnr/pppppppp/8/8/8/1Q6/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=3, fischer=2)),
            ('rnbqkbnr/pppppppp/8/8/8/2Q5/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=5, fischer=3)),
            ('rnbqkbnr/pppppppp/8/8/8/3Q4/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=10, fischer=5)),
            ('rnbqkbnr/pppppppp/8/8/8/4Q3/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=15, fischer=10)),
            ('rnbqkbnr/pppppppp/8/8/8/5Q2/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=30, fischer=15)),
            ('rnbqkbnr/pppppppp/8/8/8/6Q1/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=60, fischer=20)),
            ('rnbqkbnr/pppppppp/8/8/8/7Q/PPPPPPPP/RNBQKBNR', TimeControl(TimeMode.FISCHER, blitz=90, fischer=30))])
        # setup the result vars for api (dgtdisplay)
        self.save_choices()
        # During "picochess" is displayed, some special actions allowed
        self.picochess_displayed = set()
        self.updtmenu_state = UpdtMenuState.TOP
        self.updtmenu_top = UpdtTop.UPDATE
        self.updtmenu_devs = set()  # list of devices which are inside the update-menu
        self.updtmenu_tags = []
        self.updtmenu_version = 0  # index to current version

        self.battery = '-NA'  # standard value: NotAvailable (discharging)
        self.inside_room = False

    def inside_main_menu(self):
        """Check if currently inside the MainMenu."""
        return self.mainmenu_state != MainMenuState.TOP

    def inside_updt_menu(self):
        """Check if currently inside the UpdtMenu."""
        return self.updtmenu_state != UpdtMenuState.TOP

    def disable_picochess_displayed(self, dev):
        """Disable picochess display."""
        self.picochess_displayed.discard(dev)

    def enable_picochess_displayed(self, dev):
        """Enable picochess display."""
        self.picochess_displayed.add(dev)
        self.updtmenu_tags = get_tags()
        try:
            self.updtmenu_version = [item[1] for item in self.updtmenu_tags].index(version)
        except ValueError:
            self.updtmenu_version = 0  # set index to newest release

    def inside_picochess_time(self, dev):
        """Picochess displayed on clock."""
        return dev in self.picochess_displayed

    def save_choices(self):
        """Save the user choices to the result vars."""
        self.mainmenu_state = MainMenuState.TOP
        self.updtmenu_state = UpdtMenuState.TOP

        self.res_mode = self.mainmenu_mode

        self.res_position_whitetomove = self.mainmenu_position_whitetomove
        self.res_position_reverse = self.mainmenu_position_reverse
        self.res_position_uci960 = self.mainmenu_position_uci960

        self.res_time_mode = self.mainmenu_time_mode
        self.res_time_fixed = self.mainmenu_time_fixed
        self.res_time_blitz = self.mainmenu_time_blitz
        self.res_time_fisch = self.mainmenu_time_fisch

        self.res_book_name = self.mainmenu_book

        self.res_engine_name = self.mainmenu_engine_name
        self.res_engine_level = self.mainmenu_engine_level

        self.res_system_display_confirm = self.mainmenu_system_display_confirm
        self.res_system_display_ponderinterval = self.mainmenu_system_display_ponderinterval
        self.dgttranslate.set_capital(self.mainmenu_system_display_capital)
        self.dgttranslate.set_notation(self.mainmenu_system_display_notation)
        return False

    def set_engine_restart(self, flag: bool):
        """Set the flag."""
        self.engine_restart = flag

    def get_engine_restart(self):
        """Get the flag."""
        return self.engine_restart

    def get_flip_board(self):
        """Get the flag."""
        return self.flip_board

    def get_engine_has_960(self):
        """Get the flag."""
        return self.engine_has_960

    def set_engine_has_960(self, flag: bool):
        """Set the flag."""
        self.engine_has_960 = flag

    def get_engine_has_ponder(self):
        """Get the flag."""
        return self.engine_has_ponder

    def set_engine_has_ponder(self, flag: bool):
        """Set the flag."""
        self.engine_has_ponder = flag

    def get_dgt_fen(self):
        """Get the flag."""
        return self.dgt_fen

    def set_dgt_fen(self, fen: str):
        """Set the flag."""
        self.dgt_fen = fen

    def get_mode(self):
        """Get the flag."""
        return self.res_mode

    def set_mode(self, mode: Mode):
        """Set the flag."""
        self.res_mode = self.mainmenu_mode = mode

    def get_engine(self):
        """Get the flag."""
        return self.installed_engines[self.res_engine_name]

    def set_engine_index(self, index: int):
        """Set the flag."""
        self.res_engine_name = self.mainmenu_engine_name = index

    def get_engine_level(self):
        """Get the flag."""
        return self.res_engine_level

    def set_engine_level(self, level: int):
        """Set the flag."""
        self.res_engine_level = self.mainmenu_engine_level = level

    def get_confirm(self):
        """Get the flag."""
        return self.res_system_display_confirm

    def set_book(self, index: int):
        """Set the flag."""
        self.res_book_name = self.mainmenu_book = index

    def set_time_mode(self, mode: TimeMode):
        """Set the flag."""
        self.res_time_mode = self.mainmenu_time_mode = mode

    def get_time_mode(self):
        """Get the flag."""
        return self.res_time_mode

    def set_time_fixed(self, index: int):
        """Set the flag."""
        self.res_time_fixed = self.mainmenu_time_fixed = index

    def get_time_fixed(self):
        """Get the flag."""
        return self.res_time_fixed

    def set_time_blitz(self, index: int):
        """Set the flag."""
        self.res_time_blitz = self.mainmenu_time_blitz = index

    def get_time_blitz(self):
        """Get the flag."""
        return self.res_time_blitz

    def set_time_fisch(self, index: int):
        """Set the flag."""
        self.res_time_fisch = self.mainmenu_time_fisch = index

    def get_time_fisch(self):
        """Get the flag."""
        return self.res_time_fisch

    def set_position_reverse_flipboard(self, flip_board):
        """Set the flag."""
        self.res_position_reverse = self.flip_board = flip_board

    def get_ponderinterval(self):
        """Get the flag."""
        return self.res_system_display_ponderinterval

    def get(self):
        """Get the current state."""
        return self.mainmenu_state

    def enter_updtmenu_top(self):
        """Set the menu state."""
        self.updtmenu_state = UpdtMenuState.TOP
        self.current_text = None
        return False

    def enter_updtmenu_update(self):
        """Set the menu state."""
        self.updtmenu_state = UpdtMenuState.UPDATE
        text = self.dgttranslate.text(UpdtTop.UPDATE.value)
        return text

    def enter_updtmenu_update_release(self):
        self.updtmenu_state = UpdtMenuState.UPDATE_RELEASE
        text = self.dgttranslate.text('B00_updt_version', self.updtmenu_tags[self.updtmenu_version][1],
                                      devs=self.updtmenu_devs)
        text.rd = ClockIcons.DOT
        return text

    def enter_updtmenu_log(self):
        """Set the menu state."""
        self.updtmenu_state = UpdtMenuState.LOG
        text = self.dgttranslate.text(UpdtTop.LOG.value)
        return text

    def enter_mainmenu_top(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TOP
        self.current_text = None
        return False

    def enter_mainmenu_mode(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.MODE
        text = self.dgttranslate.text(MainTop.MODE.value)
        return text

    def enter_mainmenu_mode_type(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.MODE_TYPE
        text = self.dgttranslate.text(self.mainmenu_mode.value)
        return text

    def enter_mainmenu_pos(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.POS
        text = self.dgttranslate.text(MainTop.POSITION.value)
        return text

    def enter_mainmenu_pos_color(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.POS_COL
        text = self.dgttranslate.text('B00_sidewhite' if self.mainmenu_position_whitetomove else 'B00_sideblack')
        return text

    def enter_mainmenu_pos_rev(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.POS_REV
        text = self.dgttranslate.text('B00_bw' if self.mainmenu_position_reverse else 'B00_wb')
        return text

    def enter_mainmenu_pos_uci(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.POS_UCI
        text = self.dgttranslate.text('B00_960yes' if self.mainmenu_position_uci960 else 'B00_960no')
        return text

    def enter_mainmenu_pos_read(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.POS_READ
        text = self.dgttranslate.text('B00_scanboard')
        return text

    def enter_mainmenu_time(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME
        text = self.dgttranslate.text(MainTop.TIME.value)
        return text

    def enter_mainmenu_time_blitz(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_BLITZ
        text = self.dgttranslate.text(self.mainmenu_time_mode.value)
        return text

    def enter_mainmenu_time_blitz_ctrl(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_BLITZ_CTRL
        text = self.dgttranslate.text('B00_tc_blitz', self.tc_blitz_list[self.mainmenu_time_blitz])
        return text

    def enter_mainmenu_time_fisch(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_FISCH
        text = self.dgttranslate.text(self.mainmenu_time_mode.value)
        return text

    def enter_mainmenu_time_fisch_ctrl(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_FISCH_CTRL
        text = self.dgttranslate.text('B00_tc_fisch', self.tc_fisch_list[self.mainmenu_time_fisch])
        return text

    def enter_mainmenu_time_fixed(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_FIXED
        text = self.dgttranslate.text(self.mainmenu_time_mode.value)
        return text

    def enter_mainmenu_time_fixed_ctrl(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.TIME_FIXED_CTRL
        text = self.dgttranslate.text('B00_tc_fixed', self.tc_fixed_list[self.mainmenu_time_fixed])
        return text

    def enter_mainmenu_book(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.BOOK
        text = self.dgttranslate.text(MainTop.BOOK.value)
        return text

    def _get_current_book_name(self):
        text = self.all_books[self.mainmenu_book]['text']
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def enter_mainmenu_book_name(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.BOOK_NAME
        return self._get_current_book_name()

    def enter_mainmenu_eng(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.ENG
        text = self.dgttranslate.text(MainTop.ENGINE.value)
        return text

    def _get_current_engine_name(self):
        text = self.installed_engines[self.mainmenu_engine_name]['text']
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def enter_mainmenu_eng_name(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.ENG_NAME
        return self._get_current_engine_name()

    def enter_mainmenu_eng_name_level(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.ENG_NAME_LEVEL
        eng = self.installed_engines[self.mainmenu_engine_name]
        level_dict = eng['level_dict']
        if level_dict:
            if self.mainmenu_engine_level is None or len(level_dict) <= self.mainmenu_engine_level:
                self.mainmenu_engine_level = len(level_dict) - 1
            msg = sorted(level_dict)[self.mainmenu_engine_level]
            text = self.dgttranslate.text('B00_level', msg)
        else:
            text = self.save_choices()
        return text

    def enter_mainmenu_sys(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS
        text = self.dgttranslate.text(MainTop.SYSTEM.value)
        return text

    def enter_mainmenu_sys_info(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_INFO
        text = self.dgttranslate.text(self.mainmenu_system.value)
        return text

    def enter_mainmenu_sys_info_vers(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_INFO_VERS
        text = self.dgttranslate.text(self.mainmenu_system_info.value)
        return text

    def enter_mainmenu_sys_info_ip(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_INFO_IP
        text = self.dgttranslate.text(self.mainmenu_system_info.value)
        return text

    def enter_mainmenu_sys_info_battery(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_INFO_BATTERY
        text = self.dgttranslate.text(self.mainmenu_system_info.value)
        return text

    def enter_mainmenu_sys_sound(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_SOUND
        text = self.dgttranslate.text(self.mainmenu_system.value)
        return text

    def enter_mainmenu_sys_sound_beep(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_SOUND_BEEP
        text = self.dgttranslate.text(self.mainmenu_system_sound.value)
        return text

    def enter_mainmenu_sys_lang(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_LANG
        text = self.dgttranslate.text(self.mainmenu_system.value)
        return text

    def enter_mainmenu_sys_lang_name(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_LANG_NAME
        text = self.dgttranslate.text(self.mainmenu_system_language.value)
        return text

    def enter_mainmenu_sys_voice(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE
        text = self.dgttranslate.text(self.mainmenu_system.value)
        return text

    def enter_mainmenu_sys_voice_user(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_USER
        text = self.dgttranslate.text(Voice.USER.value)
        return text

    def enter_mainmenu_sys_voice_user_mute(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_USER_MUTE
        msg = 'on' if self.mainmenu_system_voice_user_active else 'off'
        text = self.dgttranslate.text('B00_voice_' + msg)
        return text

    def enter_mainmenu_sys_voice_user_mute_lang(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_USER_MUTE_LANG
        vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
        text = self.dgttranslate.text('B00_language_' + vkey + '_menu')
        return text

    def enter_mainmenu_sys_voice_comp(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_COMP
        text = self.dgttranslate.text(Voice.COMP.value)
        return text

    def enter_mainmenu_sys_voice_comp_mute(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_COMP_MUTE
        msg = 'on' if self.mainmenu_system_voice_comp_active else 'off'
        text = self.dgttranslate.text('B00_voice_' + msg)
        return text

    def enter_mainmenu_sys_voice_comp_mute_lang(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_COMP_MUTE_LANG
        vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
        text = self.dgttranslate.text('B00_language_' + vkey + '_menu')
        return text

    def _get_current_speaker(self, speakers, index:int):
        speaker = speakers[list(speakers)[index]]
        text = Dgt.DISPLAY_TEXT(l=speaker['large'], m=speaker['medium'], s=speaker['small'])
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        text.wait = False
        text.maxtime = 0
        text.devs = {'ser', 'i2c', 'web'}
        return text

    def enter_mainmenu_sys_voice_user_mute_lang_speak(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK
        vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
        self.mainmenu_system_voice_user_speak %= len(self.voices_conf[vkey])  # in case: change higher=>lower speakerNo
        return self._get_current_speaker(self.voices_conf[vkey], self.mainmenu_system_voice_user_speak)

    def enter_mainmenu_sys_voice_comp_mute_lang_speak(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK
        vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
        self.mainmenu_system_voice_comp_speak %= len(self.voices_conf[vkey])  # in case: change higher=>lower speakerNo
        return self._get_current_speaker(self.voices_conf[vkey], self.mainmenu_system_voice_comp_speak)

    def enter_mainmenu_sys_voice_speed(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_SPEED
        text = self.dgttranslate.text(Voice.SPEED.value)
        return text

    def enter_mainmenu_sys_voice_speed_factor(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_VOICE_SPEED_FACTOR
        text = self.dgttranslate.text('B00_voice_speed', str(self.mainmenu_system_voice_speedfactor))
        return text

    def enter_mainmenu_sys_disp(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP
        text = self.dgttranslate.text(self.mainmenu_system.value)
        return text

    def enter_mainmenu_sys_disp_confirm(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_CONFIRM
        text = self.dgttranslate.text(Display.CONFIRM.value)
        return text

    def enter_mainmenu_sys_disp_confirm_yesno(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_CONFIRM_YESNO
        msg = 'off' if self.mainmenu_system_display_confirm else 'on'
        text = self.dgttranslate.text('B00_confirm_' + msg)
        return text

    def enter_mainmenu_sys_disp_ponder(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_PONDER
        text = self.dgttranslate.text(Display.PONDER.value)
        return text

    def enter_mainmenu_sys_disp_ponder_interval(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_PONDER_INTERVAL
        text = self.dgttranslate.text('B00_ponder_interval', str(self.mainmenu_system_display_ponderinterval))
        return text

    def enter_mainmenu_sys_disp_capital(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_CAPITAL
        text = self.dgttranslate.text(Display.CAPITAL.value)
        return text

    def enter_mainmenu_sys_disp_capital_yesno(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_CAPTIAL_YESNO
        msg = 'on' if self.mainmenu_system_display_capital else 'off'
        text = self.dgttranslate.text('B00_capital_' + msg)
        return text

    def enter_mainmenu_sys_disp_notation(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_NOTATION
        text = self.dgttranslate.text(Display.NOTATION.value)
        return text

    def enter_mainmenu_sys_disp_notation_move(self):
        """Set the menu state."""
        self.mainmenu_state = MainMenuState.SYS_DISP_NOTATION_MOVE
        msg = 'long' if self.mainmenu_system_display_notation else 'short'
        text = self.dgttranslate.text('B00_notation_' + msg)
        return text

    def _fire_event(self, event: Event):
        EvtObserver.fire(event)
        return self.save_choices()

    def _fire_dispatchdgt(self, text):
        DgtObserver.fire(text)
        return self.save_choices()

    def _fire_timectrl(self, timectrl: TimeControl):
        time_text = self.dgttranslate.text('B10_oktime')
        event = Event.TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=time_text, show_ok=True)
        return self._fire_event(event)

    def exit_menu(self):
        """Exit the menu."""
        if self.inside_main_menu():
            self.enter_mainmenu_top()
            if not self.get_confirm():
                return True
        return False

    def main_up(self):
        """Change the menu state after UP action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.mainmenu_state == MainMenuState.TOP:
            pass
        elif self.mainmenu_state == MainMenuState.MODE:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.MODE_TYPE:
            text = self.enter_mainmenu_mode()

        elif self.mainmenu_state == MainMenuState.POS:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.POS_COL:
            text = self.enter_mainmenu_pos()

        elif self.mainmenu_state == MainMenuState.POS_REV:
            text = self.enter_mainmenu_pos_color()

        elif self.mainmenu_state == MainMenuState.POS_UCI:
            text = self.enter_mainmenu_pos_rev()

        elif self.mainmenu_state == MainMenuState.POS_READ:
            text = self.enter_mainmenu_pos_uci()

        elif self.mainmenu_state == MainMenuState.TIME:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ:
            text = self.enter_mainmenu_time()

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ_CTRL:
            text = self.enter_mainmenu_time_blitz()

        elif self.mainmenu_state == MainMenuState.TIME_FISCH:
            text = self.enter_mainmenu_time()

        elif self.mainmenu_state == MainMenuState.TIME_FISCH_CTRL:
            text = self.enter_mainmenu_time_fisch()

        elif self.mainmenu_state == MainMenuState.TIME_FIXED:
            text = self.enter_mainmenu_time()

        elif self.mainmenu_state == MainMenuState.TIME_FIXED_CTRL:
            text = self.enter_mainmenu_time_fixed()

        elif self.mainmenu_state == MainMenuState.BOOK:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.BOOK_NAME:
            text = self.enter_mainmenu_book()

        elif self.mainmenu_state == MainMenuState.ENG:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.ENG_NAME:
            text = self.enter_mainmenu_eng()

        elif self.mainmenu_state == MainMenuState.ENG_NAME_LEVEL:
            text = self.enter_mainmenu_eng_name()

        elif self.mainmenu_state == MainMenuState.SYS:
            text = self.enter_mainmenu_top()

        elif self.mainmenu_state == MainMenuState.SYS_INFO:
            text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.SYS_INFO_VERS:
            text = self.enter_mainmenu_sys_info()

        elif self.mainmenu_state == MainMenuState.SYS_INFO_IP:
            text = self.enter_mainmenu_sys_info()

        elif self.mainmenu_state == MainMenuState.SYS_INFO_BATTERY:
            text = self.enter_mainmenu_sys_info()

        elif self.mainmenu_state == MainMenuState.SYS_SOUND:
            text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.SYS_SOUND_BEEP:
            text = self.enter_mainmenu_sys_sound()

        elif self.mainmenu_state == MainMenuState.SYS_LANG:
            text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.SYS_LANG_NAME:
            text = self.enter_mainmenu_sys_lang()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE:
            text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER:
            text = self.enter_mainmenu_sys_voice()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE:
            text = self.enter_mainmenu_sys_voice_user()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG:
            text = self.enter_mainmenu_sys_voice_user_mute()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            text = self.enter_mainmenu_sys_voice_user_mute_lang()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP:
            text = self.enter_mainmenu_sys_voice()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE:
            text = self.enter_mainmenu_sys_voice_comp()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG:
            text = self.enter_mainmenu_sys_voice_comp_mute()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            text = self.enter_mainmenu_sys_voice_comp_mute_lang()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED:
            text = self.enter_mainmenu_sys_voice()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED_FACTOR:
            text = self.enter_mainmenu_sys_voice_speed()

        elif self.mainmenu_state == MainMenuState.SYS_DISP:
            text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM:
            text = self.enter_mainmenu_sys_disp()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM_YESNO:
            text = self.enter_mainmenu_sys_disp_confirm()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER:
            text = self.enter_mainmenu_sys_disp()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER_INTERVAL:
            text = self.enter_mainmenu_sys_disp_ponder()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPITAL:
            text = self.enter_mainmenu_sys_disp()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPTIAL_YESNO:
            text = self.enter_mainmenu_sys_disp_capital()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION:
            text = self.enter_mainmenu_sys_disp()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION_MOVE:
            text = self.enter_mainmenu_sys_disp_notation()

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_down(self):
        """Change the menu state after DOWN action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.mainmenu_state == MainMenuState.TOP:
            if self.mainmenu_top == MainTop.MODE:
                text = self.enter_mainmenu_mode()
            if self.mainmenu_top == MainTop.POSITION:
                text = self.enter_mainmenu_pos()
            if self.mainmenu_top == MainTop.TIME:
                text = self.enter_mainmenu_time()
            if self.mainmenu_top == MainTop.BOOK:
                text = self.enter_mainmenu_book()
            if self.mainmenu_top == MainTop.ENGINE:
                text = self.enter_mainmenu_eng()
            if self.mainmenu_top == MainTop.SYSTEM:
                text = self.enter_mainmenu_sys()

        elif self.mainmenu_state == MainMenuState.MODE:
            text = self.enter_mainmenu_mode_type()

        elif self.mainmenu_state == MainMenuState.MODE_TYPE:
            # maybe do action!
            if self.mainmenu_mode == Mode.REMOTE and not self.inside_room:
                text = self.dgttranslate.text('Y10_errorroom')
            elif self.mainmenu_mode == Mode.BRAIN and not self.get_engine_has_ponder():
                DgtObserver.fire(self.dgttranslate.text('Y10_erroreng'))
                text = Dgt.DISPLAY_TIME(force=True, wait=True, devs={'ser', 'i2c', 'web'})
            else:
                mode_text = self.dgttranslate.text('B10_okmode')
                event = Event.INTERACTION_MODE(mode=self.mainmenu_mode, mode_text=mode_text, show_ok=True)
                text = self._fire_event(event)

        elif self.mainmenu_state == MainMenuState.POS:
            text = self.enter_mainmenu_pos_color()

        elif self.mainmenu_state == MainMenuState.POS_COL:
            text = self.enter_mainmenu_pos_rev()

        elif self.mainmenu_state == MainMenuState.POS_REV:
            text = self.enter_mainmenu_pos_uci()

        elif self.mainmenu_state == MainMenuState.POS_UCI:
            text = self.enter_mainmenu_pos_read()

        elif self.mainmenu_state == MainMenuState.POS_READ:
            # do action!
            fen = self.dgt_fen
            if self.flip_board != self.mainmenu_position_reverse:
                logging.debug('flipping the board - %s infront now', 'B' if self.mainmenu_position_reverse else 'W')
                fen = fen[::-1]
            fen += ' {0} KQkq - 0 1'.format('w' if self.mainmenu_position_whitetomove else 'b')
            # ask python-chess to correct the castling string
            bit_board = chess.Board(fen, self.mainmenu_position_uci960)
            bit_board.set_fen(bit_board.fen())
            if bit_board.is_valid():
                self.flip_board = self.mainmenu_position_reverse
                event = Event.SETUP_POSITION(fen=bit_board.fen(), uci960=self.mainmenu_position_uci960)
                EvtObserver.fire(event)
                # self._reset_moves_and_score() done in "START_NEW_GAME"
                text = self.save_choices()
            else:
                logging.debug('illegal fen %s', fen)
                DgtObserver.fire(self.dgttranslate.text('Y10_illegalpos'))
                text = self.dgttranslate.text('B00_scanboard')
                text.wait = True

        elif self.mainmenu_state == MainMenuState.TIME:
            if self.mainmenu_time_mode == TimeMode.BLITZ:
                text = self.enter_mainmenu_time_blitz()
            if self.mainmenu_time_mode == TimeMode.FISCHER:
                text = self.enter_mainmenu_time_fisch()
            if self.mainmenu_time_mode == TimeMode.FIXED:
                text = self.enter_mainmenu_time_fixed()

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ:
            text = self.enter_mainmenu_time_blitz_ctrl()

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ_CTRL:
            # do action!
            text = self._fire_timectrl(self.tc_blitz_map[list(self.tc_blitz_map)[self.mainmenu_time_blitz]])

        elif self.mainmenu_state == MainMenuState.TIME_FISCH:
            text = self.enter_mainmenu_time_fisch_ctrl()

        elif self.mainmenu_state == MainMenuState.TIME_FISCH_CTRL:
            # do action!
            text = self._fire_timectrl(self.tc_fisch_map[list(self.tc_fisch_map)[self.mainmenu_time_fisch]])

        elif self.mainmenu_state == MainMenuState.TIME_FIXED:
            text = self.enter_mainmenu_time_fixed_ctrl()

        elif self.mainmenu_state == MainMenuState.TIME_FIXED_CTRL:
            # do action!
            text = self._fire_timectrl(self.tc_fixed_map[list(self.tc_fixed_map)[self.mainmenu_time_fixed]])

        elif self.mainmenu_state == MainMenuState.BOOK:
            text = self.enter_mainmenu_book_name()

        elif self.mainmenu_state == MainMenuState.BOOK_NAME:
            # do action!
            book_text = self.dgttranslate.text('B10_okbook')
            event = Event.NEW_BOOK(book=self.all_books[self.mainmenu_book], book_text=book_text, show_ok=True)
            text = self._fire_event(event)

        elif self.mainmenu_state == MainMenuState.ENG:
            text = self.enter_mainmenu_eng_name()

        elif self.mainmenu_state == MainMenuState.ENG_NAME:
            # maybe do action!
            text = self.enter_mainmenu_eng_name_level()
            if not text:
                if not self.remote_engine:
                    write_picochess_ini('engine-level', None)
                eng = self.installed_engines[self.mainmenu_engine_name]
                eng_text = self.dgttranslate.text('B10_okengine')
                event = Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options={}, show_ok=True)
                EvtObserver.fire(event)
                self.engine_restart = True

        elif self.mainmenu_state == MainMenuState.ENG_NAME_LEVEL:
            # do action!
            eng = self.installed_engines[self.mainmenu_engine_name]
            level_dict = eng['level_dict']
            if level_dict:
                msg = sorted(level_dict)[self.mainmenu_engine_level]
                options = level_dict[msg]
                if not self.remote_engine:
                    write_picochess_ini('engine-level', msg)
                event = Event.NEW_LEVEL(options={}, level_text=self.dgttranslate.text('B10_level', msg), level_name=msg)
                EvtObserver.fire(event)
            else:
                options = {}
            eng_text = self.dgttranslate.text('B10_okengine')
            event = Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options=options, show_ok=True)
            text = self._fire_event(event)
            self.engine_restart = True

        elif self.mainmenu_state == MainMenuState.SYS:
            if self.mainmenu_system == System.INFO:
                text = self.enter_mainmenu_sys_info()
            if self.mainmenu_system == System.SOUND:
                text = self.enter_mainmenu_sys_sound()
            if self.mainmenu_system == System.LANGUAGE:
                text = self.enter_mainmenu_sys_lang()
            if self.mainmenu_system == System.VOICE:
                text = self.enter_mainmenu_sys_voice()
            if self.mainmenu_system == System.DISPLAY:
                text = self.enter_mainmenu_sys_disp()

        elif self.mainmenu_state == MainMenuState.SYS_INFO:
            if self.mainmenu_system_info == Info.VERSION:
                text = self.enter_mainmenu_sys_info_vers()
            if self.mainmenu_system_info == Info.IPADR:
                text = self.enter_mainmenu_sys_info_ip()
            if self.mainmenu_system_info == Info.BATTERY:
                text = self.enter_mainmenu_sys_info_battery()

        elif self.mainmenu_state == MainMenuState.SYS_INFO_VERS:
            # do action!
            text = self.dgttranslate.text('B10_picochess')
            text.rd = ClockIcons.DOT
            text.wait = False
            text = self._fire_dispatchdgt(text)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_IP:
            # do action!
            if self.int_ip:
                msg = ' '.join(self.int_ip.split('.')[:2])
                text = self.dgttranslate.text('B07_default', msg)
                if len(msg) == 7:  # delete the " " for XL incase its "123 456"
                    text.s = msg[:3] + msg[4:]
                DgtObserver.fire(text)
                msg = ' '.join(self.int_ip.split('.')[2:])
                text = self.dgttranslate.text('N07_default', msg)
                if len(msg) == 7:  # delete the " " for XL incase its "123 456"
                    text.s = msg[:3] + msg[4:]
                text.wait = True
            else:
                text = self.dgttranslate.text('B10_noipadr')
            text = self._fire_dispatchdgt(text)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_BATTERY:
            # do action!
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_bat_percent', self.battery))

        elif self.mainmenu_state == MainMenuState.SYS_SOUND:
            text = self.enter_mainmenu_sys_sound_beep()

        elif self.mainmenu_state == MainMenuState.SYS_SOUND_BEEP:
            # do action!
            self.dgttranslate.set_beep(self.mainmenu_system_sound)
            write_picochess_ini('beep-config', self.dgttranslate.beep_to_config(self.mainmenu_system_sound))
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okbeep'))

        elif self.mainmenu_state == MainMenuState.SYS_LANG:
            text = self.enter_mainmenu_sys_lang_name()

        elif self.mainmenu_state == MainMenuState.SYS_LANG_NAME:
            # do action!
            langs = {Language.EN: 'en', Language.DE: 'de', Language.NL: 'nl',
                     Language.FR: 'fr', Language.ES: 'es', Language.IT: 'it'}
            language = langs[self.mainmenu_system_language]
            self.dgttranslate.set_language(language)
            write_picochess_ini('language', language)
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_oklang'))

        elif self.mainmenu_state == MainMenuState.SYS_VOICE:
            if self.mainmenu_system_voice == Voice.USER:
                text = self.enter_mainmenu_sys_voice_user()
            if self.mainmenu_system_voice == Voice.COMP:
                text = self.enter_mainmenu_sys_voice_comp()
            if self.mainmenu_system_voice == Voice.SPEED:
                text = self.enter_mainmenu_sys_voice_speed()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER:
            self.mainmenu_system_voice = Voice.USER
            text = self.enter_mainmenu_sys_voice_user_mute()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP:
            self.mainmenu_system_voice = Voice.COMP
            text = self.enter_mainmenu_sys_voice_comp_mute()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE:
            # maybe do action!
            if self.mainmenu_system_voice_user_active:
                text = self.enter_mainmenu_sys_voice_user_mute_lang()
            else:
                config = ConfigObj('picochess.ini')
                if 'user-voice' in config:
                    del config['user-voice']
                    config.write()
                event = Event.NEW_VOICE(type=self.mainmenu_system_voice, lang='en', speaker='mute', speed=2)
                EvtObserver.fire(event)
                text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okvoice'))

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG:
            text = self.enter_mainmenu_sys_voice_user_mute_lang_speak()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            # do action!
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
            speakers = self.voices_conf[vkey].keys()
            config = ConfigObj('picochess.ini')
            skey = speakers[self.mainmenu_system_voice_user_speak]
            config['user-voice'] = vkey + ':' + skey
            config.write()
            event = Event.NEW_VOICE(type=self.mainmenu_system_voice, lang=vkey, speaker=skey,
                                    speed=self.mainmenu_system_voice_speedfactor)
            EvtObserver.fire(event)
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okvoice'))

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE:
            # maybe do action!
            if self.mainmenu_system_voice_comp_active:
                text = self.enter_mainmenu_sys_voice_comp_mute_lang()
            else:
                config = ConfigObj('picochess.ini')
                if 'computer-voice' in config:
                    del config['computer-voice']
                    config.write()
                event = Event.NEW_VOICE(type=self.mainmenu_system_voice, lang='en', speaker='mute', speed=2)
                EvtObserver.fire(event)
                text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okvoice'))

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG:
            text = self.enter_mainmenu_sys_voice_comp_mute_lang_speak()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            # do action!
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey].keys()
            config = ConfigObj('picochess.ini')
            skey = speakers[self.mainmenu_system_voice_comp_speak]
            config['computer-voice'] = vkey + ':' + skey
            config.write()
            event = Event.NEW_VOICE(type=self.mainmenu_system_voice, lang=vkey, speaker=skey,
                                    speed=self.mainmenu_system_voice_speedfactor)
            EvtObserver.fire(event)
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okvoice'))

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED:
            self.mainmenu_system_voice = Voice.SPEED
            text = self.enter_mainmenu_sys_voice_speed_factor()

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED_FACTOR:
            # do action!
            assert self.mainmenu_system_voice == Voice.SPEED, 'menu item is not Voice.SPEED: %s' % self.mainmenu_system_voice
            write_picochess_ini('speed-voice', self.mainmenu_system_voice_speedfactor)
            event = Event.NEW_VOICE(type=self.mainmenu_system_voice, lang='en', speaker='mute',  # lang & speaker ignored
                                    speed=self.mainmenu_system_voice_speedfactor)
            EvtObserver.fire(event)
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okspeed'))

        elif self.mainmenu_state == MainMenuState.SYS_DISP:
            if self.mainmenu_system_display == Display.PONDER:
                text = self.enter_mainmenu_sys_disp_ponder()
            if self.mainmenu_system_display == Display.CONFIRM:
                text = self.enter_mainmenu_sys_disp_confirm()
            if self.mainmenu_system_display == Display.CAPITAL:
                text = self.enter_mainmenu_sys_disp_capital()
            if self.mainmenu_system_display == Display.NOTATION:
                text = self.enter_mainmenu_sys_disp_notation()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM:
            text = self.enter_mainmenu_sys_disp_confirm_yesno()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM_YESNO:
            # do action!
            config = ConfigObj('picochess.ini')
            if self.mainmenu_system_display_confirm:
                config['disable-confirm-message'] = self.mainmenu_system_display_confirm
            elif 'disable-confirm-message' in config:
                del config['disable-confirm-message']
            config.write()
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okconfirm'))

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER:
            text = self.enter_mainmenu_sys_disp_ponder_interval()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER_INTERVAL:
            # do action!
            write_picochess_ini('ponder-interval', self.mainmenu_system_display_ponderinterval)
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okponder'))

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPITAL:
            text = self.enter_mainmenu_sys_disp_capital_yesno()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPTIAL_YESNO:
            # do action!
            config = ConfigObj('picochess.ini')
            if self.mainmenu_system_display_capital:
                config['enable-capital-letters'] = self.mainmenu_system_display_capital
            elif 'enable-capital-letters' in config:
                del config['enable-capital-letters']
            config.write()
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_okcapital'))

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION:
            text = self.enter_mainmenu_sys_disp_notation_move()

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION_MOVE:
            # do-action!
            config = ConfigObj('picochess.ini')
            if self.mainmenu_system_display_notation:
                config['disable-short-notation'] = self.mainmenu_system_display_notation
            elif 'disable-short-notation' in config:
                del config['disable-short-notation']
            config.write()
            text = self._fire_dispatchdgt(self.dgttranslate.text('B10_oknotation'))

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_left(self):
        """Change the menu state after LEFT action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.mainmenu_state == MainMenuState.TOP:
            pass

        elif self.mainmenu_state == MainMenuState.MODE:
            self.mainmenu_state = MainMenuState.SYS
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.MODE_TYPE:
            self.mainmenu_mode = ModeLoop.prev(self.mainmenu_mode)
            text = self.dgttranslate.text(self.mainmenu_mode.value)

        elif self.mainmenu_state == MainMenuState.POS:
            self.mainmenu_state = MainMenuState.MODE
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.POS_COL:
            self.mainmenu_position_whitetomove = not self.mainmenu_position_whitetomove
            text = self.dgttranslate.text('B00_sidewhite' if self.mainmenu_position_whitetomove else 'B00_sideblack')

        elif self.mainmenu_state == MainMenuState.POS_REV:
            self.mainmenu_position_reverse = not self.mainmenu_position_reverse
            text = self.dgttranslate.text('B00_bw' if self.mainmenu_position_reverse else 'B00_wb')

        elif self.mainmenu_state == MainMenuState.POS_UCI:
            if self.engine_has_960:
                self.mainmenu_position_uci960 = not self.mainmenu_position_uci960
                text = self.dgttranslate.text('B00_960yes' if self.mainmenu_position_uci960 else 'B00_960no')
            else:
                text = self.dgttranslate.text('Y10_error960')

        elif self.mainmenu_state == MainMenuState.POS_READ:
            text = self.dgttranslate.text('B00_nofunction')

        elif self.mainmenu_state == MainMenuState.TIME:
            self.mainmenu_state = MainMenuState.POS
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ:
            self.mainmenu_state = MainMenuState.TIME_FIXED
            self.mainmenu_time_mode = TimeModeLoop.prev(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ_CTRL:
            self.mainmenu_time_blitz = (self.mainmenu_time_blitz - 1) % len(self.tc_blitz_map)
            text = self.dgttranslate.text('B00_tc_blitz', self.tc_blitz_list[self.mainmenu_time_blitz])

        elif self.mainmenu_state == MainMenuState.TIME_FISCH:
            self.mainmenu_state = MainMenuState.TIME_BLITZ
            self.mainmenu_time_mode = TimeModeLoop.prev(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_FISCH_CTRL:
            self.mainmenu_time_fisch = (self.mainmenu_time_fisch - 1) % len(self.tc_fisch_map)
            text = self.dgttranslate.text('B00_tc_fisch', self.tc_fisch_list[self.mainmenu_time_fisch])

        elif self.mainmenu_state == MainMenuState.TIME_FIXED:
            self.mainmenu_state = MainMenuState.TIME_FISCH
            self.mainmenu_time_mode = TimeModeLoop.prev(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_FIXED_CTRL:
            self.mainmenu_time_fixed = (self.mainmenu_time_fixed - 1) % len(self.tc_fixed_map)
            text = self.dgttranslate.text('B00_tc_fixed', self.tc_fixed_list[self.mainmenu_time_fixed])

        elif self.mainmenu_state == MainMenuState.BOOK:
            self.mainmenu_state = MainMenuState.TIME
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.BOOK_NAME:
            self.mainmenu_book = (self.mainmenu_book - 1) % len(self.all_books)
            text = self._get_current_book_name()

        elif self.mainmenu_state == MainMenuState.ENG:
            self.mainmenu_state = MainMenuState.BOOK
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.ENG_NAME:
            self.mainmenu_engine_name = (self.mainmenu_engine_name - 1) % len(self.installed_engines)
            text = self._get_current_engine_name()

        elif self.mainmenu_state == MainMenuState.ENG_NAME_LEVEL:
            level_dict = self.installed_engines[self.mainmenu_engine_name]['level_dict']
            self.mainmenu_engine_level = (self.mainmenu_engine_level - 1) % len(level_dict)
            msg = sorted(level_dict)[self.mainmenu_engine_level]
            text = self.dgttranslate.text('B00_level', msg)

        elif self.mainmenu_state == MainMenuState.SYS:
            self.mainmenu_state = MainMenuState.ENG
            self.mainmenu_top = MainTopLoop.prev(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO:
            self.mainmenu_state = MainMenuState.SYS_DISP
            self.mainmenu_system = SystemLoop.prev(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_VERS:
            self.mainmenu_state = MainMenuState.SYS_INFO_BATTERY
            self.mainmenu_system_info = InfoLoop.prev(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_IP:
            self.mainmenu_state = MainMenuState.SYS_INFO_VERS
            self.mainmenu_system_info = InfoLoop.prev(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_BATTERY:
            self.mainmenu_state = MainMenuState.SYS_INFO_IP
            self.mainmenu_system_info = InfoLoop.prev(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_SOUND:
            self.mainmenu_state = MainMenuState.SYS_INFO
            self.mainmenu_system = SystemLoop.prev(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_SOUND_BEEP:
            self.mainmenu_system_sound = BeepLoop.prev(self.mainmenu_system_sound)
            text = self.dgttranslate.text(self.mainmenu_system_sound.value)

        elif self.mainmenu_state == MainMenuState.SYS_LANG:
            self.mainmenu_state = MainMenuState.SYS_SOUND
            self.mainmenu_system = SystemLoop.prev(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_LANG_NAME:
            self.mainmenu_system_language = LanguageLoop.prev(self.mainmenu_system_language)
            text = self.dgttranslate.text(self.mainmenu_system_language.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE:
            self.mainmenu_state = MainMenuState.SYS_LANG
            self.mainmenu_system = SystemLoop.prev(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER:
            self.mainmenu_state = MainMenuState.SYS_VOICE_COMP
            self.mainmenu_system_voice = VoiceLoop.prev(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE:
            self.mainmenu_system_voice_user_active = not self.mainmenu_system_voice_user_active
            msg = 'on' if self.mainmenu_system_voice_user_active else 'off'
            text = self.dgttranslate.text('B00_voice_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG:
            self.mainmenu_system_voice_user_lang = (self.mainmenu_system_voice_user_lang - 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
            text = self.dgttranslate.text('B00_language_' + vkey + '_menu')  # voice using same as language

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
            speakers = self.voices_conf[vkey]
            self.mainmenu_system_voice_user_speak = (self.mainmenu_system_voice_user_speak - 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.mainmenu_system_voice_user_speak)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP:
            self.mainmenu_state = MainMenuState.SYS_VOICE_SPEED
            self.mainmenu_system_voice = VoiceLoop.prev(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE:
            self.mainmenu_system_voice_comp_active = not self.mainmenu_system_voice_comp_active
            msg = 'on' if self.mainmenu_system_voice_comp_active else 'off'
            text = self.dgttranslate.text('B00_voice_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG:
            self.mainmenu_system_voice_comp_lang = (self.mainmenu_system_voice_comp_lang - 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
            text = self.dgttranslate.text('B00_language_' + vkey + '_menu')  # voice using same as language

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey]
            self.mainmenu_system_voice_comp_speak = (self.mainmenu_system_voice_comp_speak - 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.mainmenu_system_voice_comp_speak)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED:
            self.mainmenu_state = MainMenuState.SYS_VOICE_USER
            self.mainmenu_system_voice = VoiceLoop.prev(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED_FACTOR:
            self.mainmenu_system_voice_speedfactor = (self.mainmenu_system_voice_speedfactor - 1) % 10
            text = self.dgttranslate.text('B00_voice_speed', str(self.mainmenu_system_voice_speedfactor))

        elif self.mainmenu_state == MainMenuState.SYS_DISP:
            self.mainmenu_state = MainMenuState.SYS_VOICE
            self.mainmenu_system = SystemLoop.prev(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER:
            self.mainmenu_state = MainMenuState.SYS_DISP_NOTATION
            self.mainmenu_system_display = DisplayLoop.prev(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER_INTERVAL:
            self.mainmenu_system_display_ponderinterval -= 1
            if self.mainmenu_system_display_ponderinterval < 1:
                self.mainmenu_system_display_ponderinterval = 8
            text = self.dgttranslate.text('B00_ponder_interval', str(self.mainmenu_system_display_ponderinterval))

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM:
            self.mainmenu_state = MainMenuState.SYS_DISP_PONDER
            self.mainmenu_system_display = DisplayLoop.prev(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM_YESNO:
            self.mainmenu_system_display_confirm = not self.mainmenu_system_display_confirm
            msg = 'off' if self.mainmenu_system_display_confirm else 'on'
            text = self.dgttranslate.text('B00_confirm_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPITAL:
            self.mainmenu_state = MainMenuState.SYS_DISP_CONFIRM
            self.mainmenu_system_display = DisplayLoop.prev(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPTIAL_YESNO:
            self.mainmenu_system_display_capital = not self.mainmenu_system_display_capital
            msg = 'on' if self.mainmenu_system_display_capital else 'off'
            text = self.dgttranslate.text('B00_capital_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION:
            self.mainmenu_state = MainMenuState.SYS_DISP_CAPITAL
            self.mainmenu_system_display = DisplayLoop.prev(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION_MOVE:
            self.mainmenu_system_display_notation = not self.mainmenu_system_display_notation
            msg = 'long' if self.mainmenu_system_display_notation else 'short'
            text = self.dgttranslate.text('B00_notation_' + msg)

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_right(self):
        """Change the menu state after RIGHT action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.mainmenu_state == MainMenuState.TOP:
            pass

        elif self.mainmenu_state == MainMenuState.MODE:
            self.mainmenu_state = MainMenuState.POS
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.MODE_TYPE:
            self.mainmenu_mode = ModeLoop.next(self.mainmenu_mode)
            text = self.dgttranslate.text(self.mainmenu_mode.value)

        elif self.mainmenu_state == MainMenuState.POS:
            self.mainmenu_state = MainMenuState.TIME
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.POS_COL:
            self.mainmenu_position_whitetomove = not self.mainmenu_position_whitetomove
            text = self.dgttranslate.text('B00_sidewhite' if self.mainmenu_position_whitetomove else 'B00_sideblack')

        elif self.mainmenu_state == MainMenuState.POS_REV:
            self.mainmenu_position_reverse = not self.mainmenu_position_reverse
            text = self.dgttranslate.text('B00_bw' if self.mainmenu_position_reverse else 'B00_wb')

        elif self.mainmenu_state == MainMenuState.POS_UCI:
            if self.engine_has_960:
                self.mainmenu_position_uci960 = not self.mainmenu_position_uci960
                text = self.dgttranslate.text('B00_960yes' if self.mainmenu_position_uci960 else 'B00_960no')
            else:
                text = self.dgttranslate.text('Y10_error960')

        elif self.mainmenu_state == MainMenuState.POS_READ:
            text = self.dgttranslate.text('B10_nofunction')

        elif self.mainmenu_state == MainMenuState.TIME:
            self.mainmenu_state = MainMenuState.BOOK
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ:
            self.mainmenu_state = MainMenuState.TIME_FISCH
            self.mainmenu_time_mode = TimeModeLoop.next(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_BLITZ_CTRL:
            self.mainmenu_time_blitz = (self.mainmenu_time_blitz + 1) % len(self.tc_blitz_map)
            text = self.dgttranslate.text('B00_tc_blitz', self.tc_blitz_list[self.mainmenu_time_blitz])

        elif self.mainmenu_state == MainMenuState.TIME_FISCH:
            self.mainmenu_state = MainMenuState.TIME_FIXED
            self.mainmenu_time_mode = TimeModeLoop.next(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_FISCH_CTRL:
            self.mainmenu_time_fisch = (self.mainmenu_time_fisch + 1) % len(self.tc_fisch_map)
            text = self.dgttranslate.text('B00_tc_fisch', self.tc_fisch_list[self.mainmenu_time_fisch])

        elif self.mainmenu_state == MainMenuState.TIME_FIXED:
            self.mainmenu_state = MainMenuState.TIME_BLITZ
            self.mainmenu_time_mode = TimeModeLoop.next(self.mainmenu_time_mode)
            text = self.dgttranslate.text(self.mainmenu_time_mode.value)

        elif self.mainmenu_state == MainMenuState.TIME_FIXED_CTRL:
            self.mainmenu_time_fixed = (self.mainmenu_time_fixed + 1) % len(self.tc_fixed_map)
            text = self.dgttranslate.text('B00_tc_fixed', self.tc_fixed_list[self.mainmenu_time_fixed])

        elif self.mainmenu_state == MainMenuState.BOOK:
            self.mainmenu_state = MainMenuState.ENG
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.BOOK_NAME:
            self.mainmenu_book = (self.mainmenu_book + 1) % len(self.all_books)
            text = self._get_current_book_name()

        elif self.mainmenu_state == MainMenuState.ENG:
            self.mainmenu_state = MainMenuState.SYS
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.ENG_NAME:
            self.mainmenu_engine_name = (self.mainmenu_engine_name + 1) % len(self.installed_engines)
            text = self._get_current_engine_name()

        elif self.mainmenu_state == MainMenuState.ENG_NAME_LEVEL:
            level_dict = self.installed_engines[self.mainmenu_engine_name]['level_dict']
            self.mainmenu_engine_level = (self.mainmenu_engine_level + 1) % len(level_dict)
            msg = sorted(level_dict)[self.mainmenu_engine_level]
            text = self.dgttranslate.text('B00_level', msg)

        elif self.mainmenu_state == MainMenuState.SYS:
            self.mainmenu_state = MainMenuState.MODE
            self.mainmenu_top = MainTopLoop.next(self.mainmenu_top)
            text = self.dgttranslate.text(self.mainmenu_top.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO:
            self.mainmenu_state = MainMenuState.SYS_SOUND
            self.mainmenu_system = SystemLoop.next(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_VERS:
            self.mainmenu_state = MainMenuState.SYS_INFO_IP
            self.mainmenu_system_info = InfoLoop.next(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_IP:
            self.mainmenu_state = MainMenuState.SYS_INFO_BATTERY
            self.mainmenu_system_info = InfoLoop.next(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_INFO_BATTERY:
            self.mainmenu_state = MainMenuState.SYS_INFO_VERS
            self.mainmenu_system_info = InfoLoop.next(self.mainmenu_system_info)
            text = self.dgttranslate.text(self.mainmenu_system_info.value)

        elif self.mainmenu_state == MainMenuState.SYS_SOUND:
            self.mainmenu_state = MainMenuState.SYS_LANG
            self.mainmenu_system = SystemLoop.next(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_SOUND_BEEP:
            self.mainmenu_system_sound = BeepLoop.next(self.mainmenu_system_sound)
            text = self.dgttranslate.text(self.mainmenu_system_sound.value)

        elif self.mainmenu_state == MainMenuState.SYS_LANG:
            self.mainmenu_state = MainMenuState.SYS_VOICE
            self.mainmenu_system = SystemLoop.next(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_LANG_NAME:
            self.mainmenu_system_language = LanguageLoop.next(self.mainmenu_system_language)
            text = self.dgttranslate.text(self.mainmenu_system_language.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE:
            self.mainmenu_state = MainMenuState.SYS_DISP
            self.mainmenu_system = SystemLoop.next(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER:
            self.mainmenu_state = MainMenuState.SYS_VOICE_SPEED
            self.mainmenu_system_voice = VoiceLoop.next(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE:
            self.mainmenu_system_voice_user_active = not self.mainmenu_system_voice_user_active
            msg = 'on' if self.mainmenu_system_voice_user_active else 'off'
            text = self.dgttranslate.text('B00_voice_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG:
            self.mainmenu_system_voice_user_lang = (self.mainmenu_system_voice_user_lang + 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
            text = self.dgttranslate.text('B00_language_' + vkey + '_menu')  # voice using same as language

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_user_lang]
            speakers = self.voices_conf[vkey]
            self.mainmenu_system_voice_user_speak = (self.mainmenu_system_voice_user_speak + 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.mainmenu_system_voice_user_speak)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP:
            self.mainmenu_state = MainMenuState.SYS_VOICE_USER
            self.mainmenu_system_voice = VoiceLoop.next(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE:
            self.mainmenu_system_voice_comp_active = not self.mainmenu_system_voice_comp_active
            msg = 'on' if self.mainmenu_system_voice_comp_active else 'off'
            text = self.dgttranslate.text('B00_voice_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG:
            self.mainmenu_system_voice_comp_lang = (self.mainmenu_system_voice_comp_lang + 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
            text = self.dgttranslate.text('B00_language_' + vkey + '_menu')  # voice using same as language

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.mainmenu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey]
            self.mainmenu_system_voice_comp_speak = (self.mainmenu_system_voice_comp_speak + 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.mainmenu_system_voice_comp_speak)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED:
            self.mainmenu_state = MainMenuState.SYS_VOICE_COMP
            self.mainmenu_system_voice = VoiceLoop.next(self.mainmenu_system_voice)
            text = self.dgttranslate.text(self.mainmenu_system_voice.value)

        elif self.mainmenu_state == MainMenuState.SYS_VOICE_SPEED_FACTOR:
            self.mainmenu_system_voice_speedfactor = (self.mainmenu_system_voice_speedfactor + 1) % 10
            text = self.dgttranslate.text('B00_voice_speed', str(self.mainmenu_system_voice_speedfactor))

        elif self.mainmenu_state == MainMenuState.SYS_DISP:
            self.mainmenu_state = MainMenuState.SYS_INFO
            self.mainmenu_system = SystemLoop.next(self.mainmenu_system)
            text = self.dgttranslate.text(self.mainmenu_system.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER:
            self.mainmenu_state = MainMenuState.SYS_DISP_CONFIRM
            self.mainmenu_system_display = DisplayLoop.next(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_PONDER_INTERVAL:
            self.mainmenu_system_display_ponderinterval += 1
            if self.mainmenu_system_display_ponderinterval > 8:
                self.mainmenu_system_display_ponderinterval = 1
            text = self.dgttranslate.text('B00_ponder_interval', str(self.mainmenu_system_display_ponderinterval))

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM:
            self.mainmenu_state = MainMenuState.SYS_DISP_CAPITAL
            self.mainmenu_system_display = DisplayLoop.next(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CONFIRM_YESNO:
            self.mainmenu_system_display_confirm = not self.mainmenu_system_display_confirm
            msg = 'off' if self.mainmenu_system_display_confirm else 'on'
            text = self.dgttranslate.text('B00_confirm_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPITAL:
            self.mainmenu_state = MainMenuState.SYS_DISP_NOTATION
            self.mainmenu_system_display = DisplayLoop.next(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_CAPTIAL_YESNO:
            self.mainmenu_system_display_capital = not self.mainmenu_system_display_capital
            msg = 'on' if self.mainmenu_system_display_capital else 'off'
            text = self.dgttranslate.text('B00_capital_' + msg)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION:
            self.mainmenu_state = MainMenuState.SYS_DISP_PONDER
            self.mainmenu_system_display = DisplayLoop.next(self.mainmenu_system_display)
            text = self.dgttranslate.text(self.mainmenu_system_display.value)

        elif self.mainmenu_state == MainMenuState.SYS_DISP_NOTATION_MOVE:
            self.mainmenu_system_display_notation = not self.mainmenu_system_display_notation
            msg = 'long' if self.mainmenu_system_display_notation else 'short'
            text = self.dgttranslate.text('B00_notation_' + msg)

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_middle(self):
        """Change the menu state after MIDDLE action."""
        def _exit_position():
            self.mainmenu_state = MainMenuState.POS_READ
            return self.main_down()

        text = self.dgttranslate.text('B00_nofunction')
        if False:  # switch-case
            pass
        elif self.mainmenu_state == MainMenuState.POS:
            text = _exit_position()

        elif self.mainmenu_state == MainMenuState.POS_COL:
            text = _exit_position()

        elif self.mainmenu_state == MainMenuState.POS_REV:
            text = _exit_position()

        elif self.mainmenu_state == MainMenuState.POS_UCI:
            text = _exit_position()

        elif self.mainmenu_state == MainMenuState.POS_READ:
            text = _exit_position()

        else:  # Default
            pass

        self.current_text = text
        return text

    def updt_right(self):
        """Change the menu state after RIGHT action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.updtmenu_state == UpdtMenuState.TOP:
            pass
        elif self.updtmenu_state == UpdtMenuState.UPDATE:
            self.updtmenu_state = UpdtMenuState.LOG
            self.updtmenu_top = UpdtTopLoop.next(self.updtmenu_top)
            text = self.dgttranslate.text(self.updtmenu_top.value)
        elif self.updtmenu_state == UpdtMenuState.UPDATE_RELEASE:
            self.updtmenu_version = (self.updtmenu_version + 1) % len(self.updtmenu_tags)
            text = self.dgttranslate.text('B00_updt_version', self.updtmenu_tags[self.updtmenu_version][1],
                                          devs=self.updtmenu_devs)
            text.rd = ClockIcons.DOT
        elif self.updtmenu_state == UpdtMenuState.LOG:
            self.updtmenu_state = UpdtMenuState.UPDATE
            self.updtmenu_top = UpdtTopLoop.next(self.updtmenu_top)
            text = self.dgttranslate.text(self.updtmenu_top.value)
        else:  # Default
            pass

        self.current_text = text
        return text

    def updt_left(self):
        """Change the menu state after LEFT action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.updtmenu_state == UpdtMenuState.TOP:
            pass
        elif self.updtmenu_state == UpdtMenuState.UPDATE:
            self.updtmenu_state = UpdtMenuState.LOG
            self.updtmenu_top = UpdtTopLoop.prev(self.updtmenu_top)
            text = self.dgttranslate.text(self.updtmenu_top.value)
        elif self.updtmenu_state == UpdtMenuState.UPDATE_RELEASE:
            self.updtmenu_version = (self.updtmenu_version - 1) % len(self.updtmenu_tags)
            text = self.dgttranslate.text('B00_updt_version', self.updtmenu_tags[self.updtmenu_version][1],
                                          devs=self.updtmenu_devs)
            text.rd = ClockIcons.DOT
        elif self.updtmenu_state == UpdtMenuState.LOG:
            self.updtmenu_state = UpdtMenuState.UPDATE
            self.updtmenu_top = UpdtTopLoop.prev(self.updtmenu_top)
            text = self.dgttranslate.text(self.updtmenu_top.value)
        else:  # Default
            pass

        self.current_text = text
        return text

    def updt_down(self, dev):
        """Change the menu state after DOWN action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.updtmenu_state == UpdtMenuState.TOP:
            pass
        elif self.updtmenu_state == UpdtMenuState.UPDATE:
            text = self.enter_updtmenu_update_release()
        elif self.updtmenu_state == UpdtMenuState.UPDATE_RELEASE:
            # do action!
            EvtObserver.fire(Event.UPDATE_PICO(tag=self.updtmenu_tags[self.updtmenu_version][0]))
            text = self._fire_dispatchdgt(self.dgttranslate.text('Y00_update'))
        elif self.updtmenu_state == UpdtMenuState.LOG:
            # maybe do action!
            if self.log_file:
                self.updtmenu_devs.discard(dev)
                EvtObserver.fire(Event.EMAIL_LOG())
                text = self._fire_dispatchdgt(self.dgttranslate.text('B10_oklogfile'))
            else:
                text = self.dgttranslate.text('B10_nofunction')
        else:  # Default
            pass

        self.current_text = text
        return text

    def updt_up(self, dev):
        """Change the menu state after UP action."""
        text = self.dgttranslate.text('Y00_errormenu')
        if False:  # switch-case
            pass
        elif self.updtmenu_state == UpdtMenuState.TOP:
            pass
        elif self.updtmenu_state == UpdtMenuState.UPDATE:
            self.updtmenu_devs.discard(dev)
            text = self.enter_updtmenu_top()
        elif self.updtmenu_state == UpdtMenuState.UPDATE_RELEASE:
            text = self.enter_updtmenu_update()
        elif self.updtmenu_state == UpdtMenuState.LOG:
            self.updtmenu_devs.discard(dev)
            text = self.enter_updtmenu_top()
        else:  # Default
            pass

        self.current_text = text
        return text

    def updt_middle(self, dev):
        """Change the menu state after MIDDLE action."""
        self.updtmenu_devs.add(dev)
        text = self.dgttranslate.text('B00_nofunction')
        if False:  # switch-case
            pass
        elif self.updtmenu_top == UpdtTop.UPDATE:
            text = self.enter_updtmenu_update()
        elif self.updtmenu_top == UpdtTop.LOG:
            text = self.enter_updtmenu_log()
        else:  # Default
            text = self.dgttranslate.text('Y00_errormenu')

        self.current_text = text
        return text

    def get_current_text(self):
        """Return the current text."""
        return self.current_text
