#!/usr/bin/env python3
# MIT
# fork from https://github.com/chvolkmann/code-connect

import argparse
import os
import subprocess as sp
import time
import subprocess
import sys
import socket
import json
from functools import partial
from pathlib import Path
from os.path import expanduser
from typing import Iterable, List, NoReturn, Sequence, Tuple

from sshconf import read_ssh_config  # type: ignore
from rcode.ipc import IPCClientSocket

# IPC sockets will be filtered based when they were last accessed
# This gives an upper bound in seconds to the timestamps
DEFAULT_MAX_IDLE_TIME: int = 4 * 60 * 60


def fail(*msgs, retcode: int = 1) -> NoReturn:
    """Prints messages to stdout and exits the script."""
    for msg in msgs:
        print(msg)
    exit(retcode)


def is_socket_open(path: Path, timeout: int = 2) -> bool:
    try:
        socket_path = path.resolve()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            return True
    except Exception:
        return False


def sort_by_access_timestamp(paths: Iterable[Path]) -> List[Tuple[float, Path]]:
    """Returns a list of tuples (last_accessed_ts, path) sorted by the former."""
    paths_list = [(p.stat().st_atime, p) for p in paths]
    paths_list = sorted(paths_list, reverse=True)
    return paths_list


def next_open_socket(socks: Sequence[Path], is_cursor=False) -> Path:
    """Iterates over the list and returns the first socket that is listening."""
    for sock in socks:
        if is_socket_open(sock) and get_process_using_socket(sock, is_cursor=is_cursor):
            return sock

    fail(
        "Could not find an open VS Code IPC socket.",
        "",
        "Please make sure to connect to this machine with a standard "
        "VS Code remote SSH session before using this tool.",
    )


def is_remote_vscode() -> bool:
    code_repos = Path.home().glob(".vscode-server/bin/*")
    return len(list(code_repos)) > 0 and os.getenv("SSH_CLIENT")


def is_remote_cursor() -> bool:
    code_repos = Path.home().glob(".cursor-server/*")
    return len(list(code_repos)) > 0 and os.getenv("SSH_CLIENT")


IS_REMOTE_VSCODE = is_remote_vscode() or is_remote_cursor()
IS_RSSH_CLIENT = os.environ.get("RSSH_SID") and os.environ.get("RSSH_SKEY")


def get_code_binary() -> Path:
    """Returns the path to the most recently accessed code executable."""

    # Every entry in ~/.vscode-server/bin corresponds to a commit id
    # Pick the most recent one
    code_repos = sort_by_access_timestamp(Path.home().glob(".vscode-server/bin/*"))
    if len(code_repos) == 0:
        fail(
            "No installation of VS Code Server detected!",
            "",
            "Please connect to this machine through a remote SSH session and try again.",
            "Afterwards there should exist a folder under ~/.vscode-server",
        )

    _, code_repo = code_repos[0]
    path = code_repo / "bin" / "code"
    if os.path.exists(path):
        return path
    return code_repo / "bin" / "remote-cli" / "code"


def get_cursor_binary() -> Path:
    """Returns the path to the most recently accessed code executable."""

    # Every entry in ~/.vscode-server/bin corresponds to a commit id
    # Pick the most recent one
    code_repos = sort_by_access_timestamp(
        Path.home().glob(".cursor-server/cli/servers/*/server/bin/remote-cli")
    )
    if len(code_repos) == 0:
        fail(
            "No installation of Cursor Server detected!",
            "",
            "Please connect to this machine through a remote SSH session and try again.",
            "Afterwards there should exist a folder under ~/.cursor-server/cli/servers",
        )
    _, cursor_executable = code_repos[0]
    return cursor_executable / "cursor"


def get_process_using_socket(socket_path, is_cursor=False):
    """
    Finds the process using the specified socket.

    Args:
        socket_path (str): The path to the socket file.
    """
    try:
        # Use lsof to find the process using the socket
        output = subprocess.check_output(
            ["lsof", "-t", socket_path], universal_newlines=True
        ).strip()
        if output:
            pid = int(output)
            # Get process details using /proc filesystem
            with open(f"/proc/{pid}/cmdline", "r") as f:
                cmdline = f.read().replace("\x00", " ").strip()
            if is_cursor:
                return cmdline.find("cursor-server") != -1
            else:
                return cmdline.find("vscode-server") != -1
    except subprocess.CalledProcessError:
        # lsof command failed, likely no process using the socket
        pass
    except FileNotFoundError:
        # /proc entries not found, process may have terminated
        pass
    return False


def get_ipc_socket(max_idle_time: int = DEFAULT_MAX_IDLE_TIME, is_cursor=False) -> Path:
    """Returns the path to the most recently accessed IPC socket."""

    # List all possible sockets for the current user
    # Some of these are obsolete and not actively listening anymore
    uid = os.getuid()
    socks = sort_by_access_timestamp(
        Path(f"/run/user/{uid}/").glob("vscode-ipc-*.sock")
    )
    # Only consider the ones that were active N seconds ago
    now = time.time()
    sock_list = [sock for ts, sock in socks if now - ts <= max_idle_time]

    # Find the first socket that is open, most recently accessed first
    return next_open_socket(sock_list, is_cursor=is_cursor)


def send_message(
    bin_name: str, dirname: str, sid: str, skey: str, new_window: bool = False
):
    ipc_sock = f"/tmp/rssh-ipc-{sid}.sock"

    try:
        sock = IPCClientSocket(socket.AF_UNIX)
        sock.connect(ipc_sock)

        payload = {
            "method": "open_ide",
            "params": {
                "sid": sid,
                "skey": skey,
                "bin": bin_name,
                "path": os.path.abspath(dirname),
                "is_file": os.path.isfile(dirname),
                "new_window": new_window,
            }
        }
        sock.write(payload)
        res = json.loads(sock.read()) or {}
        if res.get("code", -1) != 0:
            fail(res.get("message", "Unknown error"))

    finally:
        sock.close()


