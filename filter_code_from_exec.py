import os
import json
from tqdm import tqdm
# from ast_utils import *
# from exec_utils import *
import argparse
from multiprocessing import Pool, Process, Queue
import re
import sys

DEBUG = False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str)
    parser.add_argument('--output', type=str)
    
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    total_tasks = 0
    valid_tasks = 0
    with open(args.input, 'r', encoding='utf-8') as f, open(args.output, 'w', encoding='utf-8') as out_fh:
        for line in tqdm(f):
            total_tasks += 1
            obj = json.loads(line)
            if not obj.get('exec_status', False):
                continue
            raw_output = obj['exec_raw_output']
            example_str = re.findall(r'############ \<\|EXAMPLE INPUR START\|\> ############\n(.*?)############ \<\|EXAMPLE INPUR END\|\> ############', raw_output, re.DOTALL)
            if len(example_str) == 0:
                continue
            example_str = example_str[0].strip()
            output_str = re.findall(r'############ \<\|EXAMPLE OUTPUT START\|\> ############\n(.*?)############ \<\|EXAMPLE OUTPUT END\|\> ############', raw_output, re.DOTALL)
            if len(output_str) == 0:
                continue
            output_str = output_str[0].strip()
            examples = example_str.split('<|EX|>')
            examples = [example.strip() for example in examples if example.strip()]
            outputs = output_str.split('<|OUT|>')
            outputs = [output.strip() for output in outputs if output.strip()]
            if DEBUG:
                import pdb; pdb.set_trace()
            if len(examples) <= 0 or len(examples) != len(outputs):
                continue
            count = 0
            processed_outputs = []
            try:
                for o in outputs:
                    # error output
                    if '<|EXCEPTION|>' in o:
                        count += 1
                        processed_outputs.append({'error': o.strip()})
                    else:
                        res = o.split('<|RETURN|>')
                        if len(res) != 2:
                            raise ValueError(f'Invalid output: {output_str}')
                        trace = res[0].replace('<|TRACE|>', '', 1).strip()
                        ret_val = res[1].strip()
                        # processed_outputs.append({'trace': trace, 'return': ret_val})
                        processed_outputs.append({'return': ret_val})
            except ValueError as e:
                print(e)
                continue
            if len(outputs) == count:
                continue
            # unique_outputs = list(set(outputs))
            # if len(unique_outputs) == 1:
            #     continue
            valid_tasks += 1
            # obj.pop('example_str', None)
            obj.pop('exec_code', None)
            obj.pop('exec_raw_output', None)
            obj['example_inputs'] = examples
            obj['example_outputs'] = processed_outputs
            out_fh.write(json.dumps(obj) + '\n')
            if DEBUG and total_tasks >= 100:
                break
    
    print(f'Total tasks: {total_tasks}, Valid tasks: {valid_tasks}, Keep Rate: {valid_tasks / total_tasks:.2f}')
    
if __name__ == '__main__':
    main()