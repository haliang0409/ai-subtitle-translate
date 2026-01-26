import os
import json
import pysrt
import requests
import time
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

class TranslationError(Exception):
    """Raised when translation fails after all retries."""
    pass

class SRTTranslator:
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
        
        # Disable proxy for local API by default (set to None)
        # If you need proxy, set DISABLE_PROXY=false in .env
        disable_proxy = os.getenv("DISABLE_PROXY", "true").lower() == "true"
        self.proxies = {"http": None, "https": None} if disable_proxy else None
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _call_api(self, messages, temperature=0.7):
        """
        Call the OpenAI-compatible API using requests with retry logic.
        """
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
        """
        Tests the API connection with a simple prompt.
        """
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

    def translate_text(self, texts):
        """
        Translates a list of strings using the OpenAI API.
        """
        if not texts:
            return []
        
        # Construct the prompt
        # We pass a numbered list to ensure the model returns the same number of lines and follows the order.
        prompt_text = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
        
        system_prompt = (
            f"You are a professional translator specializing in movie and TV show subtitles. "
            f"Your task is to translate the following subtitles into {self.target_lang}. "
            f"Guidelines:\n"
            f"1. Maintain the original tone and context.\n"
            f"2. Keep the translation concise as it is for subtitles.\n"
            f"3. Return the translated text in the exact same numbered format as the input.\n"
            f"4. Do not include any extra explanations or notes.\n"
            f"5. Ensure the number of translated lines matches the number of input lines.\n"
            f"6. Maintain the '[BR]' tags in the translation if they appear; they represent line breaks."
        )

        try:
            result = self._call_api(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.3
            )
            
            translated_content = result["choices"][0]["message"]["content"].strip()
            # Parse the numbered lines
            lines = translated_content.split('\n')
            parsed_result = []
            for line in lines:
                # Remove the numbering (e.g., "1. " or "1.")
                parts = line.split('.', 1)
                if len(parts) > 1:
                    parsed_result.append(parts[1].strip())
                else:
                    parsed_result.append(line.strip())
            
            # If the model failed to return the correct number of lines, fallback or handle error
            if len(parsed_result) != len(texts):
                print(f"Warning: Expected {len(texts)} lines, got {len(parsed_result)}.")
                return parsed_result[:len(texts)] + [""] * (len(texts) - len(parsed_result))
            
            return parsed_result
        except TranslationError:
            # Re-raise TranslationError to stop the entire process
            raise
        except Exception as e:
            print(f"Error during translation: {e}")
            return texts  # Fallback to original for non-critical errors

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
        subs.save(output_file, encoding='utf-8')

    def _clear_progress(self, output_file):
        """Remove the progress file after successful completion."""
        progress_file = self._get_progress_file(output_file)
        if os.path.exists(progress_file):
            os.remove(progress_file)

    def translate_srt(self, input_file, output_file, batch_size=10, resume=True):
        """
        Translate an SRT file.
        
        Args:
            input_file: Path to the input .srt file
            output_file: Path to save the translated .srt file
            batch_size: Number of subtitles to translate in one API call
            resume: If True, resume from previous progress if available
        """
        subs = pysrt.open(input_file)
        total = len(subs)
        start_index = 0
        
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
                        subs = pysrt.open(output_file)
                        print(f"   Resuming from subtitle {start_index + 1}...")
                    else:
                        start_index = 0
                        print("   Starting from the beginning...")
                else:
                    start_index = 0
        
        try:
            with tqdm(total=total, initial=start_index, desc="Translating") as pbar:
                for i in range(start_index, total, batch_size):
                    batch = subs[i:i + batch_size]
                    # Replace newlines with a placeholder to keep each subtitle on one line in the prompt
                    texts_to_translate = [sub.text.replace('\n', ' [BR] ') for sub in batch]
                    
                    translated_texts = self.translate_text(texts_to_translate)
                    
                    for j, translated_text in enumerate(translated_texts):
                        if j < len(batch):
                            # Restore newlines from placeholder
                            batch[j].text = translated_text.replace(' [BR] ', '\n').replace('[BR]', '\n')
                    
                    # Save progress after each batch
                    current_index = min(i + batch_size, total)
                    self._save_progress(output_file, current_index, subs)
                    
                    pbar.update(len(batch))
                    
                    # Add delay between requests to avoid rate limiting
                    if current_index < total and self.request_interval > 0:
                        time.sleep(self.request_interval)
            
            # Clear progress file on successful completion
            self._clear_progress(output_file)
            subs.save(output_file, encoding='utf-8')
            print(f"✅ Finished! Translated file saved to: {output_file}")
        except TranslationError as e:
            print(f"\n🛑 Translation aborted: {e}")
            print(f"   Progress saved: {i}/{total} subtitles translated.")
            print(f"   Run the same command again to resume.")
            return False
        except KeyboardInterrupt:
            # Save progress on Ctrl+C
            self._save_progress(output_file, i, subs)
            print(f"\n\n⏸️  Translation interrupted by user.")
            print(f"   Progress saved: {i}/{total} subtitles translated.")
            print(f"   Run the same command again to resume.")
            return False
        
        return True

if __name__ == "__main__":
    pass
