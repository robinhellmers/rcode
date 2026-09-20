## Rcode

This repository is a fork of [yihong0618/rcode](https://github.com/yihong0618/rcode).

https://user-images.githubusercontent.com/1651790/172983742-b27a3fe0-2704-4fc8-b075-a6544783443a.mp4


## What changed

Compared with the upstream repository, this fork:

1. Opens remote files through RSSH with `--file-uri` while preserving `--folder-uri` for directories.
2. Supports `-n` and `--new-window` for RSSH, direct Remote SSH, and local URI launches.
3. Uses editable pipx installations from the cloned repository on the laptop and remote machine.

## Installation

Install `pipx` using your operating system's package manager. Run `pipx ensurepath`
if `~/.local/bin` is not already in your `PATH`, then start a new shell.

Clone this repository on both the laptop and each remote machine where you want
to use `rcode`. From each clone, run:

```bash
pipx install --editable . --force
hash -r
```

`--force` replaces an older pipx installation of `rcode`. The installation is
editable, so keep the cloned repository in place. Pulling and checking out code
in that clone updates the code used by the commands.

Verify the installation with:

```bash
command -v rcode
command -v rcursor
pipx runpip rcode show rcode
rcode --help
```

The commands should resolve from `~/.local/bin`, and `Editable project location`
should point to the clone.

If `rssh-ipc` was running on the laptop during the replacement, exit the current
remote shell, stop the old server, and reconnect so the new code and fresh
session credentials are used:

```bash
pgrep -ax rssh-ipc
kill <rssh-ipc-pid>
rssh your-remote-server
```

Do not kill an `ssh` process merely because its command line contains an
`rssh-ipc` socket path.

## INFO

1. just `rcode file` like your VSCode `code .`
2. or use cursor just `cursor .`
3. local open remote use rcode if you use `.ssh/config` --> `rcode remote_ssh ~/test`
4. local open latest remote `.ssh/config` --> `rcode -l or rcode --latest`
5. add shortcut_name `rcode s ~/abc -sn abc` then you can use `rcode -os abc` to open this dir quickly
6. support cursor to open remote dir command `rcursor ${ssh_name} ${ssh_dir}`
7. Connect to your SSH server with `rssh`, and you can run `rcode/rcursor` on the server to launch VS Code/Cursor, even if they are not running.

> Note: If using a traditional SSH connection, be sure to [connect to the remote host](https://code.visualstudio.com/docs/remote/ssh#_connect-to-a-remote-host) first before typing any `rcode` in the terminal.

## Remote Development with RSSH

RSSH enables seamless remote development by allowing you to launch VS Code/Cursor on your local machine while working with files on a remote server. It works by:

1. Creating a secure SSH tunnel between your local machine and remote server
2. Setting up IPC (Inter-Process Communication) sockets for command transmission
3. Managing remote sessions with unique identifiers and keys

https://github.com/user-attachments/assets/41a44915-4714-4fce-8705-a1550921b2f3

### Usage

1. Connect to remote server using `rssh`:

RSSH is designed to be fully compatible with SSH parameters, with the exception of the -R and -T options, which are not allowed when using RSSH.

```bash
rssh your-remote-server
```

All standard SSH parameters can be used with rssh, except -R and -T.

2. On the remote server, you can now use:
```bash
rcode .      # Launch VS Code
rcursor .    # Launch Cursor
```

### Using `ssh-wrapper`

If you'd like to use rssh as a drop-in replacement for ssh, you can utilize the provided ssh-wrapper. By adding an alias in your shell configuration file (e.g., ~/.bashrc or ~/.zshrc), you can override the ssh command:

```shell
alias ssh="ssh-wrapper"
```

With this alias in place, when you use ssh, it will invoke ssh-wrapper. To activate rssh, include the --rssh parameter:

```shell
ssh --rssh your-remote-server
```

If you do not include the --rssh parameter, it will behave as the default ssh command.

### How It Works

1. When you connect with `rssh`:
   - Generates a unique session ID and key
   - Creates an SSH tunnel for IPC communication
   - Sets up environment variables on the remote server

2. When running `rcode`/`rcursor` on the remote:
   - Communicates with the local IDE through the IPC socket
   - Automatically launches the appropriate IDE on your local machine
   - Opens the remote directory in your IDE

### Advanced Options

- Custom IPC host: `rssh --host <host> your-remote-server`
- Custom IPC port: `rssh --port <port> your-remote-server`

