"""The trainer's own tests (run by tools/test_addon.py trainer): who has trainer mode on."""
import os
import tempfile


def run(mod, check):
    mod.DB = os.path.join(tempfile.mkdtemp(), "trainer.db")
    check("nobody is on until switched", (mod.is_on("Mara"), mod.people_on()), (False, {}))
    mod.set_on("Mara", True, "Chief")
    check("switched on for Mara: on, whatever the case of her name", (mod.is_on("Mara"), mod.is_on("mara"), mod.is_on("Owen")),
          (True, True, False))
    check("who switched it is kept", mod.people_on()["Mara"]["by"], "Chief")
    mod.set_on("mara", False, "Mara")
    check("switched off by herself: off, one row for her", (mod.is_on("Mara"), len(mod.people_on())), (False, 1))
    check("its settings: chores first", mod.settings()["topics"], ["chores"])
    mod.DB = None
