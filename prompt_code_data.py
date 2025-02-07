import argparse
import json
from tqdm import tqdm
import os
import random
import copy
import ast
import astor
import re

instruction_templates = [
    'Write a function that generates the output from the input.',
    'Program to pass the given test cases.',
    'I have a function that takes input and returns output. Can you figure out the function?',
    'Given the Input/Output examples, figure out the function that generates the output from the input.',
    'First, I will give you some input/output examples of a function. Then, you need to reconstruct the function.',
    'I need you to write a program processing the input and generating the output.',
    'As a programmer, you need to write a function that passes the given examples.',
    'Please program a function, whose arguments are the following inputs, and the return value is the corresponding outputs.',
    "Can you develop a function that produces this output value from the given input values?",
    "Create a program that meets the provided test examples.",
    "I have input-output pairs for a function. Can you deduce the function?",
    "Based on these input/output examples, determine the function that creates the output.",
    "I'll provide some input/output test cases. Your task is to reconstruct the function.",
    "I need a function that takes this arguments and generates the corresponding returns.",
    "Write a function that satisfies the given examples.",
    "Please write a function to process the input arguments and produce the specified outputs.",
    "As a coder, write a function to match the provided examples.",
    "Can you program a function that, given the following inputs, returns the specified results?",
    "Figure out the function that transforms the input examples into the given output examples.",
    "Given these examples, write a function that produces the correct output results.",
    "Create a function that turns the provided input arguments into the expected return outputs.",
    "Write a program that handles the input and produces the required output.",
    "I need a function that matches these input/output pairs.",
    "Can you deduce the logic of a function from the given examples?",
    "Using these examples, create a function that returns the proper output.",
    "Develop a program that takes input and returns the corresponding output.",
    "Given these input-output pairs, write a function to generate the output.",
    "Please code a function that accepts the input and returns the specified output.",
]

header_templates = [
    'Example:\n',
    'Test case:\n',
    'Examples:\n\n',
    'Test cases:\n',
    'Example test cases:\n\n',
    'Some examples:\n',
    'Some test cases:\n',
    'Input/Output examples:\n',
    'Input/Output pairs:\n',
    'Input and output examples:\n\n',
    'Input and output pairs:\n',
    'Input-output examples:\n',
    'Input-output pairs:\n\n',
    'Pairs of input and output:\n',
    'A few examples:\n',
    'A few test cases:\n',
    'Several examples:\n\n',
    'Several test cases:\n',
    'Arguments and results:\n',
    'Some arguments and results:\n\n',
]

function_header_templates = [
    'Function: {function_name}',
    'The function:\n{function_name}',
    'Start with the function:\n{function_name}',
    'Based on the function name:\n{function_name}',
    'Function named {function_name}',
    'Funcion header is {function_name}',
    'Please begin with:\n{function_name}',
    'The function is:\n{function_name}',
]

new_lines = [
    '\n',
    '\n',
    '\n',
    '\n',
    '\n',
    '\n\n',
    '\n\n',
    '\n\n\n',
]

example_templates = [
    {'template': 'Input: {input}, Output: {output}', 'sep': '\n', 'style': 'raw'},
    {'template': 'Input example: {input}, Output example: {output}', 'sep': '\n', 'style': 'raw'},
    {'template': '# Input\n{input}\n# Output\n{output}', 'sep': '\n\n', 'style': 'raw'},
    {'template': 'arguments={input}\nreturn={output}', 'sep': '\n\n', 'style': 'raw'},
    {'template': 'args={input}\nreturn={output}', 'sep': '\n\n', 'style': 'raw'},
    {'template': '(args={input}, return={output})', 'sep': '\n', 'style': 'raw'},
    {'template': '({input}, {output})', 'sep': '\n', 'style': 'raw'},
    {'template': 'In: {input}, Out: {output})', 'sep': '\n', 'style': 'raw'},
    {'template': '>>> {input}\n<<< {output}', 'sep': '\n', 'style': 'call'},
    {'template': 'Call {input}, returns {output}', 'sep': '\n', 'style': 'call'},
    {'template': 'assert {input} == {output}', 'sep': '\n', 'style': 'call'},
    {'template': '>>> {input}\n{output}', 'sep': '\n', 'style': 'call'},
    {'template': '{input} -> {output}', 'sep': '\n', 'style': 'call'},
]

def find_next_matching_parentheses(s, start=0, left='(', right=')'):
    stack = []
    i = start
    while i < len(s):
        if s[i] == left:
            stack.append(i)
        elif s[i] == right:
            if stack:
                start_index = stack.pop()
                if start_index == start:
                    return (start_index, i)
        i += 1
    return None

class ExampleParser(ast.NodeVisitor):
    def __init__(self):
        self.examples = []
    
        
    def visit_Assign(self, node):
        print('Assign:', node)
        self.generic_visit(node)
        
def to_source(node):
    try:
        val = ast.literal_eval(astor.to_source(node).strip())
        if isinstance(val, str):
            return json.dumps(val)
        return repr(val)
    except ValueError:
        return astor.to_source(node).strip()
        
