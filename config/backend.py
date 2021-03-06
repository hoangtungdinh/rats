from distutils import dir_util
import uuid
import os
import time

import signal
import yaml
from SwarmBootstrapUtils import yaml_parser
import subprocess
import enum
import threading


class Launcher:
    def __init__(self):
        self._run_process = None
        self._status = Launcher.Status.IDLE
        self._status_file = 'status.txt'

        # if not self._has_valid_initial_state():
        #     raise ValueError(
        #         'Launcher was terminated improperly and the last state is: ' +
        #         self._read_last_state_from_file())

    @staticmethod
    def _clone_config_folder(original_folder_dir):
        original_folder_name = original_folder_dir.split('/')[-1]
        current_dir = os.path.dirname(os.path.realpath(__file__))
        generated_folder_dir = current_dir + '/' + original_folder_name + '_tmp_' + str(
            uuid.uuid4())
        dir_util.copy_tree(original_folder_dir, generated_folder_dir)
        return generated_folder_dir

    @staticmethod
    def _replace_drone_ip(config_dir, drone_ips):
        config_file_dir = config_dir + '/config.yaml'
        config = yaml_parser.read(config_file_dir)
        for drone_name, ip in drone_ips.items():
            if drone_name in config['bebops']:
                config['bebops'][drone_name]['bebop_ip'] = ip
        config_file = open(config_file_dir, 'w')
        yaml.dump(config, config_file, default_flow_style=False)

    def _start_script(self, config_dir, drone_ips):
        cloned_config_dir = self._clone_config_folder(config_dir)
        self._replace_drone_ip(cloned_config_dir, drone_ips)
        run_cmd = 'python3 run.py ' + cloned_config_dir
        self._run_process = subprocess.Popen(run_cmd.split(), start_new_session=True,
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _stop_script(self):
        pgid = os.getpgid(self._run_process.pid)
        os.killpg(pgid, signal.SIGINT)
        os.waitpid(-pgid, 0)
        alive_pgids = subprocess.check_output('ps x o pgid'.split()).decode(
            "utf-8").rstrip().replace(' ', '').split('\n')
        while str(pgid) in alive_pgids:
            time.sleep(1)
            alive_pgids = subprocess.check_output('ps x o pgid'.split()).decode(
                "utf-8").rstrip().replace(' ', '').split('\n')
        self._change_status(Launcher.Status.IDLE)
        self._run_process = None

    def _wait_for_ready(self):
        while self._status == Launcher.Status.LAUNCHING:
            next_line = self._run_process.stdout.readline().decode("utf-8").rstrip()
            print(next_line)
            if next_line == 'TEST YOUR XBOX CONTROLLER, PRESS ENTER WHEN YOU ARE READY!':
                if self._status == Launcher.Status.LAUNCHING:
                    self._change_status(Launcher.Status.READY)
                return

    def launch(self, config_dir, drone_ips):
        if self._status == Launcher.Status.IDLE:
            self._change_status(Launcher.Status.LAUNCHING)
            self._start_script(config_dir, drone_ips)
            wait_thread = threading.Thread(target=self._wait_for_ready)
            wait_thread.start()
        else:
            raise ValueError(
                'Script can only be launched if current state is IDLE, but the current state is: '
                '' + str(self._status.name))

    def start_flying(self):
        if self._status == Launcher.Status.READY:
            self._change_status(Launcher.Status.FLYING)
            try:
                self._run_process.communicate(b'\n', timeout=0.5)
            except subprocess.TimeoutExpired:
                # we don't expect the child process to terminate
                return
        else:
            raise ValueError(
                'Can only start flying if the current state is READY, but the current state is: '
                + str(
                    self._status.name))

    def stop(self):
        if self._status == Launcher.Status.STOPPING:
            raise ValueError('Waiting for all processes being killed. Please be patient...')
        elif self._status == Launcher.Status.IDLE:
            raise ValueError('There is no process running')
        else:
            self._change_status(Launcher.Status.STOPPING)
            stopping_thread = threading.Thread(target=self._stop_script)
            stopping_thread.start()

    def get_status(self):
        return self._status

    def _change_status(self, new_status):
        self._status = new_status
        self._write_current_state_to_file()

    def _write_current_state_to_file(self):
        with open(self._status_file, 'a+') as file:
            file.write(str(self._status.name) + '\n')

    # def _read_last_state_from_file(self):
    #     with open(self._status_file, 'a+') as file:
    #         # The last line is a blank line. We read the second last one
    #         lines = file.readlines()
    #         if len(lines) >= 2:
    #             last_state = file.readlines()[-2]
    #         else:
    #             last_state = ''
    #     return last_state

    # def _has_valid_initial_state(self):
    #     last_state = self._read_last_state_from_file()
    #     if last_state == '' or last_state == Launcher.Status.IDLE.name:
    #         return True
    #     else:
    #         return False

    class Status(enum.Enum):
        IDLE = 1
        LAUNCHING = 2
        READY = 3
        FLYING = 4
        STOPPING = 5
