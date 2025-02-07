from typing import Dict, List
import re
import uuid
import random
import json
TRUCATED_FLAG = '<|NONSTOP|>'


class DataProcessorRegistry:
    def __init__(self):
        self.registry = {}

    def register(self, name, **kwargs):
        def decorator(cls):
            if kwargs:
                for key in kwargs:
                    if key not in ['n_shot']:
                        raise ValueError(f'invalid kwargs for dataprocess {key}')
            if name in self.registry:
                raise ValueError(f"Class '{name}' is already registered.")
            if hasattr(cls, 'check_result'):
                if hasattr(cls, 'check_result_with_item'):
                    raise ValueError(f"Class '{name}' has both 'check_result' and 'check_result_with_item' methods.")
            self.registry[name] = (cls, kwargs)
            return cls
        return decorator

    def create_instance(self, name):
        cls, kwargs = self.registry.get(name, (None, {}))
        if cls:
            n_shot = kwargs.pop('n_shot', None)
            if n_shot is not None:
                cls.N_SHOT = n_shot
            return cls
        else:
            raise ValueError(f"Class '{name}' is not registered.")
        

data_processor_registry = DataProcessorRegistry()


class DataProcessor:
    STOP_TRIGGER = None
    
    def prompt_item(self, item: Dict) -> Dict:
        raise NotImplementedError
        
    def get_prompt_ds(self, ds: List[Dict]) -> List[Dict]:
        result = []
        for idx, ex in enumerate(ds):
            result.append(self.prompt_item(ex))
        return result

    def get_prompted_ds(self, ds: List[Dict]):
        for ex in ds:
            item = self.prompt_item(ex)
            yield item
            
    def post_process_item(self, item: Dict) -> Dict:
        return item
    
    def check_result_v2(self, text: str, item: Dict) -> bool:
        if hasattr(self, 'check_result'):
            return self.check_result(text)
        elif hasattr(self, 'check_result_with_item'):
            return self.check_result_with_item(text, item)
        else:
            raise NotImplementedError
            
def get_data_processor(name: str) -> DataProcessor:
    return data_processor_registry.create_instance(name)()

#########################################################
#########################################################

    
def unwrap_code(text: str) -> str:
    """Unwrap a code block."""
    if "```python" in text:
        sidx = text.index("```python") + 10

        if "```" in text[sidx:]:
            eidx = text.index("```", sidx)
        else:
            eidx = len(text)
        return text[sidx:eidx].strip()
    else: 
        return text.strip()
    

@data_processor_registry.register('write_testcase')
class WriteTestCase(DataProcessor):
    PROMPT = """
Given the function, first analysis the types of the function arguments, then write 10 different example inputs for the function, each example should be a dict with function arguments' names and their values.
Output format:
```python
examples = [
    dict(argname=argvalue),
    ....
]
```

Function:
```python
def test_func(a: int, b: str) -> str:
    return str(a) + b
```
Examples:
```python
examples = [
    dict(a=1, b='a'),
    dict(a=2, b='b'),
    dict(a=3, b='c'),
    dict(a=4, b='d'),
    dict(a=5, b='e'),
    dict(a=6, b='f'),
    dict(a=7, b='g'),
    dict(a=8, b='h'),
    dict(a=9, b='i'),
    dict(a=10, b='j'),
]
```

Function:
```python
{code}
```
Examples:
"""
    
    def check_result(self, text: str) -> bool:
        return True
    
    def post_process_item(self, item: Dict) -> Dict:
        return item

    def prompt_item(self, item: Dict) -> Dict:
        ex_id = item['id']
        code = item['content']
        prompt = self.PROMPT.format(code=code)
        return {
            'prompt': prompt,
            'gen_answer_id': ex_id,
        }
        
    def check_result_v2(self, text: str, item: Dict) -> bool:
        testcases = unwrap_code(text)
        if len(testcases) == 0:
            return False
        return True
    
    def post_process_item(self, item: Dict) -> Dict:
        text = item['completions']
        testcases = unwrap_code(text)
        item['example_str'] = testcases
        return item


@data_processor_registry.register('write_testcase_zs')
class WriteTestCase_zs(DataProcessor):
    PROMPT = """
Given the function, first analysis the types of the function arguments, then write 10 different example inputs for the function, each example should be a dict with function arguments' names and their values.
Output format:
```python
examples = [
    dict(argname=argvalue),
    ....
]

Function:
```python
{code}
```
Examples:
"""
    
    def check_result(self, text: str) -> bool:
        return True
    
    def post_process_item(self, item: Dict) -> Dict:
        return item

    def prompt_item(self, item: Dict) -> Dict:
        ex_id = item['id']
        code = item['content']
        prompt = self.PROMPT.format(code=code)
        return {
            'prompt': prompt,
            'gen_answer_id': ex_id,
        }
        
    def check_result_v2(self, text: str, item: Dict) -> bool:
        testcases = unwrap_code(text)
        if len(testcases) == 0:
            return False
        return True
    
    def post_process_item(self, item: Dict) -> Dict:
        text = item['completions']
        testcases = unwrap_code(text)
        item['example_str'] = testcases
        return item

@data_processor_registry.register('trace2code_test_sft')
class WriteTestCase(DataProcessor):
    def prompt_item(self, item: Dict) -> Dict:
        ex_id = item['id']
        prompt = item['prompt']
        return {
            'prompt': prompt,
            'gen_answer_id': ex_id,
        }
        
    def check_result_v2(self, text: str, item: Dict) -> bool:
        testcases = unwrap_code(text)
        if len(testcases) == 0:
            return False
        return True

@data_processor_registry.register('trace2code_test_baseline')
class WriteTestCase_b(DataProcessor):
    meta_prompt = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"""
    PROMPT = "{prompt}\n\n\nPlease write the correct names of arguments. As the function you implement will be called by: {func_name}(**input_dict)."
    def prompt_item(self, item: Dict) -> Dict:
        ex_id = item['id']
        prompt = self.PROMPT.format(prompt=item['prompt'], func_name=item['func_name'])
        prompt = self.meta_prompt.format(prompt=prompt)
        return {
            'prompt': prompt,
            'gen_answer_id': ex_id,
        }
        
    def check_result_v2(self, text: str, item: Dict) -> bool:
        testcases = unwrap_code(text)
        if len(testcases) == 0:
            return False
        return True
    

    