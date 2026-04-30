import sys
import os

# ANSI color codes
_G  = "\033[92m"   # green
_C  = "\033[96m"   # cyan
_Y  = "\033[93m"   # yellow
_R  = "\033[91m"   # red
_B  = "\033[1m"    # bold
_RS = "\033[0m"    # reset

_USE_COLOR = sys.stdout.isatty()


def _c(code, text):
    return f"{code}{text}{_RS}" if _USE_COLOR else text


def header(title: str):
    bar = "=" * 60
    print(f"\n{_c(_B + _C, bar)}")
    print(_c(_B + _C, f"  {title}"))
    print(_c(_B + _C, bar))


def section(title: str):
    print(f"\n{_c(_B + _G, '--- ' + title + ' ---')}")


def info(msg: str):
    print(f"  {_c(_C, '>')} {msg}")


def success(msg: str):
    print(f"  {_c(_G, '[OK]')} {msg}")


def warn(msg: str):
    print(f"  {_c(_Y, '[WARN]')} {msg}", file=sys.stderr)


def error(msg: str):
    print(f"  {_c(_R, '[ERROR]')} {msg}", file=sys.stderr)


def choose_airfoil() -> str:
    """Prompt user to select one of the three supported airfoils."""
    airfoils = ["NACA 0012", "NACA 2412", "NACA 4412"]
    section("Select Airfoil")
    for i, a in enumerate(airfoils, 1):
        print(f"    {_c(_Y, str(i))}) {a}")
    while True:
        raw = input(f"  {_c(_C, 'Choice [1-3]')}: ").strip()
        if raw in ("1", "2", "3"):
            chosen = airfoils[int(raw) - 1].replace(" ", "").lower()
            success(f"Selected {airfoils[int(raw) - 1]}")
            return chosen
        warn("Enter 1, 2, or 3.")


def ask_float(prompt: str, default: float | None = None) -> float:
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {_c(_C, prompt + hint)}: ").strip()
        if raw == "" and default is not None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            warn("Please enter a valid number.")


def ask_int(prompt: str, default: int | None = None) -> int:
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {_c(_C, prompt + hint)}: ").strip()
        if raw == "" and default is not None:
            return int(default)
        try:
            return int(raw)
        except ValueError:
            warn("Please enter a valid integer.")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"  {_c(_C, prompt + ' ' + hint)}: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Enter y or n.")


def print_table(headers: list[str], rows: list[list], col_width: int = 12):
    """Print a simple aligned table."""
    fmt = "".join(f"{{:<{col_width}}}" for _ in headers)
    sep = "-" * (col_width * len(headers))
    print(f"\n  {_c(_B + _C, fmt.format(*headers))}")
    print(f"  {sep}")
    for row in rows:
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
        print(f"  {fmt.format(*cells)}")
    print()
