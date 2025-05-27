import ipaddress
import os
import threading
import time
from datetime import datetime, timedelta
from queue import Queue

import pytz
from airodor_wifi_api import airodor
from flask import Flask, redirect, render_template, request, url_for

env_variable_venilation_address = "VENTILATION_ADDRESS"
default_IP = ipaddress.ip_address("192.168.2.122")
env_variable_server_name = "SERVER_NAME"
default_server_name = "Ventilation Server"
env_variable_test_mode = "TEST_MODE"

# check if ipadress is given as environment variable
if env_variable_venilation_address in os.environ:
    current_ip = ipaddress.ip_address(os.environ[env_variable_venilation_address])
else:
    current_ip = default_IP

# check if server name is given as environment variable
if env_variable_server_name in os.environ:
    server_name = os.environ[env_variable_server_name]
else:
    server_name = default_server_name

lock_timer_dict = threading.Lock()
timer_dict = {"A": airodor.VentilationTimerList(), "B": airodor.VentilationTimerList()}
timezone = pytz.timezone('Europe/Berlin')

lock_message_queue = threading.Lock()
return_message_queue = Queue(maxsize=10)

# enable/disable real communication with the ventilation device
do_real_communication = False

# check if test mode is given as environment variable
if env_variable_test_mode in os.environ:
    do_real_communication = False
else:
    do_real_communication = True
app = Flask(__name__)

# status variable to check if the backend thread is running
backend_running = False


def backend_thread():
    while 1:
        # print(datetime.now().time())
        check_and_update_timers()
        time.sleep(10)


def add_message_to_queue(message: str):
    global return_message_queue
    with lock_message_queue:
        if return_message_queue.full():
            return_message_queue.get()
        return_message_queue.put(message)


def message_queue_to_string() -> str:
    global return_message_queue
    with lock_message_queue:
        return str("\n".join(return_message_queue.queue))


def check_and_update_timers():
    with lock_timer_dict:
        global timer_dict
        is_ok = False
        now = datetime.now(timezone)
        for td in timer_dict:
            for timer in timer_dict[td].timer_list[:]:  # loop over a copy but ...
                if timer.execution_time < now:
                    if do_real_communication:
                        is_ok = airodor.set_mode(current_ip, timer.group, timer.mode)
                    else:
                        is_ok = True
                    # remove the timer from the list
                    if is_ok:
                        print("removing timer {}".format(timer))
                        timer_dict[td].timer_list.remove(timer)  # ... remove from the original
                        add_message_to_queue(
                            "Executed timer for group {} and mode {}".format(timer.group.name, timer.mode.name)
                        )
                    else:
                        add_message_to_queue("Error processing queue")


@app.route('/')
def index():
    global backend_running
    if not backend_running:
        threading.Thread(target=backend_thread).start()
        backend_running = True
    now = datetime.now(timezone)
    timer_val_A = ""
    timer_val_B = ""
    if do_real_communication:
        vent_mode_A = airodor.get_mode(current_ip, group=airodor.VentilationGroup.A)
        if vent_mode_A:
            add_message_to_queue("Success reading status for group A")
            if vent_mode_A == airodor.VentilationModeRead.TIMED_OFF:
                timer_val_A = airodor.get_timer(current_ip, group=airodor.VentilationGroup.A)
        else:
            add_message_to_queue("Error reading status for group A")
        vent_mode_B = airodor.get_mode(current_ip, group=airodor.VentilationGroup.B)
        if vent_mode_B:
            add_message_to_queue("Success reading status for group B")
            if vent_mode_B == airodor.VentilationModeRead.TIMED_OFF:
                timer_val_B = airodor.get_timer(current_ip, group=airodor.VentilationGroup.A)
        else:
            add_message_to_queue("Error reading status for group B")
    else:
        vent_mode_A = airodor.VentilationModeRead.ALTERNATING_MAX
        add_message_to_queue("Success reading status for group A")
        vent_mode_B = airodor.VentilationModeRead.INSIDE_MED
        add_message_to_queue("Success reading status for group B")
    return render_template(
        'index.html',
        server_name=server_name,
        ip_address=current_ip,
        ventilation_modes=airodor.VentilationModeSet,
        status_string_group_A=vent_mode_A.name + (f"→{timer_val_A}h" if timer_val_A else ""),
        status_time_group_A=now.strftime("%X"),
        status_string_group_B=vent_mode_B.name + (f"→{timer_val_B}h" if timer_val_B else ""),
        status_time_group_B=now.strftime("%X"),
        timer_list_A=timer_dict["A"].create_string_list(),
        timer_list_B=timer_dict["B"].create_string_list(),
        comm_log=message_queue_to_string(),
    )


