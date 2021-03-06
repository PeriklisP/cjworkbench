import cjwkernel.kernel

kernel = None


def init_module_system():
    """Initialize the module system.

    This must be called during startup. It creates `kernel`, a subprocess
    spawner.
    """
    global kernel
    # Ignore spurious init() calls. They happen in unit-testing: each unit test
    # that relies on the module system needs to ensure it's initialized.
    if kernel is None:
        kernel = cjwkernel.kernel.Kernel()
