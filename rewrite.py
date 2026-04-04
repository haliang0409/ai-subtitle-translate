import os
import re

def rewrite():
    try:
        with open('translator.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. Imports
        imports = """import os
import re
import json
import requests
import time
import pysubs2
import hashlib
from dotenv import load_dotenv
from tqdm import tqdm
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False
"""
        content = re.sub(r'import os.*?from tqdm import tqdm', imports, content, flags=re.DOTALL)

        # 2. Init modifications
        init_orig = r'        if len\(self.api_configs\) > 1:.*?API configurations \(round-robin polling enabled\)"\)'
        init_repl = """        if len(self.api_configs) > 1:
            print(f"🔄 Loaded {len(self.api_configs)} API configurations")

        # New features
        import config
        cfg = config.load()
        self.refine_pass = cfg.get("refine_pass", False)
        self.max_length = int(cfg.get("max_length", 40))
        self.smart_break = cfg.get("smart_break", True)
        self.punct_localize = cfg.get("punct_localize", True)
        self.enable_cache = cfg.get("enable_cache", True)
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".translation_cache.json")
        self.cache = self._load_cache()
        self.total_tokens = 0
        self.total_cost = 0.0

    def _load_cache(self):
        if self.enable_cache and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        if self.enable_cache:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _get_cache_key(self, text, system_prompt):
        s = f"{self.target_lang}|{system_prompt}|{text}"
        return hashlib.md5(s.encode('utf-8')).hexdigest()

    def _count_tokens(self, text):
        if HAS_TIKTOKEN:
            try:
                enc = tiktoken.encoding_for_model(self.api_configs[0]["model"])
                return len(enc.encode(text))
            except:
                pass
        return len(text) // 2

    def _update_cost(self, prompt_tokens, completion_tokens):
        self.total_tokens += prompt_tokens + completion_tokens
        # Simple estimation: $0.15 per 1M input, $0.60 per 1M output (gpt-4o-mini limits)
        self.total_cost += (prompt_tokens / 1000000.0) * 0.15 + (completion_tokens / 1000000.0) * 0.60
"""
        content = re.sub(init_orig, init_repl, content, flags=re.DOTALL)

        # 3. Call API update for Cost tracking
        call_api_orig = r'                    return response.json\(\)'
        call_api_repl = """                    result = response.json()
                    usage = result.get("usage", {})
                    if usage:
                        self._update_cost(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
                    elif "messages" in data:
                        # Fallback counting
                        pt = sum(self._count_tokens(m["content"]) for m in data["messages"])
                        ct = self._count_tokens(result["choices"][0]["message"]["content"])
                        self._update_cost(pt, ct)
                    return result"""
        content = re.sub(call_api_orig, call_api_repl, content)

        with open('translator.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched basic structure.")
    except Exception as e:
        print("Error patching: ", e)

if __name__ == '__main__':
    rewrite()