# -*- encoding: utf-8 -*-
from ast import Return
import os
import re
import sys

import click
from flask import Flask

os.putenv("PYTHONUTF8", "1")

from xbcli import cli_util

app = Flask(__name__)

python_version_list = [
    "3.10",
    "3.11",
    "3.12",
]


@app.cli.command()
@click.pass_context
@click.option("-f", "--force", required=False, type=bool, default=False, is_flag=True)
@click.option("-m", "--message", required=False, type=str)
def build(ctx: click.Context, message: str, force: bool):
    work_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    os.chdir(work_path)

    print(f"xbcli: {work_path}")
    result = cli_util.check_output("git status --porcelain", cwd=work_path)
    if force is False and any((re.match("^\s*?M\s+", text) for text in result)):
        return cli_util.click_exit("Found modified file")
    if any((re.match("^\s*?\?\?\s+", text) for text in result)):
        return cli_util.click_exit("Found untrack file")
    if force is False and any((re.match("^\s*?D\s+", text) for text in result)):
        return cli_util.click_exit("Found deleted file")
    if force is False and any((len(text) for text in result)):
        return cli_util.click_exit("Not clean repository")

    result = cli_util.check_output("git tag --list", cwd=work_path, echo=False)
    release_list: list[tuple[int, ...]] = []
    for text in result:
        ret = re.findall(f"^v(\d+)\.(\d+)\.(\d+)$", text)
        if len(ret) == 1 and isinstance(ret[0], tuple) and len(ret[0]) == 3:
            release_list.append(tuple(int(v) for v in ret[0]))

    release_list.sort(key=lambda release: release)
    for major, minor, micro in release_list[-3:]:
        click.echo(f"v{major}.{minor}.{micro}")

    version_filename = os.path.abspath(os.path.join(work_path, "xbcli/__version__.py"))
    with open(version_filename, "r") as f:
        content = f.read()

    result = re.findall("^VERSION\\s*?=\\s*?\(\\s*?(\d+)\\s*?,\\s*?(\d+)\\s*?,\\s*?(\d+)\\s*?\)", content, flags=re.M | re.S)
    print(result)
    if len(result) == 1 and isinstance(result[0], tuple) and result[0][-1].isdigit():
        previous_version = result[0]
    else:
        return cli_util.click_exit("version not found")

    new_version_text = tuple([*previous_version[:-1], str(int(previous_version[-1]) + 1)])
    print("Found version: {:s}, new version: {:s}".format(".".join(previous_version), ".".join(new_version_text)))

    new_content = re.sub("^(VERSION\\s*?=\\s*?)\(.*?\)", "\\g<1>({:s})".format(", ".join(new_version_text)), content, flags=re.M)
    with open(version_filename, "w") as f:
        f.write(new_content)

    result = cli_util.check_output(f"git add {os.path.relpath(version_filename, work_path)}", cwd=work_path)

    if isinstance(message, str):
        new_message = "\n".join(
            [
                message,
                f'{"=" * 32}',
                "build {:s} from {:s}".format(".".join(new_version_text), ".".join(previous_version)),
            ]
        )
    else:
        new_message = "\n".join(
            [
                "build {:s} from {:s}".format(".".join(new_version_text), ".".join(previous_version)),
            ]
        )

    if force is True:
        result = cli_util.check_output(f"git add -u", cwd=work_path)
    result = cli_util.check_output('git commit -m "{:s}"'.format(".".join(new_version_text)), cwd=work_path)
    result = cli_util.check_output('git tag -a v{:s} -m "{:s}"'.format(".".join(new_version_text), new_message), cwd=work_path)

    cli_util.run_command("python setup.py upload")
