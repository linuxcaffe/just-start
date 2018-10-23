#!/usr/bin/env python3
from datetime import datetime, timedelta
from enum import Enum
from functools import partial
from itertools import cycle
from threading import Timer
from typing import Dict, Any, Tuple, Optional, Callable

from just_start.constants import (
    STOP_MESSAGE, SKIP_NOT_ENABLED, INVALID_PHASE_NUMBER, SKIP_ENABLED,
    LONG_BREAK_SKIP_NOT_ENABLED,
)
from ._log import log
from just_start.config_reader import get_location_name, get_pomodoro_config
from just_start.os_utils import (
    JustStartError, UserInputError, db, block_sites,
)


def time_after_seconds(seconds_left: int) -> str:
    end_time = datetime.now() + timedelta(seconds=seconds_left)
    return end_time.strftime('%H:%M')


class Phase(Enum):
    WORK = 'Work and switch tasks'
    SHORT_REST = 'Short break'
    LONG_REST = 'LONG BREAK!!!'


class PomodoroError(JustStartError):
    pass


class PromptSkippedPhases(Exception):
    pass


class PomodoroTimer:
    SERIALIZABLE_ATTRIBUTES = ('pomodoro_cycle', 'phase', 'time_left', 'work_count')

    def __init__(self, notifier: Callable, notify: bool = False):

        self.start_datetime = self.timer = None
        self.is_running = False
        self.work_count = 0
        self.PHASE_DURATION = self._generate_phase_duration()

        self.pomodoro_cycle = self._create_cycle()
        self.phase, self.time_left = self._get_next_phase_and_time_left()
        self.skip_enabled = False

        self.notifier = notifier
        if notify:
            self.notifier(STOP_MESSAGE)

    @property
    def serializable_data(self) -> Dict[str, Any]:
        self._pause()
        return {attribute: self.__getattribute__(attribute) for attribute
                in self.SERIALIZABLE_ATTRIBUTES}

    @serializable_data.setter
    def serializable_data(self, data: Dict) -> None:
        for attribute, value in data.items():
            self.__setattr__(attribute, value)

    def _pause(self) -> None:
        self._cancel_timer()
        self.is_running = False
        block_sites(True)

    def _cancel_timer(self) -> None:
        if self.is_running:
            self.timer.cancel()
            elapsed_timedelta = datetime.now() - self.start_datetime
            self.time_left -= elapsed_timedelta.seconds

    @property
    def skip_enabled(self) -> bool:
        return db.get(SKIP_ENABLED, False)

    @skip_enabled.setter
    def skip_enabled(self, value: bool):
        db[SKIP_ENABLED] = value

    @staticmethod
    def _generate_phase_duration() -> Dict:
        pomodoro_config = get_pomodoro_config()
        durations = (duration * 60 for duration in (pomodoro_config.pomodoro_length,
                                                    pomodoro_config.short_rest,
                                                    pomodoro_config.long_rest))
        phase_duration = dict(zip(Phase, durations))
        return phase_duration

    @staticmethod
    def _create_cycle() -> cycle:
        states = ([Phase.WORK, Phase.SHORT_REST] *
                  get_pomodoro_config().cycles_before_long_rest)
        states[-1] = Phase.LONG_REST
        return cycle(states)

    def _get_next_phase_and_time_left(self) -> Tuple[Phase, int]:
        next_phase = next(self.pomodoro_cycle)
        return next_phase, self.PHASE_DURATION[next_phase]

    def toggle(self) -> None:
        if self.is_running:
            self._pause()
            self.notifier('Paused')
        else:
            self._run()

    def _run(self) -> None:
        self.start_datetime = datetime.now()
        now = self.start_datetime.time().strftime('%H:%M')
        pomodoros = 'pomodoro' if self.work_count == 1 else 'pomodoros'
        self.notifier(f'{self.phase.value} - {self.work_count} {pomodoros} so'
                      f' far at {get_location_name()}.'
                      f'\n{now} - {time_after_seconds(self.time_left)}'
                      f' ({int(self.time_left / 60)} mins)')

        self.timer = Timer(self.time_left, partial(self.advance_phases, False))
        self.timer.start()
        self.is_running = True
        block_sites(self.phase is self.phase.WORK)

    def advance_phases(self, is_skipping=True,
                       phases_skipped: Optional[int]=1) -> None:
        log.debug(f'advancing pomodoro phases (db: {db}, skipping:'
                  f' {is_skipping}, phase: {self.phase})')
        if is_skipping:
            if self.phase is self.phase.WORK:
                if not self.skip_enabled:
                    raise PomodoroError(SKIP_NOT_ENABLED)

                if phases_skipped is None:
                    raise PromptSkippedPhases

                if phases_skipped < 1:
                    raise UserInputError(INVALID_PHASE_NUMBER)

                self.skip_enabled = False
                # A skipped work phase is counted as finished
                self.work_count += 1
            else:
                phases_skipped = phases_skipped or 1
        else:
            self.skip_enabled = True
            self.work_count += 1

        self._cancel_timer()

        # Skipped phases count as finished (but not the running one)
        for _ in range(phases_skipped - 1):
            phase, _ = self._get_next_phase_and_time_left()

            if phase is self.phase.WORK:
                self.work_count += 1

        phase, time_left = self._get_next_phase_and_time_left()

        if is_skipping and phase is self.phase.LONG_REST:
            raise PomodoroError(LONG_BREAK_SKIP_NOT_ENABLED)

        self.phase, self.time_left = phase, time_left

        self._run()

    def reset(self) -> None:
        self._pause()
        self.__init__(notifier=self.notifier, notify=True)
