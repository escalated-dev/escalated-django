from escalated.conf import get_setting


def get_driver():
    """
    Return the appropriate driver instance based on the ESCALATED MODE setting.
    """
    mode = get_setting("MODE")
    if mode == "self_hosted":
        from escalated.drivers.local import LocalDriver
        return LocalDriver()
    elif mode == "synced":
        from escalated.drivers.synced import SyncedDriver
        return SyncedDriver()
    elif mode == "cloud":
        from escalated.drivers.cloud import CloudDriver
        return CloudDriver()
    else:
        raise ValueError(
            f"Invalid ESCALATED MODE: '{mode}'. "
            f"Must be one of: self_hosted, synced, cloud"
        )
