#!/usr/bin/env python3
"""Version a generated README image URL by its contents to refresh GitHub Camo."""

import hashlib
import re
import sys
from pathlib import Path


def main() -> None:
    asset = Path(sys.argv[1])
    version = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
    readme = Path("README.md")
    content = readme.read_text()
    url = f"https://raw.githubusercontent.com/TaewoooPark/TaewoooPark/main/{asset.as_posix()}"
    updated, count = re.subn(
        re.escape(url) + r'(?:\?v=[^"\s]*)?(?=")',
        f"{url}?v={version}",
        content,
    )
    if count != 1:
        raise ValueError(f"Expected one README image for {asset}, found {count}")
    if updated != content:
        readme.write_text(updated)
    print(f"{asset}: {version}")


if __name__ == "__main__":
    main()