class ListExtractor(ast.NodeVisitor):
    def __init__(self):
        self.result = []
        self.in_list_flag = False

    def visit_Assign(self, node):
        if isinstance(node.value, ast.List) and not self.in_list_flag:
            if isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'examples':
                # print(ast.dump(node))
                self.in_list_flag = True
                self.visit(node.value)

    def visit_List(self, node):
        for item in node.elts:
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == 'dict':
                arg_list = []
                for kw in item.keywords:
                    key = kw.arg
                    value = to_source(kw.value)
                    arg_list.append((key, value))
                self.result.append(arg_list)
            elif isinstance(item, ast.Dict):
                arg_list = []
                for key, value in zip(item.keys, item.values):
                    arg_list.append((key.value, to_source(value)))
                self.result.append(arg_list)

def parse_examples(text: str):
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        print('Error syntax:', text)
        return None
    extractor = ListExtractor()
    extractor.visit(tree)
    return extractor.result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str)
    parser.add_argument('--output', type=str)
    parser.add_argument('--keep_raw', type=int, default=0)
    parser.add_argument('--for_eval', type=int, default=0)
    args = parser.parse_args()
    
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    with open(args.input, 'r', encoding='utf-8') as f, open(args.output, 'w', encoding='utf-8') as out_fh:
        for line in tqdm(f):
            d = json.loads(line)
            if args.for_eval:
                instruction = instruction_templates[0]
            else:
                instruction = random.choice(instruction_templates)
            if args.for_eval:
                example_header = ''
                func_header = function_header_templates[0].format(function_name=d['func_name'])
            else:
                if random.random() < 0.8:
                    example_header = random.choice(header_templates)
                else:
                    example_header = ''
                if random.random() < 0.8:
                    func_header = random.choice(function_header_templates).format(function_name=d['func_name'])
                else:
                    func_header = ''
            ori_prompt = d.pop('prompt')
            code = d['code']
            if args.for_eval:
                example_template = example_templates[0]
            else:
                example_template = random.choice(example_templates)
            min_samples = 3
            if len(d['example_inputs']) <= min_samples:
                num_samples = min_samples
            else:
                num_samples = random.randint(min_samples, len(d['example_inputs']))
            choose_sample_idx = []
            function_name = d['func_name']
            examples = parse_examples(d['example_str'])
            if examples is None or len(examples) == 0:
                # print('Error No examples:', d['example_str'])
                print('Error No examples')
                continue
            if len(examples) != len(d['example_outputs']):
                # print('Error num of examples:', d['example_str'])
                print('Error num of examples')
                continue
            total_index = list(range(len(examples)))
            random.shuffle(total_index)
            for i in total_index[:num_samples]:
                ex_in, ex_out = examples[i], d['example_outputs'][i]
                if example_template['style'] == 'call':
                    if random.random() < 0.5:
                        ex_in = ', '.join([f'{k}={v}' for k, v in ex_in])
                    else:
                        ex_in = ', '.join([f'{v}' for k, v in ex_in])
                    ex_in = f'{function_name}({ex_in})'
                elif example_template['style'] == 'raw':
                    rand_val = random.random() if not args.for_eval else 1
                    
                    if rand_val < 0.33:
                        ex_in = ', '.join([f'{k}:{v}' for k, v in ex_in])
                    elif rand_val < 0.66:
                        ex_in = ', '.join([f'{v}' for k, v in ex_in])
                    else:
                        ex_in = f'dict({", ".join([f"{k}={v}" for k, v in ex_in])})'
                else:
                    raise ValueError(f'Unknown style: {example_template["style"]}')

                if 'error' in ex_out:
                    # TODO: whether or not need repr()
                    ex_out = ex_out['error'].replace('<|EXCEPTION|>', '', 1).strip()
                else:
                    ex_out = ex_out['return']

                ex = example_template['template'].format(input=ex_in, output=ex_out)
                example_header += ex + example_template['sep']
                choose_sample_idx.append(i)
                
            if func_header:
                prompt_parts = [instruction, func_header, example_header]
            else:
                prompt_parts = [instruction, example_header]
            random.shuffle(prompt_parts)
            prompt = ''
            for p in prompt_parts:
                prompt += p + random.choice(new_lines)
                
            if len(prompt) > 4096 * 8:
                print('Prompt too long:', len(prompt))
                continue
            
            output = 'The function is:\n\n```python\n{code}\n```'.format(code=code)
            if args.keep_raw or args.for_eval:
                d['parsed_inputs'] = examples
                d['exec_code'] = code
                d['prompt'] = prompt
                d['output'] = output
                d['choosed_example_idx'] = choose_sample_idx
                d.pop('completions', None)
                out_fh.write(json.dumps(d) + '\n')
            else:
                o = {'id': d['gen_answer_id'], 'prompt': prompt, 'output': output}
                out_fh.write(json.dumps(o) + '\n')
        
if __name__ == '__main__':
    main()
    