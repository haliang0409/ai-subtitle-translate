import argparse
import os
import sys
from dotenv import load_dotenv
from translator import SubtitleTranslator

load_dotenv()

def main():
    # Get default batch size from env
    default_batch = int(os.getenv("BATCH_SIZE", "30"))
    
    parser = argparse.ArgumentParser(description="Translate subtitle files using OpenAI-compatible API.")
    parser.add_argument("input", nargs="?", help="Path to the input subtitle file (required unless --test or --gui is used)")
    parser.add_argument("-o", "--output", help="Path to the output subtitle file (optional)")
    parser.add_argument("-l", "--lang", help="Target language (default: taken from .env or Chinese)")
    parser.add_argument("-b", "--batch", type=int, default=default_batch, help=f"Batch size for translation (default: {default_batch})")
    parser.add_argument("--test", action="store_true", help="Test API connection and exit")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh, ignore previous progress")
    parser.add_argument("--context", action="store_true", help="Enable enhanced context mode for better coherence")
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode (PyQt6)")

    args = parser.parse_args()

    # GUI mode
    if args.gui or (not args.input and not args.test):
        try:
            from gui_pyqt import SubtitleTranslatorApp
            from PyQt6.QtWidgets import QApplication
            app = QApplication(sys.argv)
            window = SubtitleTranslatorApp()
            window.show()
            sys.exit(app.exec())
        except ImportError:
            print("PyQt6 is required for GUI mode. Install with: pip install PyQt6")
            return

    translator = SubtitleTranslator()

    if args.test:
        translator.check_connection()
        return

    if not args.input:
        parser.error("the following arguments are required: input")

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        return

    # Determine output file path if not provided
    if not args.output:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}_translated{ext}"
    
    if args.lang:
        translator.target_lang = args.lang
    
    print(f"Starting translation of '{args.input}' to {translator.target_lang}...")
    translator.translate(
        args.input, 
        args.output, 
        batch_size=args.batch, 
        resume=not args.no_resume,
        enhanced_context=args.context
    )


if __name__ == "__main__":
    main()

