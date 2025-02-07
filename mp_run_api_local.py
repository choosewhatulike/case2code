from api_call_util import LLMClient, save_jsonl, read_gen_data, read_jsonl, set_proxy, unset_proxy
import os
from threading import Thread, Lock
import json
from functools import partial
from tqdm import tqdm
from data_process import get_data_processor
import argparse

bar_format="{desc:<5.5}{percentage:3.0f}%|{bar:20}{r_bar}"

parser = argparse.ArgumentParser()

parser.add_argument('--data', type=str)
parser.add_argument('--model', type=str)
parser.add_argument('--task', type=str)
parser.add_argument('--use_chat', type=int, default=1)
parser.add_argument('--n_workers', type=int, default=64)
parser.add_argument('--temp', type=float, default=0.8)
parser.add_argument('--top_p', type=float, default=0.95)
parser.add_argument('--max_tokens', type=int, default=512)
parser.add_argument('--save_jsonl', type=int, default=1)
parser.add_argument('--stream', type=int, default=0)
parser.add_argument('--now', type=str, default='2024-10-01')
parser.add_argument('--debug', type=int, default=0)
parser.add_argument('--api_base', type=str)

args = parser.parse_args()

input_path = args.data
now = args.now
current_idx = 0
prompt_dir = ''
max_tokens=args.max_tokens
temperature = args.temp
top_p = args.top_p
model_name = args.model
prompt_name = args.task
output_path = f'./dataset/{now}/{prompt_name}/{model_name}-temp{temperature}-{os.path.basename(input_path)}'
n_workers = args.n_workers if not args.debug else 1
steam_flag = True if args.stream else False
client = LLMClient(api_key='EMPTY', base_url=args.api_base)

chatgpt_system_prompt = None

ps = get_data_processor(prompt_name)
ds = read_jsonl(input_path, stream=steam_flag)

def write_to_file(obj, output_path, lock):
    with lock:
        with open(output_path, 'a', encoding='utf-8') as fp:
            if args.save_jsonl:
                print(json.dumps(obj, ensure_ascii=False), file=fp)
            else:
                fp.write(json.dumps(obj, ensure_ascii=False, indent=2))

def api_worker(dataset, ps, progress_bar, lock, write_fn):
    global current_idx
    cur_task_done_retry = 0
    while True:
        if cur_task_done_retry <= 0:
            with lock:
                idx = current_idx
                current_idx += 1
                if isinstance(dataset, list):
                    if idx >= len(dataset):
                        obj = None
                    else:
                        obj = dataset[idx]
                else:
                    obj = next(dataset, None)
                if obj is None:
                    break
                obj = ps.prompt_item(obj)
                if obj['gen_answer_id'] in gened_keys:
                    progress_bar.update()
                    continue
        prompt = obj['prompt']
        if args.debug:
            print(prompt)
            return
        completion = ''
        num_gen_tokens = 0
        try:
            if args.use_chat:
                completion, num_gen_tokens = client.call_chat_completion(model_name, prompt, max_tokens=max_tokens, temperature=temperature, top_p=top_p, n=1, stop=None)
            else:
                completion, num_gen_tokens = client.call_completion(model_name, prompt, max_tokens=max_tokens, temperature=temperature, top_p=top_p, n=1, stop=ps.STOP_TRIGGER)
        except Exception as e:
            print(repr(e))
            if 'APIError' in repr(e):
                break
            cur_task_done_retry = 100
        assert isinstance(completion, str), type(completion)
        obj['completions'] = completion
        obj['num_gen_tokens'] = num_gen_tokens
        obj['task'] = prompt_name
        obj['data'] = input_path
        res = ps.check_result_v2(completion, obj)
        obj['check_result'] = res
        if not res:
            cur_task_done_retry += 1
            if cur_task_done_retry > 3:
                obj['retry_time'] = cur_task_done_retry
                write_fn(obj)
                print(f'failed for index {idx}')
                with lock:
                    progress_bar.update()
                cur_task_done_retry = 0
            continue
        else:
            obj['retry_time'] = cur_task_done_retry + 1
            cur_task_done_retry = 0
            obj = ps.post_process_item(obj)
            write_fn(obj)
            with lock:
                progress_bar.update()


threads = []
output_path = os.path.abspath(output_path)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
file_lock = Lock()
progress_lock = Lock()

gened_keys = set()
if args.save_jsonl:
    read_gen_fn = read_jsonl
else:
    read_gen_fn = read_gen_data
if os.path.exists(output_path):
    for ex in read_gen_fn(output_path, stream=True):
        if not ex['check_result']:
            continue
        if ex['gen_answer_id'] in gened_keys:
            print('dup', ex['gen_answer_id'])
        gened_keys.add(ex['gen_answer_id'])
print(f'input: {input_path}, output: {output_path}')
print(f'completed: {len(gened_keys)}, use_chat: {args.use_chat}, temp: {temperature}, top_p: {top_p}, max_tokens: {max_tokens}')
write_fn = partial(write_to_file, output_path=output_path, lock=file_lock)
progress_bar = tqdm(ds, total=1 if steam_flag else len(ds), bar_format=bar_format)

for i in range(n_workers):
    t = Thread(target=api_worker, args=(ds, ps, progress_bar, progress_lock, write_fn))
    threads.append(t)
    
for t in threads:
    t.start()

for t in threads:
    t.join()
    
print('Result at', output_path)
