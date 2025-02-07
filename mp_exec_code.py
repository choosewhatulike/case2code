import os
import json
from tqdm import tqdm
from ast_utils import *
from exec_utils import *
import argparse
from multiprocessing import Pool, Process, Queue
import re
import sys

DEBUG = False

json_encoder = MultiDimensionalArrayEncoder(ensure_ascii=False)

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sandbox_prefix.py'), 'r') as f:
    code_template = f.read()

code_insert_pos = code_template.find('### FUNCTION & EX DEFINITION ###')


def process_code(ex, timeout=1):
    if 'example_str' not in ex:
        return {'gen_answer_id': ex['gen_answer_id'], 'error': 'No example_str'}
    prompt = ex['prompt']
    prompt = prompt.replace("Given the function, first analysis the types of the function arguments, then write 10 different example inputs for the function, each example should be a dict with function arguments' names and their values.\nOutput format:\n```python\nexamples = [\n    dict(argname=argvalue),\n    ....\n]", '')
    code = re.findall(r'```python\n(.*?)```', prompt, re.DOTALL)[-1]
    node = source_to_ast(code)
    # print(code)
    try:
        for n in ast.iter_child_nodes(node):
            if isinstance(n, ast.FunctionDef):
                break
    except Exception as e:
        print(ex['gen_answer_id'], f'{type(e)}: {str(e)}')
        return {'gen_answer_id': ex['gen_answer_id'], 'error': f'{type(e)}: {str(e)}'}
    func_ast = FunctionAst(n)
    func_name = func_ast.name
    
    code_to_run = code_template.replace('### FUNCTION & EX DEFINITION ###', code + '\n\n' + ex['example_str'])
    code_to_run = code_to_run.replace('target_function_XXX', func_name)
    
    r = execute_code_wrapped(code_to_run, f'tmp_exec/exe_{os.getpid()}.py', timeout + 20, add_guard=False)
    ex['code'] = code
    ex['func_name'] = func_name
    # ex['examples'] = examples
    # ex['code_to_run'] = code_to_run
    ex['exec_raw_output'] = r['result']
    ex['exec_status'] = r['status']
    return ex

def worker(in_queue, out_queue, timeout):
    while True:
        ex = in_queue.get()
        if ex is None:
            break
        ex = process_code(ex, timeout)
        out_queue.put(ex)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, default='dataset/raw_code')
    parser.add_argument('--output', type=str, default='dataset/raw_code/simple_code.jsonl')
    parser.add_argument('--timeout', type=int, default=1)
    parser.add_argument('--n_workers', type=int, default=4)
    
    args = parser.parse_args()
    
    os.makedirs('tmp_exec', exist_ok=True)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    procs = []
    in_queue = Queue()
    out_queue = Queue()
    if DEBUG:
        args.n_workers = 1
    for i in range(args.n_workers):
        p = Process(target=worker, args=(in_queue, out_queue, args.timeout))
        p.start()
        procs.append(p)
        
    num_tasks = 0
    seen_tasks = set()
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                seen_tasks.add(obj['gen_answer_id'])
     
    total_tasks = 0           
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            ex = json.loads(line)
            total_tasks += 1
            if ex['gen_answer_id'] in seen_tasks:
                continue
            in_queue.put(ex)
            num_tasks += 1
            if DEBUG and num_tasks > 10:
                break
        for i in range(args.n_workers):
            in_queue.put(None)
    print(f'Total tasks: {total_tasks}, Seen tasks: {len(seen_tasks)}, New tasks: {num_tasks}')

    bar = tqdm(total=num_tasks, file=sys.stdout)
    with open(args.output, 'a', encoding='utf-8') as f:
        while num_tasks > 0:
            ex = out_queue.get()
            if ex is not None:
                try:
                    f.write(json_encoder.encode(ex)+ '\n')
                except:
                    print(ex['gen_answer_id'])
            num_tasks -= 1
            bar.update(1)
    bar.close()
    
    for p in procs:
        p.join()
    
if __name__ == '__main__':
    main()
