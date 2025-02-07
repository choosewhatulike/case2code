import os
import json
from tqdm import tqdm
from ast_utils import *
from exec_utils import *
import argparse
from multiprocessing import Pool, Process, Queue
import re
import sys


with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sandbox_prefix.py'), 'r') as f:
    code_template = f.read()

code_insert_pos = code_template.find('### FUNCTION & EX DEFINITION ###')

def run_worker(data, model_obj):    
    pred_code = unwrap_code(model_obj['completions'])
    if '<|NONSTOP|>' in pred_code:
        model_obj['is_correct'] = 'Error: nonstop'
        return model_obj
    func_name = data['func_name']
    code_to_run = code_template.replace('### FUNCTION & EX DEFINITION ###', pred_code + '\n\n' + data['example_str'])
    code_to_run = code_to_run.replace('target_function_XXX', func_name)
    r = execute_code_wrapped(code_to_run, f'exec_{os.getpid()}.py', 10, add_guard=False)
    model_obj['exec_raw_output'] = r['result']
    model_obj['exec_status'] = r['status']
    gold_exec_output = [ex['return'] if 'return' in ex else ex['error'] for ex in data['example_outputs']]
    model_obj['gold_exec_output'] = gold_exec_output
    output_str = re.findall(r'############ \<\|EXAMPLE OUTPUT START\|\> ############\n(.*?)############ \<\|EXAMPLE OUTPUT END\|\> ############', r['result'], re.DOTALL)
    if len(output_str) == 0:
        model_obj['is_correct'] = 'Error: no output'
        return model_obj
    output_str = output_str[0].strip()
    outputs = output_str.split('<|OUT|>')
    outputs = [output.strip() for output in outputs if output.strip()]
    processed_outputs = []
    for o in outputs:
        # error output
        if '<|EXCEPTION|>' in o:
            # processed_outputs.append({'error': o.replace('<|EXCEPTION|>', '', 1).strip()})
            processed_outputs.append(o.strip())
        else:
            res = o.split('<|RETURN|>')
            if len(res) != 2:
                raise ValueError(f'Invalid output: {output_str}')
            ret_val = res[1].strip()
            processed_outputs.append(ret_val)
            
    model_obj['processed_outputs'] = processed_outputs
    if len(processed_outputs) != len(gold_exec_output):
        model_obj['is_correct'] = 'Error: output length mismatch'
        return model_obj
    
    for r, g in zip(processed_outputs, gold_exec_output):
        if r == g:
            continue
        model_obj['is_correct'] = 'Error: output mismatch'
        return model_obj
    model_obj['is_correct'] = 'Correct'
    return model_obj

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str)
    parser.add_argument('--model_output', type=str)
    parser.add_argument('--output', type=str)
    parser.add_argument('--passk', type=int, default=1)
    parser.add_argument('--n_workers', type=int, default=6)
    
    args = parser.parse_args()
    
    args.output = os.path.abspath(args.output)
    args.model_output = os.path.abspath(args.model_output)
    args.data = os.path.abspath(args.data)
    
    os.makedirs(args.output, exist_ok=True)
    os.makedirs('./tmp_exec', exist_ok=True)
    os.chdir('./tmp_exec')
    
    score_path = os.path.join(args.output, os.path.basename(args.model_output))
    if os.path.exists(score_path):
        results = {}
        with open(score_path, 'r', encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                results[obj[0]['gen_answer_id']] = obj
    else:    
        data = {}
        with open(args.data, 'r', encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                data[obj['id']] = obj
                
        model_output = {}
        with open(args.model_output, 'r', encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                ex_id = obj['gen_answer_id']
                if ex_id in model_output:
                    model_output[ex_id].append(obj)
                else:
                    model_output[obj['gen_answer_id']] = [obj]
        
        pool = Pool(args.n_workers)
        results = {}
        for key in data:
            if key not in model_output:
                results[key] = [{'is_correct': 'Error: no model output'}] * args.passk
            else:
                for idx in range(args.passk):
                    if idx < len(model_output[key]):
                        r = pool.apply_async(run_worker, (data[key], model_output[key][idx]))
                        if key not in results:
                            results[key] = [r]
                        else:
                            results[key].append(r)
                    else:
                        results[key].append({'is_correct': 'Error: no model output'})

        for key in tqdm(results):
            r_list = results[key]
            new_r_list = []
            for r in r_list:
                if isinstance(r, dict):
                    new_r_list.append(r)
                else:
                    new_r_list.append(r.get())            
            results[key] = new_r_list
        
    pass_k = {i: 0 for i in range(args.passk)}
    for key in results:
        r_list = results[key]
        for idx in range(len(r_list)):
            if r_list[idx]['is_correct'] == 'Correct':
                for j in range(idx, len(r_list)):
                    pass_k[j] += 1
                break

    for k in pass_k:
        print(f'{args.model_output} Pass {k+1}: {pass_k[k]}/{len(results)}={round(pass_k[k] / len(results), 4)}')
        
    with open(os.path.join(args.output, os.path.basename(args.model_output)), 'w', encoding='utf-8') as f:
        for key in results:
            f.write(json.dumps(results[key]) + '\n')

if __name__ == '__main__':
    main()