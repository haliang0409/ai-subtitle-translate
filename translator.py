import os
import re
import json
import requests
import time
import pysubs2
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

class TranslationError(Exception):
    """Raised when translation fails after all retries."""
    pass


class SubtitleTranslator:
    """
    A subtitle translator supporting multiple formats (SRT, ASS, VTT, LRC, etc.)
    with optional enhanced context mode.
    """
    
    # Supported formats
    SUPPORTED_FORMATS = {'.srt', '.ass', '.ssa', '.vtt', '.sub', '.lrc'}
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.target_lang = os.getenv("TARGET_LANGUAGE", "Chinese")
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3  # seconds
        
        # Request interval to avoid rate limiting (seconds)
        self.request_interval = float(os.getenv("REQUEST_INTERVAL", "1.0"))
        
        # Default batch size
        self.default_batch_size = int(os.getenv("BATCH_SIZE", "30"))
        
        # Context window size for enhanced context mode
        self.context_window = int(os.getenv("CONTEXT_WINDOW", "5"))
        
        # Disable proxy for local API by default
        disable_proxy = os.getenv("DISABLE_PROXY", "true").lower() == "true"
        self.proxies = {"http": None, "https": None} if disable_proxy else None
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _call_api(self, messages, temperature=0.7):
        """Call the OpenAI-compatible API with retry logic."""
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    proxies=self.proxies
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    print(f"\n⚠️  Request failed (attempt {attempt}/{self.max_retries}): {e}")
                    print(f"   Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    print(f"\n❌ Request failed after {self.max_retries} attempts: {e}")
        
        raise TranslationError(f"API call failed after {self.max_retries} retries: {last_error}")

    def check_connection(self):
        """Test the API connection."""
        print(f"Testing connection to {self.base_url} with model {self.model}...")
        try:
            result = self._call_api([{"role": "user", "content": "Hello"}])
            content = result["choices"][0]["message"]["content"]
            print("✅ Connection successful!")
            print(f"Response: {content[:100]}...")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print("Tip: Check your API_KEY, BASE_URL settings in .env")
            return False

    def _get_system_prompt(self, enhanced_context=False):
        """Get the system prompt for translation."""
        base_prompt = (
            f"You are a professional translator specializing in movie and TV show subtitles. "
            f"Your task is to translate subtitles into {self.target_lang}. "
            f"Guidelines:\n"
            f"1. Maintain the original tone and context.\n"
            f"2. Keep the translation concise as it is for subtitles.\n"
            f"3. Return the translated text in the exact same numbered format as the input.\n"
            f"4. Do not include any extra explanations or notes.\n"
            f"5. Ensure the number of translated lines matches the number of input lines.\n"
            f"6. Maintain the '[BR]' tags in the translation if they appear; they represent line breaks."
        )
        
        if enhanced_context:
            base_prompt += (
                f"\n7. IMPORTANT: Some lines marked with [CONTEXT] are already translated - "
                f"use them to understand the conversation flow but do NOT include them in your output. "
                f"Only translate and output the lines marked with [TRANSLATE]."
            )
        
        return base_prompt

    def translate_batch(self, texts):
        """Translate a batch of texts (standard mode)."""
        if not texts:
            return []
        
        prompt_text = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
        
        try:
            result = self._call_api(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.3
            )
            
            return self._parse_numbered_response(result, len(texts))
        except TranslationError:
            raise
        except Exception as e:
            print(f"Error during translation: {e}")
            return texts

    def translate_batch_with_context(self, texts_to_translate, context_before=None, context_after=None):
        """
        Translate with enhanced context (滑动窗口模式).
        
        Args:
            texts_to_translate: List of texts to translate
            context_before: List of (original, translated) tuples for context before
            context_after: List of original texts for context after (not yet translated)
        """
        if not texts_to_translate:
            return []
        
        prompt_parts = []
        
        # Add context before (already translated)
        if context_before:
            prompt_parts.append("=== Previously translated (for context only, DO NOT output) ===")
            for orig, trans in context_before:
                prompt_parts.append(f"[CONTEXT] Original: {orig}")
                prompt_parts.append(f"[CONTEXT] Translated: {trans}")
            prompt_parts.append("")
        
        # Add texts to translate
        prompt_parts.append("=== Translate these lines (output numbered translations) ===")
        for i, text in enumerate(texts_to_translate):
            prompt_parts.append(f"[TRANSLATE] {i+1}. {text}")
        
        # Add context after (not yet translated)
        if context_after:
            prompt_parts.append("")
            prompt_parts.append("=== Upcoming lines (for context only, DO NOT output) ===")
            for text in context_after:
                prompt_parts.append(f"[CONTEXT] {text}")
        
        prompt_text = "\n".join(prompt_parts)
        
        try:
            result = self._call_api(
                messages=[
                    {"role": "system", "content": self._get_system_prompt(enhanced_context=True)},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.3
            )
            
            return self._parse_numbered_response(result, len(texts_to_translate))
        except TranslationError:
            raise
        except Exception as e:
            print(f"Error during translation: {e}")
            return texts_to_translate

    def _parse_numbered_response(self, result, expected_count):
        """Parse the numbered response from API."""
        translated_content = result["choices"][0]["message"]["content"].strip()
        lines = translated_content.split('\n')
        parsed_result = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip context markers if any leaked through
            if line.startswith('[CONTEXT]'):
                continue
            # Remove [TRANSLATE] marker if present
            line = line.replace('[TRANSLATE]', '').strip()
            # Remove the numbering (e.g., "1. " or "1.")
            parts = line.split('.', 1)
            if len(parts) > 1 and parts[0].strip().isdigit():
                parsed_result.append(parts[1].strip())
            elif line:
                parsed_result.append(line)
        
        if len(parsed_result) != expected_count:
            print(f"Warning: Expected {expected_count} lines, got {len(parsed_result)}.")
            return parsed_result[:expected_count] + [""] * (expected_count - len(parsed_result))
        
        return parsed_result

    def _load_subtitle(self, input_file):
        """Load subtitle file using pysubs2."""
        ext = os.path.splitext(input_file)[1].lower()
        
        if ext == '.lrc':
            return self._load_lrc(input_file)
        else:
            return pysubs2.load(input_file)

    def _save_subtitle(self, subs, output_file, input_file=None):
        """Save subtitle file."""
        ext = os.path.splitext(output_file)[1].lower()
        
        if ext == '.lrc':
            self._save_lrc(subs, output_file)
        else:
            subs.save(output_file)

    def _load_lrc(self, input_file):
        """Load LRC lyrics file."""
        subs = pysubs2.SSAFile()
        lrc_pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
        
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                match = lrc_pattern.match(line.strip())
                if match:
                    minutes, seconds, centiseconds, text = match.groups()
                    # Convert to milliseconds
                    start_ms = (int(minutes) * 60 + int(seconds)) * 1000 + int(centiseconds.ljust(3, '0')[:3])
                    if text.strip():
                        event = pysubs2.SSAEvent(start=start_ms, end=start_ms + 5000, text=text.strip())
                        subs.append(event)
        
        return subs

    def _save_lrc(self, subs, output_file):
        """Save as LRC lyrics file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            for event in subs:
                minutes = event.start // 60000
                seconds = (event.start % 60000) // 1000
                centiseconds = (event.start % 1000) // 10
                f.write(f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]{event.text}\n")

    def _get_progress_file(self, output_file):
        """Get the path to the progress file."""
        return output_file + ".progress"

    def _load_progress(self, output_file):
        """Load translation progress from file."""
        progress_file = self._get_progress_file(output_file)
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_progress(self, output_file, translated_index, subs):
        """Save current progress to file."""
        progress_file = self._get_progress_file(output_file)
        progress_data = {
            "translated_index": translated_index,
            "total": len(subs)
        }
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f)
        # Also save the partial translation
        self._save_subtitle(subs, output_file)

    def _clear_progress(self, output_file):
        """Remove the progress file after successful completion."""
        progress_file = self._get_progress_file(output_file)
        if os.path.exists(progress_file):
            os.remove(progress_file)

    def translate(self, input_file, output_file, batch_size=None, resume=True, enhanced_context=False):
        """
        Translate a subtitle file.
        
        Args:
            input_file: Path to the input subtitle file
            output_file: Path to save the translated subtitle file
            batch_size: Number of subtitles to translate in one API call
            resume: If True, resume from previous progress if available
            enhanced_context: If True, use sliding window context for better coherence
        """
        if batch_size is None:
            batch_size = self.default_batch_size
        
        # Validate format
        input_ext = os.path.splitext(input_file)[1].lower()
        if input_ext not in self.SUPPORTED_FORMATS:
            print(f"❌ Unsupported format: {input_ext}")
            print(f"   Supported formats: {', '.join(self.SUPPORTED_FORMATS)}")
            return False
        
        subs = self._load_subtitle(input_file)
        total = len(subs)
        start_index = 0
        
        # Store original texts and translations for context mode
        all_originals = [event.text.replace('\n', ' [BR] ') for event in subs]
        all_translations = [None] * total
        
        # Check for existing progress
        if resume:
            progress = self._load_progress(output_file)
            if progress and os.path.exists(output_file):
                start_index = progress.get("translated_index", 0)
                if start_index > 0 and start_index < total:
                    print(f"📂 Found previous progress: {start_index}/{total} subtitles translated.")
                    user_input = input("   Continue from where you left off? [Y/n]: ").strip().lower()
                    if user_input not in ('n', 'no'):
                        # Load the partially translated file
                        subs = self._load_subtitle(output_file)
                        # Rebuild translation list
                        for i in range(start_index):
                            all_translations[i] = subs[i].text.replace('\n', ' [BR] ')
                        print(f"   Resuming from subtitle {start_index + 1}...")
                    else:
                        start_index = 0
                        subs = self._load_subtitle(input_file)
                        print("   Starting from the beginning...")
                else:
                    start_index = 0
        
        mode_str = "enhanced context" if enhanced_context else "standard"
        print(f"📝 Translation mode: {mode_str}")
        
        try:
            with tqdm(total=total, initial=start_index, desc="Translating") as pbar:
                for i in range(start_index, total, batch_size):
                    batch_end = min(i + batch_size, total)
                    batch_texts = all_originals[i:batch_end]
                    
                    if enhanced_context:
                        # Get context before (already translated)
                        context_start = max(0, i - self.context_window)
                        context_before = []
                        for j in range(context_start, i):
                            if all_translations[j]:
                                context_before.append((all_originals[j], all_translations[j]))
                        
                        # Get context after (not yet translated)
                        context_end = min(total, batch_end + self.context_window)
                        context_after = all_originals[batch_end:context_end]
                        
                        translated_texts = self.translate_batch_with_context(
                            batch_texts, context_before, context_after
                        )
                    else:
                        translated_texts = self.translate_batch(batch_texts)
                    
                    # Update subtitles and translation cache
                    for j, translated_text in enumerate(translated_texts):
                        idx = i + j
                        if idx < total:
                            # Restore newlines
                            final_text = translated_text.replace(' [BR] ', '\n').replace('[BR]', '\n')
                            subs[idx].text = final_text
                            all_translations[idx] = translated_text
                    
                    # Save progress
                    current_index = batch_end
                    self._save_progress(output_file, current_index, subs)
                    
                    pbar.update(len(batch_texts))
                    
                    # Add delay between requests
                    if current_index < total and self.request_interval > 0:
                        time.sleep(self.request_interval)
            
            # Clear progress file on successful completion
            self._clear_progress(output_file)
            self._save_subtitle(subs, output_file)
            print(f"✅ Finished! Translated file saved to: {output_file}")
            return True
            
        except TranslationError as e:
            print(f"\n🛑 Translation aborted: {e}")
            print(f"   Progress saved: {i}/{total} subtitles translated.")
            print(f"   Run the same command again to resume.")
            return False
        except KeyboardInterrupt:
            self._save_progress(output_file, i, subs)
            print(f"\n\n⏸️  Translation interrupted by user.")
            print(f"   Progress saved: {i}/{total} subtitles translated.")
            print(f"   Run the same command again to resume.")
            return False


# Backwards compatibility alias
SRTTranslator = SubtitleTranslator
