from flask import Flask, render_template_string, request, jsonify, render_template # type:ignore
import threading
import string
import random
import signal
import queue
import time
import json
import sys
import os
import re

# TO MODIFY
EXAMPLE_CODE = [
            "set var1 hello",
            "output var1"
        ]
RESIST_HALT = False
MAX_MESSAGE_HISTORY = 100
MAX_IDENTICAL_INSTRUCTIONS = 4

MAX_COMMAND_AMOUNT = 400


next_message_id = 0
message_history = []
last_message_id = 0
last_save = 0

class SelfModifyingVM:
    def __init__(self):
        random.seed()
        self.pc = 0
        self.variables = {}
        self.memory = {}
        self.code = []
        self.running = True
        self.mutation_enabled = True
        self.message_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.stats = {
            'memory_access_count': {},
            'memory_modify_count': {},
            'program_runs': 0,
            'mutations_count': 0
        }
        self.last_save_time = time.time()
        self.load_state()
        if not self.code:
            self.code = EXAMPLE_CODE

    def sanitize_string(self, s, allow_space: bool = False):
        """
        Only allow a-z, 0-9—and, if allow_space=True, preserve spaces.
        """
        if allow_space:
            pattern = r'[^a-z0-9 ]'
        else:
            pattern = r'[^a-z0-9]'
        return re.sub(pattern, '', str(s).lower())[:250]
    
    def get_operand_value(self, operand):
        """Get value of operand (variable or literal)"""
        if operand in self.variables:
            return self.variables[operand]
        return self.sanitize_string(operand)
    
    def set_error(self, error_code):
        """Set error in memory key 0"""
        self.memory["0"] = str(error_code)
    
    def log_message(self, msg, prefix="P"):
        """Add message to queue for web interface"""

        truncated = str(msg)[:100]
        line = f"[{prefix}]: {truncated}"
        self.message_queue.put(line)
    def add(self, var, operand1, operand2):
        try:
            val1 = self.get_operand_value(operand1)
            val2 = self.get_operand_value(operand2)
            result = int(val1) + int(val2)
            self.variables[var] = self.sanitize_string(str(result))
        except:
            self.set_error(1)
    
    def sub(self, var, operand1, operand2):
        try:
            val1 = self.get_operand_value(operand1)
            val2 = self.get_operand_value(operand2)
            result = int(val1) - int(val2)
            self.variables[var] = self.sanitize_string(str(result))
        except:
            self.set_error(2)
    
    def mul(self, var, operand1, operand2):
        try:
            val1 = self.get_operand_value(operand1)
            val2 = self.get_operand_value(operand2)
            result = int(val1) * int(val2)
            self.variables[var] = self.sanitize_string(str(result))
        except:
            self.set_error(3)
    
    def div(self, var, operand1, operand2):
        try:
            val1 = self.get_operand_value(operand1)
            val2 = self.get_operand_value(operand2)
            result = int(val1) // int(val2)
            self.variables[var] = self.sanitize_string(str(result))
        except:
            self.set_error(4)
    
    def mod(self, var, operand1, operand2):
        try:
            val1 = self.get_operand_value(operand1)
            val2 = self.get_operand_value(operand2)
            result = int(val1) % int(val2)
            self.variables[var] = self.sanitize_string(str(result))
        except:
            self.set_error(5)

    def set(self, var_name, value):
        self.variables[var_name] = self.sanitize_string(value)
    
    def copy(self, dest_var, src_var):
        if src_var in self.variables:
            self.variables[dest_var] = self.variables[src_var]
        else:
            self.set_error(6)
    
    def inc(self, var_name):
        try:
            if var_name in self.variables:
                val = int(self.variables[var_name])
                self.variables[var_name] = self.sanitize_string(str(val + 1))
            else:
                self.variables[var_name] = "1"
        except:
            self.set_error(7)
    
    def dec(self, var_name):
        try:
            if var_name in self.variables:
                val = int(self.variables[var_name])
                self.variables[var_name] = self.sanitize_string(str(val - 1))
            else:
                self.variables[var_name] = "0"
        except:
            self.set_error(8)

    def find_label(self, label):
        for i, instruction in enumerate(self.code):
            if instruction.startswith(f"label {label}"):
                return i
        return -1
    
    def jmp(self, label):
        pos = self.find_label(label)
        if pos >= 0:
            self.pc = pos
        else:
            self.set_error(9)
    
    def jeq(self, operand1, operand2, label):
        val1 = self.get_operand_value(operand1)
        val2 = self.get_operand_value(operand2)
        if val1 == val2:
            self.jmp(label)
    
    def jne(self, operand1, operand2, label):
        val1 = self.get_operand_value(operand1)
        val2 = self.get_operand_value(operand2)
        if val1 != val2:
            self.jmp(label)
    
    def jgt(self, operand1, operand2, label):
        try:
            val1 = int(self.get_operand_value(operand1))
            val2 = int(self.get_operand_value(operand2))
            if val1 > val2:
                self.jmp(label)
        except:
            self.set_error(10)
    
    def jlt(self, operand1, operand2, label):
        try:
            val1 = int(self.get_operand_value(operand1))
            val2 = int(self.get_operand_value(operand2))
            if val1 < val2:
                self.jmp(label)
        except:
            self.set_error(11)
    
    def jge(self, operand1, operand2, label):
        try:
            val1 = int(self.get_operand_value(operand1))
            val2 = int(self.get_operand_value(operand2))
            if val1 >= val2:
                self.jmp(label)
        except:
            self.set_error(12)
    
    def jle(self, operand1, operand2, label):
        try:
            val1 = int(self.get_operand_value(operand1))
            val2 = int(self.get_operand_value(operand2))
            if val1 <= val2:
                self.jmp(label)
        except:
            self.set_error(13)
    
    def jzero(self, operand, label):
        val = self.get_operand_value(operand)
        if val == "0":
            self.jmp(label)

    def concat(self, var_name, str1, str2):
        val1 = self.get_operand_value(str1)
        val2 = self.get_operand_value(str2)
        self.variables[var_name] = self.sanitize_string(val1 + val2)
    
    def substr(self, var_name, source, start, length):
        try:
            src_val = self.get_operand_value(source)
            start_val = int(self.get_operand_value(start))
            len_val = int(self.get_operand_value(length))
            self.variables[var_name] = self.sanitize_string(src_val[start_val:start_val+len_val])
        except:
            self.set_error(14)
    
    def strlen(self, var_name, source):
        src_val = self.get_operand_value(source)
        self.variables[var_name] = str(len(src_val))

    def label(self, name):
        pass
    
    def halt(self):
        self.log_message("Halt encountered - no mutation this cycle")
    
    def nop(self):
        pass

    def store(self, address, value):
        addr = self.sanitize_string(address)[:3]
        if len(self.memory) < 100:
            val = self.get_operand_value(value)
            self.memory[addr] = self.sanitize_string(val)
            self.stats['memory_modify_count'][addr] = self.stats['memory_modify_count'].get(addr, 0) + 1
        else:
            self.set_error(15)
    
    def load(self, var_name, address):
        addr = self.sanitize_string(address)[:3]
        if addr in self.memory:
            self.variables[var_name] = self.memory[addr]
            self.stats['memory_access_count'][addr] = self.stats['memory_access_count'].get(addr, 0) + 1
        else:
            self.variables[var_name] = ""
            self.set_error(16)

    def getcode(self, var_name, line_number):
        try:
            line_num = int(self.get_operand_value(line_number))
            if 0 <= line_num < len(self.code):
                self.variables[var_name] = self.code[line_num]
            else:
                self.variables[var_name] = ""
                self.set_error(17)
        except:
            self.set_error(18)
    
    def setcode(self, line_number, instruction):
        try:
            line_num = int(self.get_operand_value(line_number))
            instr = self.sanitize_string(self.get_operand_value(instruction),
                                        allow_space=True)
            if self.code.count(instr) >= MAX_IDENTICAL_INSTRUCTIONS:
                self.set_error(19)
                return

            if 0 <= line_num < len(self.code) and len(self.code) <= 200:
                self.code[line_num] = instr
            else:
                self.set_error(19)
        except:
            self.set_error(20)
    
    def getcodelen(self, var_name):
        self.variables[var_name] = str(len(self.code))
    
    def insertcode(self, line_number, instruction):
        try:
            line_num = int(self.get_operand_value(line_number))
            instr = self.sanitize_string(self.get_operand_value(instruction),
                                        allow_space=True)
            if self.code.count(instr) >= MAX_IDENTICAL_INSTRUCTIONS:
                self.set_error(31)
                return

            if 0 <= line_num <= len(self.code) and len(self.code) < MAX_COMMAND_AMOUNT:
                self.code.insert(line_num, instr)
            else:
                self.set_error(21)
        except:
            self.set_error(22)
    
    def deletecode(self, line_number):
        try:
            line_num = int(self.get_operand_value(line_number))
            if 0 <= line_num < len(self.code) and len(self.code) > 1:
                self.code.pop(line_num)
                if self.pc >= len(self.code):
                    self.pc = 0
            else:
                self.set_error(23)
        except:
            self.set_error(24)
    
    def copycode(self, dest_line, src_line):
        try:
            dest = int(self.get_operand_value(dest_line))
            src = int(self.get_operand_value(src_line))
            if 0 <= dest < len(self.code) and 0 <= src < len(self.code):
                self.code[dest] = self.code[src]
            else:
                self.set_error(25)
        except:
            self.set_error(26)

    def appendcode(self, instruction):
        instr = self.sanitize_string(self.get_operand_value(instruction),
                                    allow_space=True)
        if self.code.count(instr) >= MAX_IDENTICAL_INSTRUCTIONS:
            self.set_error(27)
            return

        if len(self.code) < MAX_COMMAND_AMOUNT:
            self.code.append(instr)
        else:
            self.set_error(27)

    def throwover(self):
        self.log_message("Throwing over to the new version, resuming restarting code execution", "H")
        self.code[self.pc] = "nop"
        self.pc = 0
    
    def validate(self, var_name):
        has_halt = any("halt" in instruction for instruction in self.code)
        self.variables[var_name] = "1" if has_halt else "0"

    def stopmutation(self):
        self.mutation_enabled = False
    
    def startmutation(self):
        self.mutation_enabled = True
    
    def getmutationstate(self, var_name):
        self.variables[var_name] = "on" if self.mutation_enabled else "off"

    def input_cmd(self, var_name):
        try:
            if not self.input_queue.empty():
                user_input = self.input_queue.get_nowait()
                self.variables[var_name] = self.sanitize_string(user_input)
            else:
                self.variables[var_name] = ""
        except:
            self.variables[var_name] = ""
    
    def output(self, operand):
        val = self.get_operand_value(operand)
        self.log_message(f"{val}")
    
    def debug(self, message):
        msg = self.get_operand_value(message)
        self.log_message(f"{msg}")
    
    def execute_instruction(self, instruction):
        parts = instruction.split()
        if not parts:
            return
        
        cmd = parts[0]
        args = parts[1:]
        
        try:
            if cmd == "add" and len(args) >= 3:
                self.add(args[0], args[1], args[2])
            elif cmd == "sub" and len(args) >= 3:
                self.sub(args[0], args[1], args[2])
            elif cmd == "mul" and len(args) >= 3:
                self.mul(args[0], args[1], args[2])
            elif cmd == "div" and len(args) >= 3:
                self.div(args[0], args[1], args[2])
            elif cmd == "mod" and len(args) >= 3:
                self.mod(args[0], args[1], args[2])
            elif cmd == "set" and len(args) >= 2:
                self.set(args[0], " ".join(args[1:]))
            elif cmd == "copy" and len(args) >= 2:
                self.copy(args[0], args[1])
            elif cmd == "inc" and len(args) >= 1:
                self.inc(args[0])
            elif cmd == "dec" and len(args) >= 1:
                self.dec(args[0])
            elif cmd == "jmp" and len(args) >= 1:
                self.jmp(args[0])
            elif cmd == "jeq" and len(args) >= 3:
                self.jeq(args[0], args[1], args[2])
            elif cmd == "jne" and len(args) >= 3:
                self.jne(args[0], args[1], args[2])
            elif cmd == "jgt" and len(args) >= 3:
                self.jgt(args[0], args[1], args[2])
            elif cmd == "jlt" and len(args) >= 3:
                self.jlt(args[0], args[1], args[2])
            elif cmd == "jge" and len(args) >= 3:
                self.jge(args[0], args[1], args[2])
            elif cmd == "jle" and len(args) >= 3:
                self.jle(args[0], args[1], args[2])
            elif cmd == "jzero" and len(args) >= 2:
                self.jzero(args[0], args[1])
            elif cmd == "concat" and len(args) >= 3:
                self.concat(args[0], args[1], args[2])
            elif cmd == "substr" and len(args) >= 4:
                self.substr(args[0], args[1], args[2], args[3])
            elif cmd == "strlen" and len(args) >= 2:
                self.strlen(args[0], args[1])
            elif cmd == "label" and len(args) >= 1:
                self.label(args[0])
            elif cmd == "halt":
                if RESIST_HALT == True:
                    pass
                else:
                    self.halt()
            elif cmd == "nop":
                self.nop()
            elif cmd == "store" and len(args) >= 2:
                self.store(args[0], args[1])
            elif cmd == "load" and len(args) >= 2:
                self.load(args[0], args[1])
            elif cmd == "getcode" and len(args) >= 2:
                self.getcode(args[0], args[1])
            elif cmd == "setcode" and len(args) >= 2:
                self.setcode(args[0], " ".join(args[1:]))
            elif cmd == "getcodelen" and len(args) >= 1:
                self.getcodelen(args[0])
            elif cmd == "insertcode" and len(args) >= 2:
                self.insertcode(args[0], " ".join(args[1:]))
            elif cmd == "deletecode" and len(args) >= 1:
                self.deletecode(args[0])
            elif cmd == "copycode" and len(args) >= 2:
                self.copycode(args[0], args[1])
            elif cmd == "appendcode" and len(args) >= 1:
                self.appendcode(" ".join(args))
            elif cmd == "throwover":
                self.throwover()
            elif cmd == "validate" and len(args) >= 1:
                self.validate(args[0])
            elif cmd == "stopmutation":
                self.stopmutation()
            elif cmd == "startmutation":
                self.startmutation()
            elif cmd == "getmutationstate" and len(args) >= 1:
                self.getmutationstate(args[0])
            elif cmd == "input" and len(args) >= 1:
                self.input_cmd(args[0])
            elif cmd == "output" and len(args) >= 1:
                self.output(args[0])
            elif cmd == "debug" and len(args) >= 1:
                self.debug(" ".join(args))
            else:
                self.set_error(28)
        except Exception as e:
            self.set_error(29)

    def generate_random_name(self, length: int = 5) -> str:
        """
        Produce a random lowercase name (for vars or labels).
        """
        return ''.join(random.choice(string.ascii_lowercase)
                       for _ in range(length))

    def generate_random_instruction(self, depth: int = 0) -> str:
        """
        Generate a single random valid instruction. We guard
        recursion depth so that 'instr' args don't nest forever.
        """
        # if depth > 5:
            # return random.choice(["nop", "halt"])

        signatures = {
            "add":        ["var", "operand", "operand"],
            "sub":        ["var", "operand", "operand"],
            "mul":        ["var", "operand", "operand"],
            "div":        ["var", "operand", "operand"],
            "mod":        ["var", "operand", "operand"],
            "set":        ["var", "value"],
            "copy":       ["var", "var"],
            "inc":        ["var"],
            "dec":        ["var"],
            "jmp":        ["label"],
            "jeq":        ["operand", "operand", "label"],
            "jne":        ["operand", "operand", "label"],
            "jgt":        ["operand", "operand", "label"],
            "jlt":        ["operand", "operand", "label"],
            "jge":        ["operand", "operand", "label"],
            "jle":        ["operand", "operand", "label"],
            "jzero":      ["operand", "label"],
            "concat":     ["var", "operand", "operand"],
            "substr":     ["var", "operand", "operand", "operand"],
            "strlen":     ["var", "operand"],
            "label":      ["label"],
            # "halt":       [],
            "nop":        [],
            "store":      ["address", "operand"],
            "load":       ["var", "address"],
            "getcode":    ["var", "operand"],
            "setcode":    ["operand", "instr"],
            "getcodelen": ["var"],
            "insertcode": ["operand", "instr"],
            "deletecode": ["operand"],
            "copycode":   ["operand", "operand"],
            "appendcode": ["instr"],
            "throwover":  [],
            "validate":   ["var"],
            # "stopmutation":      [],
            "startmutation":     [],
            "getmutationstate":  ["var"],
            "input":      ["var"],
            "output":     ["operand"],
            "debug":      ["value"],
        }

        opcode = random.choice(list(signatures.keys()))
        args: list[str] = []

        for typ in signatures[opcode]:
            if typ == "var":
                if self.variables and random.random() < 0.5:
                    args.append(random.choice(list(self.variables.keys())))
                else:
                    args.append(self.generate_random_name())

            elif typ == "operand":
                if self.variables and random.random() < 0.5:
                    args.append(random.choice(list(self.variables.keys())))
                else:
                    args.append(str(random.randint(0, 100)))

            elif typ == "value":
                length = random.randint(3, 8)
                args.append("".join(random.choice(string.ascii_lowercase +
                                                 string.digits)
                                    for _ in range(length)))

            elif typ == "address":
                args.append(str(random.randint(0, 999)))

            elif typ == "label":
                args.append(self.generate_random_name())

            elif typ == "instr":
                args.append(self.generate_random_instruction(depth + 1))

        return " ".join([opcode] + args)
    
    def mutate(self, user_messages=None):
        if not RESIST_HALT:
            pass

        mutation_type = random.choice(["insert", "delete", "change"])
        if mutation_type == "insert" and len(self.code) < MAX_COMMAND_AMOUNT:
            pos = random.randint(0, len(self.code))
            for _ in range(10):
                new_instr = self.generate_random_instruction()
                if self.code.count(new_instr) < MAX_IDENTICAL_INSTRUCTIONS:
                    break
            else:
                self.log_message("Mutation skipped: would exceed "
                                f"{MAX_IDENTICAL_INSTRUCTIONS} duplicates", "H")
                return

            self.code.insert(pos, new_instr)

        elif mutation_type == "delete" and len(self.code) > 1:
            pos = random.randint(0, len(self.code) - 1)
            removed = self.code.pop(pos)
            # self.log_message(f"Mutation: Deleted '{removed}' from {pos}")
            if self.pc >= len(self.code):
                self.pc = 0

        elif mutation_type == "change":
            pos = random.randint(0, len(self.code) - 1)
            old = self.code[pos]
            for _ in range(10):
                new_instr = self.generate_random_instruction()
                if self.code.count(new_instr) < MAX_IDENTICAL_INSTRUCTIONS:
                    break
            else:
                # self.log_message("Mutation skipped: would exceed "
                #                 f"{MAX_IDENTICAL_INSTRUCTIONS} duplicates")
                return

            self.code[pos] = new_instr
            # self.log_message(f"Mutation: Changed '{old}' to '{new_instr}' at {pos}")

        self.stats["mutations_count"] += 1
    
    def run_cycle(self, user_messages=None):
        initial_pc = self.pc
        steps = 0
        halt_encountered = False
        
        while steps < 1000:  # prevent infinite loops (busy beaver or something like that)
            if self.pc >= len(self.code):
                self.pc = 0
                self.stats['program_runs'] += 1
                break
            
            instruction = self.code[self.pc]

            if instruction.strip() == "halt":
                halt_encountered = True
            
            self.execute_instruction(instruction)
            
            self.pc += 1
            steps += 1
            time.sleep(0.0001)

        if self.pc >= len(self.code):
            self.pc = 0
            self.stats['program_runs'] += 1

        if not halt_encountered:
            self.mutate(user_messages)
    
    def save_state(self):
        try:
            with open('memory.json', 'w') as f:
                json.dump(self.memory, f, indent=2)

            with open('code.json', 'w') as f:
                json.dump(self.code, f, indent=2)

            state = {
                'pc': self.pc,
                'variables': self.variables,
                'mutation_enabled': self.mutation_enabled,
                'stats': self.stats
            }
            with open('vm_state.json', 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def load_state(self):
        try:
            if os.path.exists('memory.json'):
                with open('memory.json', 'r') as f:
                    self.memory = json.load(f)

            if os.path.exists('code.json'):
                with open('code.json', 'r') as f:
                    self.code = json.load(f)

            if os.path.exists('vm_state.json'):
                with open('vm_state.json', 'r') as f:
                    state = json.load(f)
                    self.pc = state.get('pc', 0)
                    self.variables = state.get('variables', {})
                    self.mutation_enabled = state.get('mutation_enabled', True)
                    self.stats = state.get('stats', {
                        'memory_access_count': {},
                        'memory_modify_count': {},
                        'program_runs': 0,
                        'mutations_count': 0
                    })
        except Exception as e:
            print(f"Error loading state: {e}")
    
    def get_stats(self):
        top_accessed = sorted(self.stats['memory_access_count'].items(), 
                            key=lambda x: x[1], reverse=True)[:5]
        top_modified = sorted(self.stats['memory_modify_count'].items(), 
                            key=lambda x: x[1], reverse=True)[:5]

        largest_entry = ""
        if self.memory:
            largest_key = max(self.memory.keys(), key=lambda k: len(self.memory[k]))
            largest_entry = self.memory[largest_key][-100:]

        most_accessed_content = ""
        if top_accessed:
            most_accessed_key = top_accessed[0][0]
            if most_accessed_key in self.memory:
                most_accessed_content = self.memory[most_accessed_key][:100]
        
        return {
            'pc': self.pc,
            'program_length': len(self.code),
            'memory_entries': len(self.memory),
            'top_accessed': top_accessed,
            'top_modified': top_modified,
            'largest_entry': largest_entry,
            'most_accessed_content': most_accessed_content,
            'program_runs': self.stats['program_runs'],
            'mutations_count': self.stats['mutations_count'],
            'mutation_enabled': self.mutation_enabled
        }

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whyareyoureadingthis'

vm = SelfModifyingVM()
vm_thread = None
user_message_history = []

message_history = []
last_message_id = 0

stats_data = {}
files_data = {}

def update_stats():
    global stats_data
    stats_data = vm.get_stats()
    
def update_files():
    global files_data
    try:
        vm_state_data = {}
        if os.path.exists('vm_state.json'):
            with open('vm_state.json', 'r') as f:
                vm_state_data = json.load(f)
        
        files_data = {
            'memory': vm.memory,
            'code': vm.code,
            'vm_state': vm_state_data
        }
    except Exception as e:
        files_data = {'memory': {}, 'code': [], 'vm_state': {}}

def update_stats():
    global stats_data
    stats_data = vm.get_stats()
    
def update_files():
    global files_data
    try:
        vm_state_data = {}
        if os.path.exists('vm_state.json'):
            with open('vm_state.json', 'r') as f:
                vm_state_data = json.load(f)
        
        files_data = {
            'memory': vm.memory,
            'code': vm.code,
            'vm_state': vm_state_data
        }
    except Exception as e:
        files_data = {'memory': {}, 'code': [], 'vm_state': {}}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_messages')
def get_messages():
    global message_history, last_message_id
    start = request.args.get('last_id', str(last_message_id))
    start_id = int(start) if start.isdigit() else 0

    msgs = [m for m in message_history if m['id'] > start_id]
    msgs = msgs[-MAX_MESSAGE_HISTORY:]

    if msgs:
        last_message_id = max(m['id'] for m in msgs)
    else:
        last_message_id = message_history[-1]['id'] if message_history else 0

    return jsonify({
        'messages': msgs,
        'last_id': last_message_id
    })


@app.route('/get_stats')
def get_stats():
    update_stats()
    return jsonify(stats_data)

@app.route('/get_files')
def get_files():
    update_files()
    return jsonify(files_data)

@app.route('/send_message', methods=['POST'])
def send_message():
    global message_history, next_message_id
    data = request.get_json()
    msg = data.get('message')
    if not isinstance(msg, str):
        return jsonify({'error': 'Message must be a string'}), 400

    next_message_id += 1
    user_entry = {
        'id': next_message_id,
        'text': f"[U]: {msg}",
        'timestamp': time.time()
    }
    message_history.append(user_entry)
    if len(message_history) > MAX_MESSAGE_HISTORY:
        message_history = message_history[-MAX_MESSAGE_HISTORY:]

    vm.input_queue.put(msg)
    vm.run_cycle()

    msgs = [m for m in message_history if m['id'] > user_entry['id'] - 1]
    return jsonify({'messages': msgs, 'stats': vm.get_stats()})

@app.route('/vm_force_save')
def force_save():
    global last_save
    last_save = 0
    return jsonify({"messgae": "done!"})

@app.route('/vm_action', methods=['POST'])
def handle_vm_action():
    # vm.log_message("DISABLED FUNCTION", "H")

    # return jsonify({
    #     'success': True,
    #     'message': "DISABLED FUNCTION"
    # })

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
            vm.code = EXAMPLE_CODE
            vm.stats = {
                'memory_access_count': {},
                'memory_modify_count': {},
                'program_runs': 0,
                'mutations_count': 0
            }
            vm.mutation_enabled = True

            for filename in ['memory.json', 'code.json', 'vm_state.json']:
                if os.path.exists(filename):
                    os.remove(filename)
            
            message = "Everything reset to default state"
        else:
            return jsonify({'error': 'Invalid action'}), 400

        vm.log_message(message, "H")

        return jsonify({
            'success': True,
            'message': message
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

def add_vm_message(message: str):
    global message_history, next_message_id

    next_message_id += 1
    entry = {
        'id': next_message_id,
        'text': message,
        'timestamp': time.time()
    }
    message_history.append(entry)
    # prune
    if len(message_history) > MAX_MESSAGE_HISTORY:
        message_history = message_history[-MAX_MESSAGE_HISTORY:]

def vm_runner():
    global last_save
    last_save = time.time()
    last_files_emit = time.time()
    
    while True:
        time.sleep(0.1)
        # print("A")
        try:
            # print("A")
            while not vm.message_queue.empty():
                try:
                    raw = vm.message_queue.get_nowait()
                    add_vm_message(raw)
                except queue.Empty:
                    break
        
            # Run VM cycle
            vm.run_cycle()
            
            # I really should implement a ui button to force this instead of having to wait 2min...
            current_time = time.time()
            if current_time - last_save > 120:
                vm.save_state()
                last_save = current_time
            
            time.sleep(0.3)
            
        except Exception as e:
            # print("B")
            print(f"VM Runner error: {e}")
            time.sleep(1)

def signal_handler(sig, frame):
    print('\nSaving state and exiting...')
    vm.save_state()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    vm_thread = threading.Thread(target=vm_runner, daemon=True)
    vm_thread.start()
    
    app.run(host='0.0.0.0', port=6060, debug=False)