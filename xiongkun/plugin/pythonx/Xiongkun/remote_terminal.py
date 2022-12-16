"""  This file is plugin for remote terminal control:

     Terminal: open a new terminal in remote shell. [build environment]
     Sendfile: send file into remote shell.
"""

import vim
import sys
import os
import os.path as osp
from .func_register import *
from .vim_utils import *
from collections import OrderedDict

def send_keys(bufnr, keys):
    vim.eval(f"term_sendkeys({bufnr}, \"{keys}\")")

def LoadConfig(config_path="./.vim_clangd.py"): 
    pwd = GetPwd()
    path = os.path.join(pwd, config_path)
    if os.path.isfile(path): 
        config = absolute_import("vim_clangd", path)
        if hasattr(config, "wd"): 
            pwd = config.wd
    else: 
        raise RuntimeError(f"Not found {config_path} in your project directory.")
    setattr(config, "wd", pwd)
    return config

def TerminalStart(ssh_url, ssh_passwd, docker_cmd, work_dir=None):
    """ provide keys with: 
    """
    print (f"Connect to {ssh_url} , {docker_cmd}, {work_dir}")
    if not work_dir: 
        work_dir = GetPwd()
    vim.command("tabe")
    vim.command("terminal")
    #vim.command("file ssh")
    vim.command("wincmd o")
    bufnr = vim.eval("bufnr()")
    send_keys(bufnr, f"ssh {ssh_url}\n")
    import time
    time.sleep(1)
    send_keys(bufnr, f"{ssh_passwd}\r\n")
    time.sleep(0.4)
    send_keys(bufnr, f"\r\n")
    time.sleep(0.4)
    send_keys(bufnr, f"{docker_cmd}\r\n")
    time.sleep(0.4)
    send_keys(bufnr, f"cd {work_dir}\r\n")
    return bufnr

@vim_register(command="Bash", with_args=True)
def BashStart(args=[]):
    if len(args) == 1: 
        config_file = "/home/data/.vim_clangd.py"
        from easydict import EasyDict as edict
        configs = LoadConfig(config_file)
        if (args[0] == 'ls'): 
            print("tf | torch | paddle | profile | wzf | cvpods")
            return
        else: 
            config = edict(getattr(configs, args[0]))
            config.wd = GetPwd()
    else: 
        config = LoadConfig()
    TerminalStart(config.ssh_url, config.ssh_passwd, config.docker_cmd, config.wd)


@vim_register(command="BashHelp", with_args=True)
def TerminalHelper(args):
    print ("Keymap: ")
    print ("  <F1>  -> helper page")
    print ("  <M-a> -> start a abbreviate")
    print ("  <M-c> -> exit the terminal")
    print ("  <M-h> -> switch tabpage: previous")
    print ("  <M-l> -> switch tabpage: next")
    print ("  <M-n> -> normal mode")
    print ("  <M-p> -> page the \" register into the terminal")
    print ("  <M-f> -> start a command")
    print ("Abbreviate:")
    print ("  pp    -> PYTHONPATH=")
    print ("  proxy -> set proxy short cut")
    print ("  nopro -> set no proxy short cut")
    print ("  pdb   -> python pdb")

@vim_register(command="Write", with_args=True)
def TerminalWriteFile(args):
    if (len(args) < 1): 
        print ("Write python_obj -> write str(python_obj) into tmpfile, and open a new tabe to present it.")
    obj = args[0]
    def prediction(wnr):
        return vim.eval(f"getwinvar({wnr}, '&buftype')") == "terminal"
    bufnr = int(FindWindowInCurrentTabIf(prediction))
    tmpfile = "/home/data/tmp.txt"
    send_keys(bufnr, f"open('{tmpfile}', 'w').write(str({obj}))\n")
    with CurrentWindowGuard(): 
        vim.command("tabe")
        time.sleep(1.0)
        vim.command(f"read {tmpfile}")