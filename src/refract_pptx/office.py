"""Optional isolated LibreOffice rendering; never controls an existing user session."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader


def render_pdf(
    source: str | Path, output: str | Path, *, executable: str | None = None, timeout: int = 120
) -> Path:
    source, target = Path(source).resolve(), Path(output).resolve()
    command = executable or shutil.which("libreoffice") or shutil.which("soffice")
    if not source.is_file():
        raise ValueError(f"presentation does not exist: {source}")
    if target.exists():
        raise ValueError(f"refusing to overwrite existing reference: {target}")
    if not command:
        raise ValueError(
            "LibreOffice was not found. Install it, pass --office-executable, "
            "or export a PDF manually from the target presentation editor."
        )
    if timeout <= 0:
        raise ValueError("render timeout must be positive")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / f".refract-render-{uuid4().hex}"
    temp.mkdir()
    try:
        subprocess.run(
            [
                command,
                f"-env:UserInstallation={(temp / 'profile').as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp),
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        result = temp / f"{source.stem}.pdf"
        if not result.is_file() or not len(PdfReader(result).pages):
            raise ValueError("Office conversion produced no readable PDF pages")
        # Exclusive creation prevents a concurrent render from overwriting another result.
        with target.open("xb") as destination, result.open("rb") as stream:
            shutil.copyfileobj(stream, destination)
        return target
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Office PDF conversion timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Office PDF conversion failed (exit {exc.returncode})") from exc
    finally:
        shutil.rmtree(temp)
