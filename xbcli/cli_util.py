# -*- encoding: utf-8 -*-
import os
import platform
import re
import shutil
import subprocess
import sys

import click
from click import testing
from flask import Flask

__all__ = [
    "app_cli_runner",
    "check_output",
    "click_echo",
    "click_exit",
    "conda_command",
    "conda_executable",
    "init_conda",
    "platform_uname",
    "run_command",
    "run_subprocess",
]


def platform_uname(entry_python: str) -> str:
    script = "\"import sys; print(f'{sys.version_info.major}{sys.version_info.minor}');\""
    result = check_output(conda_executable("python", "-c", script, entry_python=entry_python), echo=False)
    assert len(result) >= 1

    if sys.platform == "win32":
        return f"cp{result[0]}-win_{platform.machine().lower()}"
    elif sys.platform == "linux":
        return f"cpython-{result[0]}-{platform.machine().lower()}-linux"
    elif sys.platform == "darwin":
        return f"cpython-{result[0]}-darwin"
    else:
        raise Exception(f"platform not support: {platform.uname()}")


def click_echo(message: str, err: bool = False, fg: str | None = None):
    if err is True:
        click.echo(click.style(message, fg=fg or "red"))
    else:
        click.echo(click.style(message, fg=fg))


def click_exit(message: str, return_code: int = 1):
    click_echo(message, err=True)
    sys.exit(return_code)


def app_cli_runner(app: Flask, *args):
    with app.app_context():
        runner = app.test_cli_runner()
        result: testing.Result = runner.invoke(args=args)
        if result.stdout_bytes:
            print(result.stdout_bytes.decode("utf-8"))
        if result.stderr_bytes:
            print(result.stderr_bytes.decode("utf-8"))


def run_command(*args: str, echo: bool = True, executable: str | None = None) -> int:
    if executable is None:
        command = " ".join(args)
    else:
        command = f'{executable} {" ".join(args)}'

    if echo is True:
        print(">>>", command)
    return os.system(command)


def run_subprocess(
    *args: str,
    echo: bool = True,
    shell: bool = True,
    executable: str | None = None,
    detached: bool = False,
) -> int:
    if echo is True:
        if executable is None:
            print(">>>", *args)
        else:
            print(">>>", executable, *args)

    kwargs = dict()
    if sys.platform.startswith("win32"):
        kwargs.update(
            startupinfo=subprocess.STARTUPINFO(
                dwFlags=subprocess.CREATE_NEW_CONSOLE | subprocess.STARTF_USESHOWWINDOW,
                wShowWindow=subprocess.SW_HIDE,
            )
        )
        if detached is True:
            kwargs.update(creationflags=subprocess.DETACHED_PROCESS)
        else:
            kwargs.update(creationflags=subprocess.HIGH_PRIORITY_CLASS)
    else:
        raise Exception(f"platform not support: {sys.platform}")

    kwargs.update(
        shell=shell,
        executable=executable,
    )
    if detached is True:
        kwargs.update(
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        subprocess.Popen(" ".join(args), **kwargs)
        return 0
    else:
        kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        p = subprocess.Popen(" ".join(args), **kwargs)

        while True:
            output = p.stdout.readline()
            if not output and p.poll() is not None:
                break

            if isinstance(output, bytes) and len(output):
                print(output.decode("gbk"), end="")
            if isinstance(output, str) and len(output):
                print(output, end="")

        while True:
            output = p.stderr.readline()
            if not output and p.poll() is not None:
                break

            if isinstance(output, bytes) and len(output):
                print(output.decode("gbk"), end="")
            if isinstance(output, str) and len(output):
                print(output, end="")

        return p.poll()


def check_output(
    *args: str,
    cwd: str | None = None,
    executable: str = None,
    encoding: str = "utf-8",
    echo: bool = True,
    shell: bool = True,
) -> list[str]:
    if cwd is None:
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    previous_cwd = os.getcwd()
    os.chdir(cwd)
    if echo is True:
        print(">>>", " ".join(args).replace("\r\n", "\\n").replace("\n", "\\n"))
    result = subprocess.check_output(*args, executable=executable, shell=shell)
    os.chdir(previous_cwd)
    if isinstance(result, bytes):
        result = result.decode(encoding)
    if isinstance(result, str):
        if echo is True:
            print(result)
        return re.split("\r?\n", result)
    else:
        raise Exception(f"unsupported return type: {type(result)}")


def conda_executable(*args: str, entry_python: str) -> str:
    if len(args) == 0:
        raise Exception("command_args not specified")

    if sys.platform.startswith("win32"):
        result = check_output("where conda", echo=False)
    else:
        result = check_output("which conda", echo=False)

    if len(result) == 0 or len(result[0]) == 0:
        return click_exit("conda not found")

    conda_filename = result[0]

    result = check_output(f"{conda_filename} env list", echo=False)
    if not any((text.startswith(entry_python + " ") for text in result)):
        return click_exit(f"entry_python not found: {entry_python}")

    if sys.platform.startswith("win32"):
        if re.match("^(python[3]?$|python[3]? )", args[0]):
            return os.path.abspath(os.path.join(os.path.dirname(conda_filename), f"../envs/{entry_python}")) + os.sep + " ".join(args)
        else:
            return os.path.abspath(os.path.join(os.path.dirname(conda_filename), f"../envs/{entry_python}/Scripts")) + os.sep + " ".join(args)
    else:
        return os.path.abspath(os.path.join(os.path.dirname(conda_filename), f"../envs/{entry_python}/bin")) + os.sep + " ".join(args)


def conda_command(
    *args: str,
    entry_python: str,
    shell: bool = True,
    echo: bool = True,
    detached: bool = False,
    high_priority: bool = False,
) -> int:
    if echo is True:
        print(">>>", " ".join(args))

    command = conda_executable(*args, entry_python=entry_python)

    if detached is True:
        return run_subprocess(command, shell=shell, detached=True)
    elif high_priority is True:
        return run_subprocess(command, shell=shell)
    else:
        return run_command(command, echo=False)


def init_conda(entry_python: str, python_version: str, force: bool = False, requirements_txt: str | None = None) -> int:
    if sys.platform.startswith("win32"):
        result = check_output("where conda", echo=False)
    else:
        result = check_output("which conda", echo=False)

    if len(result) == 0 or len(result[0]) == 0:
        return click_exit("conda not found")

    conda_filename = result[0]

    result = check_output(f"{conda_filename} env list")
    print(f"\n{entry_python}")
    print("=" * 32)

    if any((text.startswith(entry_python + " ") for text in result)):
        if force is True:
            run_command(f"{conda_filename} remove -n {entry_python} --all -y")
            environment_path = os.path.abspath(os.path.join(os.path.dirname(conda_filename), f"../envs/{entry_python}"))
            if os.path.isdir(environment_path):
                shutil.rmtree(environment_path)
            return run_command(f"{conda_filename} create -q --name {entry_python} python={python_version} -y")
    else:
        return run_command(f"{conda_filename} create -q --name {entry_python} python={python_version} -y")

    if requirements_txt is not None:
        return conda_command(f'pip install --no-warn-script-location -r "{requirements_txt}"', entry_python=entry_python)