@app.route('/updateIP/', methods=['POST'])
def updateIP():
    if request.method == "POST":
        try:
            new_ip = ipaddress.ip_address(request.form.get('ip_address'))
            global current_ip
            current_ip = new_ip
        except ValueError:
            print("Got invalid ipaddress: {}".format(request.form.get('ip_address')))
    return redirect(url_for("index"))


@app.route('/add_timer/', methods=['POST'])
def add_timer():
    print('new timer')
    if request.method == "POST":
        deltatime = int(request.form.get('timerValue'))
        mode = int(request.form.get('mode_select'))
        group = request.form.get('group_select')
        print("timer:group {}, mode {}, value {}".format(group, mode, deltatime))
        if mode >= 0:
            mode = airodor.VentilationModeSet(mode)
            if group == "both":
                group = [airodor.VentilationGroup("A"), airodor.VentilationGroup("B")]
            else:
                group = [airodor.VentilationGroup(group)]

            for g in group:
                global timer_dict
                timer_dict[g.name].add_list_item(datetime.now(timezone) + timedelta(minutes=deltatime), g, mode)
                add_message_to_queue("Added timer for group {} with mode {}".format(g.name, mode.name))

    check_and_update_timers()
    return redirect(url_for("index"))


@app.route('/remove_timer/', methods=['POST'])
def remove_timer():
    print('remove timer')
    if request.method == "POST":
        remove_from = dict()
        remove_from["A"] = request.form.getlist('selected_indices_listA')
        remove_from["B"] = request.form.getlist('selected_indices_listB')

        global timer_dict
        for remove_list_key in remove_from:
            # we have to remove the higher indices first, otherwise we can not loop
            remove_indices = [int(i) for i in remove_from[remove_list_key]]
            remove_indices.reverse()
            for remove_index in remove_indices:
                add_message_to_queue(
                    "Removed timer for group {} with mode {}".format(
                        timer_dict[remove_list_key].timer_list[remove_index].group.name,
                        timer_dict[remove_list_key].timer_list[remove_index].mode.name,
                    )
                )
                del timer_dict[remove_list_key].timer_list[int(remove_index)]

    return redirect(url_for("index"))


@app.route('/both_one_dir_max_now_alternate_med_500/', methods=['POST'])
def both_one_dir_max_now_alternate_med_500():
    print('new timer')
    if request.method == "POST":
        group = [airodor.VentilationGroup("A"), airodor.VentilationGroup("B")]

        for g in group:
            global timer_dict
            timer_dict[g.name].add_list_item(datetime.now(timezone), g, airodor.VentilationModeSet.ONE_DIR_MAX)
            timer_dict[g.name].add_list_item(
                datetime.now(timezone) + timedelta(minutes=500), g, airodor.VentilationModeSet.ALTERNATING_MED
            )
        add_message_to_queue("Fast action: ONE_DIR_MAX now and ALTERNATING_MED in 500m")

    check_and_update_timers()
    return redirect(url_for("index"))


def main():
    app.run(debug=True, host="0.0.0.0")


if __name__ == '__main__':
    main()
