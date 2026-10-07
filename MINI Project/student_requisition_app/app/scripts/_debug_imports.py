import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
print("APP_DIR:", APP_DIR)
print("sys.path[0:5]:", sys.path[:5])
sys.path.insert(0, str(APP_DIR))

import pdf_generator
import inspect
print("build_pdf signature:", inspect.signature(pdf_generator.build_pdf))
print("---build_pdf source---")
src = inspect.getsource(pdf_generator.build_pdf)
print(src[:2000])


