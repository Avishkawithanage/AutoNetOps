"""All CLI strings live here (read-only collection commands + restore helpers)."""

CONFIG_COMMANDS = {
    "running": "show running-config",
    "startup": "show startup-config",
}

STATE_COMMANDS = {
    "version": "show version",
    "interfaces": "show ip interface brief",
    "vlans": "show vlan brief",
    "routes": "show ip route",
}

SAVE_COMMAND = "write memory"
REPLACE_FILE = "autonetops_restore.cfg"
REPLACE_COMMAND = f"configure replace flash:{REPLACE_FILE} force"

# CLI error markers that mean "this is not a configuration"
CLI_ERROR_MARKERS = (
    "% Invalid input",
    "% Ambiguous command",
    "% Incomplete command",
    "% Authorization failed",
    "% Access denied",
    "% Unknown command",
    "% Bad passwords",
)

# Lines that must never be replayed when restoring in merge mode
RESTORE_SKIP_PREFIXES = (
    "building configuration",
    "current configuration",
    "using ",  # "Using 1234 out of 262144 bytes"
    "version ",
    "! last configuration change",
    "! nvram config last updated",
    "! no configuration change since",
)

# Commands that must not appear in a configuration being restored
DANGEROUS_PATTERNS = (
    "crypto key zeroize",
    "write erase",
    "erase startup-config",
    "erase nvram",
    "reload",
    "delete flash",
    "format ",
    "boot system",  # changing boot image is out of scope for a config restore
)
