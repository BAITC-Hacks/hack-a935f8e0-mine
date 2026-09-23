"""Alternate entry point: python -m streamlit run app.py (inside this folder)."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("streamlit_app.py")), run_name="__main__")
