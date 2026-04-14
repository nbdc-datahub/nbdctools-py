import builtins
import os
import sys

from .r_wrapper import create_dataset
from .exceptions import NBDCtoolsRError
from .pure_python import create_dataset_py, download_metadata, load_metadata


def _print_welcome_once() -> None:
	flag_name = "_nbdctools_import_message_printed"
	if getattr(builtins, flag_name, False):
		return

	def _supports_color() -> bool:
		if os.environ.get("NO_COLOR"):
			return False
		if os.environ.get("FORCE_COLOR"):
			return True
		if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
			return False
		term = os.environ.get("TERM", "")
		if term.lower() in {"", "dumb"}:
			return False
		return True

	if _supports_color():
		bold = "\033[1m"
		cyan = "\033[36m"
		green = "\033[32m"
		reset = "\033[0m"
		message = (
			f"Welcome to the {bold}{cyan}nbdctools{reset} package! "
			f"For more information, visit: {green}https://software.nbdc-datahub.org/nbdctools-py/{reset}\n"
			f"This package is developed by the ABCD {cyan}D{reset}ata {cyan}A{reset}nalysis, {cyan}I{reset}nformatics & "
			f"{cyan}R{reset}esource {cyan}C{reset}enter ({cyan}DAIRC{reset}) at the J. Craig Venter Institute (JCVI)"
		)
	else:
		message = (
			"Welcome to the nbdctools package! For more information, visit: "
			"https://software.nbdc-datahub.org/nbdctools-py/\n"
			"This package is developed by the ABCD Data Analysis, Informatics & "
			"Resource Center (DAIRC) at the J. Craig Venter Institute (JCVI)"
		)
	print(message)
	setattr(builtins, flag_name, True)


_print_welcome_once()

__all__ = [
	"NBDCtoolsRError",
	"create_dataset",
	"create_dataset_py",
	"download_metadata",
	"load_metadata",
]
