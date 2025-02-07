import requests
import msgpack
import os
import re
import json
import openai
import random
from openai.types import Completion
from openai.types.chat import ChatCompletion
from openai import RateLimitError

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
    stop_never
)  # for exponential backoff
 

def set_proxy(url):
    os.environ["http_proxy"] = url
    os.environ["https_proxy"] = url
    os.environ["HTTP_PROXY"] = url
    os.environ["HTTPS_PROXY"] = url

def unset_proxy():
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    

def read_gen_data(path, stream=False):
    if stream:
        return read_gen_data_stream(path)
    with open(path, 'r', encoding='utf-8') as fp:
        raw = fp.read().split('}{\n')
    data = []
    for s in raw:
        s = s.strip()
        if not s.startswith('{'):
            s = '{' + s
        if not s.endswith('}'):
            s = s + '}'
        ex = json.loads(s)
        data.append(ex)
    return data

def read_gen_data_stream(path):
    with open(path, 'r', encoding='utf-8') as fp:
        text = ''
        # import pdb; pdb.set_trace()
        for line in fp:
            line = line.strip()
            if line == '}{':
                text += '}'
                ex = json.loads(text)
                yield ex
                text = '{'
            else:
                text += line
        if text:
            ex = json.loads(text)
            yield ex

def read_json(path):
    with open(path, 'rb') as fp:
        return json.load(fp)
    
    
def read_jonl_stream(path):
    with open(path, 'rb') as fp:
        for line in fp:
            if line.strip():
                yield json.loads(line)
    return

def read_jsonl(path, stream=False):
    if stream:
        return read_jonl_stream(path)
    results = []
    with open(path, 'rb') as fp:
        for line in fp:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except Exception as e:
                    print(e, line)
                    continue
    return results

def get_output(res):
    out = res['message']['content']
    if res['finish_reason'] != 'stop':
        out += '<|NONSTOP|>'
    return out

def get_output_raw(res):
    out = res['text']
    if res['finish_reason'] != 'stop':
        out += '<|NONSTOP|>'
    return out

def save_jsonl(data, path):
    with open(path, 'w', encoding='utf-8') as fp:
        for ex in data:
            print(json.dumps(ex, ensure_ascii=False), file=fp)
       
       
class LLMClient:
    def __init__(self, api_key, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        if self.base_url:
            self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = openai.OpenAI(api_key=api_key)
            
            
    @staticmethod
    def get_completion_output(response: Completion):
        outputs = []
        for res in response.choices:
            out = res.text
            if res.finish_reason == 'length':
                out += '<|NONSTOP|>'
            outputs.append(out)
        return outputs, response.usage.completion_tokens

    @staticmethod
    def get_chat_output(response: ChatCompletion):
        outputs = []
        for res in response.choices:
            out = res.message.content
            if res.finish_reason == 'length':
                out += '<|NONSTOP|>'
            outputs.append(out)
        return outputs, response.usage.completion_tokens
        
    # @retry(retry=retry_if_exception_type(RateLimitError), wait=wait_random_exponential(min=5, max=60), stop=stop_never)
    def call_completion(self, model, prompt, max_tokens, temperature=0.7, top_p=0.95, n=1, stop=None, **kwargs):
        response = self.client.completions.create(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
            frequency_penalty=kwargs.get('frequency_penalty', 0),
        )
        outputs, num_gen_tokens = self.get_completion_output(response)
        if n == 1:
            return outputs[0], num_gen_tokens
        return outputs, num_gen_tokens
    
    
    # @retry(retry=retry_if_exception_type(RateLimitError), wait=wait_random_exponential(min=5, max=60), stop=stop_never)
    def call_chat_completion(self, model, messages, max_tokens, temperature=0.7, top_p=0.95, n=1, stop=None):
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
        )
        outputs, num_gen_tokens = self.get_chat_output(response)
        if n == 1:
            return outputs[0], num_gen_tokens
        return outputs, num_gen_tokens
    
class OpenAILLMClient:
    def __init__(self, api_key_path):
        self.api_key_path = api_key_path
        with open(api_key_path, 'r') as fp:
            api_keys = json.load(fp)
        self.api_keys = [key['apikey'] for key in api_keys if key['model_provider'] == 'openai']
        self.clients = []
        for api_key in self.api_keys:
            self.clients.append(openai.OpenAI(api_key=api_key))
        
    @retry(retry=retry_if_exception_type(RateLimitError), wait=wait_random_exponential(min=5, max=60), stop=stop_never)
    def call_chat_completion(self, model, messages, max_tokens, temperature=0.7, top_p=0.95, n=1, stop=None):
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        client = random.choice(self.clients)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
        )
        outputs, num_gen_tokens = LLMClient.get_chat_output(response)
        if n == 1:
            return outputs[0], num_gen_tokens[0]
        return outputs, num_gen_tokens
