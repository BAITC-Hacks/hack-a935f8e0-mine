"""Game command center entry point: run inside astana_simulator.

The shared Streamlit UI keeps both supported launch commands identical;
calculation and validation remain in src/model.py."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("streamlit_app.py")), run_name="__main__")
