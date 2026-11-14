"""Run through Blender MCP. Rebuild explicitly from authored source modules."""
import sys
import importlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
for name in ('common','car','studio','character','action'):
    if name in sys.modules:importlib.reload(sys.modules[name])
from common import initialize
from car import build_car
from studio import build_studio,save_scene
from character import build_character
from action import build_action

initialize()
build_car()
build_studio()
fabric,glove=build_character()
build_action(fabric,glove)
save_scene('gem_detailing_v02.blend')
