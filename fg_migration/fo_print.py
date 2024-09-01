"""print functions"""

GLOBAL_ERROR_COUNT = 0


class Bcolors:
    """Color definitions for console output"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def message(color, msg, colorend=Bcolors.ENDC, bold=False) -> str:
    """Returns a message in color"""
    if bold:
        return Bcolors.BOLD + message(color, msg, colorend, False)

    return color + msg + colorend


def print_color(color, msg, colorend=Bcolors.ENDC, _bold=False) -> None:
    """Prints a message in color"""
    print(message(color, msg, colorend))


def info(msg) -> None:
    """Prints an info message"""
    print_color(Bcolors.OKBLUE, msg)


def success(msg) -> None:
    """Prints a success message"""
    print_color(Bcolors.OKGREEN, msg)


def warning(msg) -> None:
    """Prints a warning message"""
    print_color(Bcolors.WARNING, msg)


def error(msg) -> int:
    """Prints an error message and increments the global error count"""
    global GLOBAL_ERROR_COUNT  # pylint: disable=global-statement
    GLOBAL_ERROR_COUNT += 1
    print_color(Bcolors.FAIL, msg)
    return GLOBAL_ERROR_COUNT
