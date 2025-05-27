'''This module provides basic methods to create the api calls'''
from datetime import datetime
from enum import Enum
from ipaddress import ip_address
from typing import List

import requests
import time
from yarl import URL


class ExtendedEnum(Enum):
    @classmethod
    def list(cls):
        return list(map(lambda c: c.name, cls))


class VentilationGroup(Enum):
    '''Basic enum to represent ventilation groups'''

    A = "A"
    B = "B"


class VentilationAction(ExtendedEnum):
    '''Basic enum to represent ventilation actions'''

    READ_MODE = "R"
    WRITE_MODE = "W"
    READ_OFF_TIMER = "T"
    SET_OFF_TIMER = "S"


class VentilationModeSet(ExtendedEnum):
    '''Basic enum to represent the available ventilation modes when setting modes'''

    OFF = 0
    ALTERNATING_MIN = 1
    ALTERNATING_MED = 2
    ALTERNATING_MAX = 4
    ONE_DIR_MED = 8
    ONE_DIR_MAX = 16
    INSIDE_MED = 32
    INSIDE_MAX = 64


class VentilationModeRead(ExtendedEnum):
    '''Basic enum to represent the available ventilation modes when reading modes'''

    OFF = 0
    ALTERNATING_MIN = 1
    ALTERNATING_MED = 2
    ALTERNATING_MED_FORCED = 3
    ALTERNATING_MAX = 6
    ONE_DIR_MED = 10
    ONE_DIR_MAX = 18
    INSIDE_MED = 34
    INSIDE_MAX = 66
    TIMED_OFF = 130
    UNKNOWN = 999


class VentilationAnswerType(Enum):
    '''Basic enum to represent the available answer types'''

    R = "R"
    M = "M"
    T = "T"
    S = "S"


class VentilationTimerList:
    '''class to handle a list of timer entries for the ventilation'''

    class VentilationTimerEntry:
        '''helper class to hold all necessary data of a timer list entry'''

        def __init__(self, time: datetime, group: VentilationGroup, mode: VentilationModeSet):
            self.execution_time = time
            self.group = group
            self.mode = mode

    def __init__(self):
        self.timer_list: List[self.VentilationTimerEntry] = []

    def add_list_item(self, time: datetime, group: VentilationGroup, mode: VentilationModeSet):
        '''add a new entry to the timer list'''
        self.timer_list.append(self.VentilationTimerEntry(time=time, group=group, mode=mode))
        # in-place sorting is also possible
        self.timer_list.sort(key=lambda x: x.execution_time.strftime("%Y%m%d%H%M%S"))

    def pop_list_item(self) -> VentilationTimerEntry:
        '''remove the first item from the list and return it'''
        return self.timer_list.pop(0)

    def create_string_list(self) -> List[str]:
        '''create a list of strings for all entries'''
        str_list = [
            "{} @ {}".format(e.mode.name, e.execution_time.strftime("%H:%M:%S, %d/%m/%Y")) for e in self.timer_list
        ]
        return str_list


def get_base_api_url(ip_addr: ip_address) -> URL:
    '''create the basic url to communicate to the wifi module'''
    return URL(f"http://{ip_addr}/msg?Function=")


def get_request_url(
    ip_addr: ip_address, action: VentilationAction, group: VentilationGroup, mode: VentilationModeSet = ""
) -> URL:
    '''create url for the required action, group and mode'''
    url = get_base_api_url(ip_addr=ip_addr)

    if action == VentilationAction.WRITE_MODE:
        assert VentilationModeSet != ""
        return URL(f"{url}{action.value}{group.value}{mode.value}")
    if action == VentilationAction.READ_MODE:
        return URL(f"{url}{action.value}{group.value}")
    if action == VentilationAction.READ_OFF_TIMER:
        return URL(f"{url}{action.value}{group.value}")

    raise NotImplementedError(f"VentilationAction {action} is not yet implemented")


def interpret_answer(answer: requests.Response) -> tuple:
    '''interpret the request answer from the wifi module.
    For READ, the return is (group, mode).
    For WRITE, the return is (group, OK?)
    For TIMER_READ, the return is (group, timer_value)'''
    # assert that the answer is valid
    assert answer.ok
    # first character is always answer type
    vat = VentilationAnswerType(answer.text[0])
    # second character is always group
    group = VentilationGroup(answer.text[1])

    if vat == VentilationAnswerType.R:
        # for read type, the character 2+ is the ventilation mode
        mode_number = int(answer.text[2:])
        if mode_number in VentilationModeRead:
            mode = VentilationModeRead(mode_number)
        elif mode_number in VentilationModeSet:
            # right after setting a mode, the answer is part of the "Set" enum
            # it switches to the "Read" enum after some seconds
            mode = VentilationModeSet(mode_number)
        else:
            mode = VentilationModeRead.UNKNOWN
        return group, mode
    if vat == VentilationAnswerType.M:
        # for write type, the character 2+ is the "OK" notifier
        return group, (answer.text[2:] == "OK")
    if vat == VentilationAnswerType.T:
        return group, (int(answer.text[2:]))


    raise NotImplementedError(f"VentilationAnswer for {vat} is not yet implemented")


def get_timer(ip_addr: ip_address, group: VentilationGroup) -> VentilationModeRead:
    '''get the current mode for the given ip and ventilation group'''
    print(f"getting timer value for group {group} from {ip_addr}")
    request = get_request_url(ip_addr=ip_addr, action=VentilationAction.READ_OFF_TIMER, group=group)
    try:
        r = requests.get(str(request), timeout=10)
        r_group, timer_value = interpret_answer(r)
        assert r_group == group  # answer should fit to the request
        return timer_value
    except requests.exceptions.Timeout:
        return None
    
def get_mode(ip_addr: ip_address, group: VentilationGroup) -> VentilationModeRead:
    '''get the current mode for the given ip and ventilation group'''
    print(f"getting status for group {group} from {ip_addr}")
    request = get_request_url(ip_addr=ip_addr, action=VentilationAction.READ_MODE, group=group)
    try:
        r = requests.get(str(request), timeout=10)
        r_group, r_mode = interpret_answer(r)
        assert r_group == group  # answer should fit to the request
        return r_mode
    except requests.exceptions.Timeout:
        return None


def set_mode(ip_addr: ip_address, group: VentilationGroup, mode: VentilationModeRead) -> bool:
    '''set mode for the given ip and ventilation group'''
    request = get_request_url(ip_addr=ip_addr, action=VentilationAction.WRITE_MODE, group=group, mode=mode)
    try:
        r = requests.get(str(request), timeout=10)
        r_group, is_ok = interpret_answer(r)
        assert r_group == group  # answer should fit to the request
        time.sleep(1)
        return is_ok
    except requests.exceptions.Timeout:
        return False