def run_remote(
    dir_name,
    max_idle_time: int = DEFAULT_MAX_IDLE_TIME,
    is_cursor: bool = False,
    new_window: bool = False,
) -> NoReturn:
    if not dir_name:
        raise Exception("need dir name here")

    if IS_RSSH_CLIENT:
        try:
            # communicate with rssh's IPC Socket
            sid = os.environ.get("RSSH_SID")
            skey = os.environ.get("RSSH_SKEY")
            bin_name = "cursor" if is_cursor else "code"
            send_message(bin_name, dir_name, sid, skey, new_window=new_window)
            return
        except Exception as e:
            print(f"Failed to connect to rssh's IPC socket: {e}\ntrying fallback to vscode's IPC socket")

    if IS_REMOTE_VSCODE:
        # communicate with vscode's IPC socket
        # Fetch the path of the "code" executable
        # and determine an active IPC socket to use
        code_binary = get_code_binary() if not is_cursor else get_cursor_binary()
        ipc_socket = get_ipc_socket(max_idle_time, is_cursor=is_cursor)
        args = [str(code_binary)]
        if new_window:
            args.append("--new-window")
        args.append(dir_name)
        os.environ["VSCODE_IPC_HOOK_CLI"] = str(ipc_socket)

        # run the "code" executable with the proper environment variable set
        # stdout/stderr remain connected to the current process
        proc = sp.run(args)
        # return the same exit code as the wrapped process
        exit(proc.returncode)


def run_loacl(
    dir_name,
    remote_name=None,
    is_latest=False,
    shortcut_name=None,
    open_shortcut_name=None,
    is_cursor=False,
    new_window=False,
):
    # run local to open remote
    bin_name = "code" if not is_cursor else "cursor"
    rcode_home = Path.home() / ".rcode"
    ssh_remote = "vscode-remote://ssh-remote+{remote_name}{remote_dir}"
    rcode_used_list = []
    is_win = sys.platform == "win32"
    if os.path.exists(rcode_home):
        with open(rcode_home) as f:
            rcode_used_list = list(filter(len, f.read().splitlines()))
    if is_latest:
        if rcode_used_list:
            ssh_remote_latest = rcode_used_list[-1].split(",")[-1].strip()
            args = [bin_name]
            if new_window:
                args.append("--new-window")
            args.extend(["--folder-uri", ssh_remote_latest])
            proc = sp.run(args, shell=is_win)
            exit(proc.returncode)
        else:
            print("Not use rcode before, just use it once")
            return
    if open_shortcut_name and rcode_used_list:
        for l in rcode_used_list:
            name, server = l.split(",")
            if open_shortcut_name.strip() == name.strip():
                args = [bin_name]
                if new_window:
                    args.append("--new-window")
                args.extend(["--folder-uri", server.strip()])
                proc = sp.run(args, shell=is_win)
                # then add it to the latest
                with open(rcode_home, "a") as f:
                    f.write(f"latest,{server}{str(os.linesep)}")
                exit(proc.returncode)
        else:
            raise Exception(f"no short_cut name in your added")

    sshs = read_ssh_config(expanduser("~/.ssh/config"))
    hosts = sshs.hosts()
    remote_name = remote_name
    if remote_name not in hosts:
        raise Exception("Please config your .ssh config to use this")
    dir_name = expanduser(dir_name)
    local_home_dir = expanduser("~")
    if dir_name.startswith(local_home_dir):
        user_name = sshs.host(remote_name).get("user", "root")
        # replace with the remote ~
        dir_name = str(dir_name).replace(local_home_dir, f"/home/{user_name}")
    ssh_remote = ssh_remote.format(remote_name=remote_name, remote_dir=dir_name)
    with open(rcode_home, "a") as f:
        if shortcut_name:
            f.write(f"{shortcut_name},{ssh_remote}{str(os.linesep)}")
        else:
            f.write(f"latest,{ssh_remote}{str(os.linesep)}")

    args = [bin_name]
    if new_window:
        args.append("--new-window")
    args.extend(["--folder-uri", ssh_remote])
    proc = sp.run(args, shell=is_win)
    exit(proc.returncode)


def main(is_cursor=False):
    parser = argparse.ArgumentParser(
        # %(prog)s <host> <dir>
        usage="""
        rcode <host> <dir>
        """,
        description="""
        just rcode \'file\' like your VSCode \'code\' .
        but you should config your ~/.ssh/config first
        """,
    )
    parser.add_argument("dir", help="dir_name", nargs="?")
    parser.add_argument("host", help="ssh hostname", nargs="?")
    parser.add_argument(
        "-l",
        "--latest",
        dest="is_latest",
        action="store_true",
        help="if is_latest",
    )
    parser.add_argument(
        "-sn",
        "--shortcut_name",
        dest="shortcut_name",
        help="add shortcut name to this",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-os",
        "--open_shortcut",
        dest="open_shortcut",
        help="if ",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-n",
        "--new-window",
        dest="new_window",
        action="store_true",
        help="force a new window",
    )
    options = parser.parse_args()
    if IS_RSSH_CLIENT or IS_REMOTE_VSCODE:
        run_remote(options.dir, is_cursor=is_cursor, new_window=options.new_window)
    else:
        run_loacl(
            options.host,
            options.dir,
            is_latest=options.is_latest,
            shortcut_name=options.shortcut_name,
            open_shortcut_name=options.open_shortcut,
            is_cursor=is_cursor,
            new_window=options.new_window,
        )


cmain = partial(main, is_cursor=True)

if __name__ == "__main__":
    main()
