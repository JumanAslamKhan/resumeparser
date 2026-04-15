from pathlib import Path
import runpy


if __name__ == "__main__":
    backend_app = Path(__file__).parent / "resume-parser-project" / "Backend" / "app.py"
    runpy.run_path(str(backend_app), run_name="__main__")
