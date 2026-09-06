"""
pytest bootstrap for KlipperACE.

The plugin lives in ``extras/`` and is installed on the printer as the Klipper
package ``klippy/extras/ace``. It uses relative imports, so it must be imported
as a package named ``ace``. ``load_ace_package`` does that without copying files.
"""
import sys
import pathlib

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from ace_sim import load_ace_package, AceSimulator, FakeSerial  # noqa: E402
from fake_reactor import FakeReactor  # noqa: E402


@pytest.fixture(scope="session")
def ace():
    """The plugin imported as the ``ace`` package (same name as on the printer)."""
    return load_ace_package()


@pytest.fixture
def reactor():
    return FakeReactor()


@pytest.fixture
def fake_serial(ace, monkeypatch):
    """
    Replace pyserial's Serial class with FakeSerial for the duration of a test.
    Returns a helper to register simulated ACE units by port path.
    """
    import serial as pyserial
    monkeypatch.setattr(pyserial, "Serial", FakeSerial)
    FakeSerial.simulators.clear()
    FakeSerial.instances.clear()

    def register(port="/dev/ttyACE0", **sim_kwargs):
        sim = AceSimulator(**sim_kwargs)
        FakeSerial.simulators[port] = sim
        return sim

    yield register
    FakeSerial.simulators.clear()
    FakeSerial.instances.clear()
