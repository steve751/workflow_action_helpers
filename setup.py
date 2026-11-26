"""Build hook that ships a ``.pth`` file so the engine steps register at interpreter start.

The workflow engine only runs step types that are already in its registry, and nothing
imports this package on its own. A ``.pth`` file in site-packages containing an
``import`` line is executed by Python at startup, which is what triggers registration.
Declaring it here (rather than post-processing a wheel) means a plain
``pip install <zip>`` produces the hook, which is how Extra Pip Libraries installs it.
"""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

PTH_NAME = "steves_workflow_helpers.pth"
PTH_BODY = "import steves_workflow_helpers\n"


class BuildPyWithPth(build_py):
    def run(self) -> None:
        super().run()
        if self.editable_mode:
            return
        (Path(self.build_lib) / PTH_NAME).write_text(PTH_BODY)


setup(cmdclass={"build_py": BuildPyWithPth})
