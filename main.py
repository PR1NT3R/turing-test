from vm_core import signal_handler, get_files_and_stats_data, update_stats, update_files, SelfModifyingVM, add_vm_message, get_message_history_and_last_message_id
from flask import Flask, render_template_string, request, jsonify, render_template # type:ignore
import threading
import platform
import string
import random
import signal
import queue
import time
import json
import sys
import os
import re

vm = SelfModifyingVM()

if platform.system() == 'Windows':
    FILES_PATH = os.getcwd()
else:
    FILES_PATH = '/home/pr1nt3r/turing_test'

CODE_FILE = os.path.join(FILES_PATH, 'code.json')
MEMORY_FILE = os.path.join(FILES_PATH, 'memory.json')
VM_STATE_FILE = os.path.join(FILES_PATH, 'vm_state.json')

# TO MODIFY
EXAMPLE_CODE = [
            "set var1 hello",
            "output var1"
        ]

MAX_MESSAGE_HISTORY = 100

# basically useless
PRIMARY_DELAY=0.1
SECONDARY_DELAY=0.1

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whyareyoureadingthis'

next_message_id = 0
last_save = 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_messages')
def get_messages():
    message_history, last_message_id = get_message_history_and_last_message_id()
    
    start = request.args.get('last_id', '0')
    start_id = int(start) if start.isdigit() else 0

    msgs = [m for m in message_history if m['id'] > start_id]
    msgs = msgs[-MAX_MESSAGE_HISTORY:]

    current_last_id = message_history[-1]['id'] if message_history else 0

    return jsonify({
        'messages': msgs,
        'last_id': current_last_id
    })

stats_data = {}
files_data = {}

def get_files_and_stats_data2():
    global stats_data, files_data
    stats_data, files_data = get_files_and_stats_data()

@app.route('/get_stats')
def get_stats():
    get_files_and_stats_data2()
    update_stats()
    return jsonify(stats_data)

@app.route('/get_files')
def get_files():
    get_files_and_stats_data2()
    update_files()
    return jsonify(files_data)

@app.route('/send_message', methods=['POST'])
def send_message():
    global next_message_id
    
    data = request.get_json()
    msg = data.get('message')
    if not isinstance(msg, str):
        return jsonify({'error': 'Message must be a string'}), 400

    user_message = f"[U]: {msg}"
    add_vm_message(user_message)

    vm.input_queue.put(msg)

    vm.run_cycle()

    message_history, last_message_id = get_message_history_and_last_message_id()
    
    return jsonify({
        'messages': message_history[-10:],
        'stats': vm.get_stats(),
        'last_id': last_message_id
    })

@app.route('/vm_force_save')
def force_save():
    global last_save
    last_save = 0
    vm.save_state()
    return jsonify({"message": "State saved!"})

@app.route('/vm_action', methods=['POST'])
def handle_vm_action():
    data = request.get_json()
    if 'action' not in data:
        return jsonify({'error': 'Action not specified'}), 400
    
    action = data['action']
    
    try:
        if action == 'resetPC':
            vm.pc = 0
            message = "Program Counter reset to 0"
        elif action == 'restartVM':
            vm.pc = 0
            vm.running = True
            message = "VM restarted"
        elif action == 'resetAll':
            vm.pc = 0
            vm.variables = {}
            vm.memory = {}
            vm.code = EXAMPLE_CODE.copy()
            vm.stats = {
                'memory_access_count': {},
                'memory_modify_count': {},
                'program_runs': 0,
                'mutations_count': 0
            }
            vm.mutation_enabled = True

            for filename in [MEMORY_FILE, CODE_FILE, VM_STATE_FILE]:
                if os.path.exists(filename):
                    os.remove(filename)
            
            message = "Everything reset to default state"
        else:
            return jsonify({'error': 'Invalid action'}), 400

        add_vm_message(f"[H]: {message}")

        return jsonify({
            'success': True,
            'message': message
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500
    
def vm_runner():
    global last_save
    last_save = time.time()
    
    while True:
        try:
            while not vm.message_queue.empty():
                try:
                    raw = vm.message_queue.get_nowait()
                    add_vm_message(raw)
                except queue.Empty:
                    break

            vm.run_cycle()

            current_time = time.time()
            if current_time - last_save > 120:
                vm.save_state()
                last_save = current_time
            
            time.sleep(PRIMARY_DELAY)
            
        except Exception as e:
            print(f"VM Runner error: {e}")
            time.sleep(1)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    vm_thread = threading.Thread(target=vm_runner, daemon=True)
    vm_thread.start()
    
    app.run(host='0.0.0.0', port=6060, debug=False)