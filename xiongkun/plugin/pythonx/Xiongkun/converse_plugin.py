import vim
import subprocess
import os
from os import path as osp
from . import vim_utils
from .func_register import *
import random
import threading
import json
from contextlib import contextmanager
import time
import os.path as osp
from .log import log, log_google
from urllib.parse import quote
import shlex
from .remote_machine import RemoteConfig, remote_machine_guard
from .remote_fs import FileSystem
from .rpc import rpc_wait

@vim_register(command="SetRemote", with_args=True, action_tag="set remote")
def SetRemote(args):
    """ 
    `SetRemote <remote-name>`: 设置远程的机器，用于远程操作
    1. _<remote-name>_ in [ pc | mac ]
    >>> SetRemote pc
    >>> SetRemote mac
    """
    RemoteConfig().set_remote(args[0])
    print(f"set the remote name to -> {args[0]}")
    print(f"    the os machine is  -> {RemoteConfig().get_machine()}")

@vim_register(command="Google", with_args=True)
def Google(args):
    """ 
    `Google <text>`: google the _<text>_ in remote machine.
    1. _<text>_ can be space split.
    >>> Google hello world
    """
    from os import path as ops
    text = " ".join(args)
    if not text: 
        text = vim_utils.GetCurrentWord()
    if text: log_google(text)
    url_text = quote(text)
    """ 
    MacOs: open "http://" can open a http website in default browser.
    """
    url = """https://www.google.com.hk/search?q=%s""" % url_text
    RemoteConfig().get_machine().chrome(url)

@vim_register(command="Paper", with_args=True)
def RandomReadPaper(args):
    """ 
    `Paper`: open a paper list.
    >>> Paper
    """
    papers = [
        'Selected the Conference:',
        '1. 计算机自动化: Automated Software Engineering', 
        '2. 离散算法: TALG', 
        '3. CCF 排名',
    ]
    link = [
        'place_holder',
        'https://www.springer.com/journal/10515', 
        'https://dl.acm.org/toc/talg/2022/18/1', 
        'https://www.ccf.org.cn/Academic_Evaluation/TCS/',
    ]
    lis = vim_utils.VimVariable(papers)
    selected = int(vim.eval(f"inputlist({lis.name()})"))
    RemoteConfig().get_machine().chrome(link[selected])

def baidu_translate(sentence):
    import subprocess
    sentence = sentence.replace("\n", "")
    cmd = "python3 ~/xkvim/cmd_script/baidu_fanyi.py --query \"{sentence}\"".format(
        sentence = sentence,
    )
    child = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
    info = child.stdout.readline().strip()
    return info

def run_python_file(python_file, **kwargs):
    import subprocess
    args_str = []
    pre_command = ["source ~/.bashrc"]
    with open(python_file, "r") as fp :
        lines = fp.readlines()
        for line in lines:
            if line.startswith("#cmd:"):
                line = line.replace("#cmd:", "").strip()
                pre_command.append(line)
                
    for key, val in kwargs.items():
        args_str.append(f"--{key} {val}")
    args_str = " ".join(args_str)
    pre_command.append("python3")
    command_str = "&&".join(pre_command)
    cmd = f"bash -c '{command_str} {python_file} {args_str}'"
    log(f"Start run `{cmd}`")
    child = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    error = "".join(child.stderr.readlines()).strip()
    info = "".join(child.stdout.readlines()).strip()
    if error: 
        print("Error occur:\n", error)
        return ""
    return info


def open_terminal_window(name):
    if not FileSystem().is_remote(): 
        vim.command("bot terminal")
    else: 
        vim.command("Bash")
    vim.command("wincmd J")
    vim.command("resize 7")
    vim.command("setlocal bufhidden=hide")
    vim.command(f"silent file {name}")
    bufnr = vim.eval("bufnr()")
    return bufnr

def run_in_terminal_window(cmd):
    if int(vim.eval("bufexists('terminal_run_file')")) == 0: 
        log(f"Start run `{cmd}` in terminal windows.")
        with vim_utils.CurrentWindowGuard():
            bufnr = open_terminal_window("terminal_run_file")
    bufnr = vim.eval("bufnr('terminal_run_file')")
    is_hidden = int(vim.eval(f"getbufinfo({bufnr})")[0]['hidden'])
    if is_hidden == 1: 
        with vim_utils.CurrentWindowGuard():
            vim.command("bot sb terminal_run_file")
            vim.command("resize 7")
    from .remote_terminal import send_keys
    vim_utils.PythonFunctionTimer().do_later(0.5, send_keys, [bufnr, cmd+"\n"])

def get_run_file_command(file, **kwargs):
    args_str = []
    file = FileSystem().abspath(file)
    pre_command = ["source ~/.bashrc"]
    lines = FileSystem().fetch(file).split("\n")
    for line in lines:
        if line.startswith("#cmd:"):
            line = line.replace("#cmd:", "").strip()
            pre_command.append(line)
                
    for key, val in kwargs.items():
        args_str.append(f"--{key} {val}")
    args_str = " ".join(args_str)
    if file.split(".")[-1] == 'py': 
        pre_command.append(f"python3 ")
    elif file.split(".")[-1] in ['hs', 'haskell']: 
        pre_command.append(f"runhaskell ")
    else: 
        raise NotImplementedError("Not support file type.")
    command_str = "&&".join(pre_command)
    cmd = f"bash -c '{command_str} {file} {args_str}'"
    return cmd

@vim_register(command="Trans")
def TranslateAndReplace(args):
    """ translate and replace the current visual highlight sentence.
    """
    word = vim_utils.GetVisualWords()
    info = baidu_translate(word)
    vim_utils.SetVisualWords(info)

@vim_register(keymap="K")
def Translate(args):
    word = vim_utils.GetCurrentWord()
    info = baidu_translate(word)
    vim.command("echom '百度翻译结果：'")
    print(info)

@vim_register_visual(keymap="K")
def VisualTranslate(args):
    """ `< and `>
    """
    text = vim_utils.GetVisualWords()
    info = baidu_translate(text)
    vim.command("echom '百度翻译结果：'")
    print(info)

@vim_register(command="Gast")
def GastDump(args):
    """ `< and `>
    """
    file = vim_utils.WriteVisualIntoTempfile()
    info = run_python_file("~/xkvim/cmd_script/dump_gast.py", file=file)
    print(info)

@vim_register(command="Run", keymap="<F9>")
def RunCurrentFile(args):
    """
    `Run`: Run a python file and print the output.
    we need a sleep to wait for draw.
    >>> Run
    >>> <F9>
    """
    file = vim_utils.CurrentEditFile(True)
    file = FileSystem().abspath(file)
    run_command = []
    if vim.eval("getcwd()").strip() in file: 
        run_command = rpc_wait("config.get_config_by_key", "default_run", FileSystem().getcwd())
    if len(run_command) == 0: 
        run_command = get_run_file_command(file)
    run_in_terminal_window(run_command)

@vim_register(command="Copyfile")
def PaddleCopyfile(args):
    """ In paddlepaddle, we call /home/data/web/scripts/copy_file.sh under each build* directory.
    """
    from .remote_fs import FileSystem
    filepath = FileSystem().current_filepath()
    build_filepath = filepath.replace("Paddle/python/paddle", "Paddle/build/python/paddle")
    ret = FileSystem().command(f"cp {filepath} {build_filepath}")
    if ret:
        print ("You paddlepaddle is updated.")

@vim_register(command="Pdoc", with_args=True)
def PaddleDocumentFile(args):
    """ In paddlepaddle, search the offical docuement and show the api usage.
    """
    text = " ".join(args)
    if not text: 
        text = vim_utils.GetCurrentWord()
    url_text = quote(text)
    url = RemoteConfig().get_machine()._command_escape(f"https://www.paddlepaddle.org.cn/searchall?q={url_text}&language=zh&version=2.3")
    RemoteConfig().get_machine().chrome(url)

@vim_register(command="ShareCode")
def ShareCode(args):
    """ we share code into 0007 server.
    """
    word = vim_utils.GetVisualWords()
    open("/tmp/share.txt", "w").write(word)
    if vim_utils.system("python3 ~/xkvim/cmd_script/upload.py --file /tmp/share.txt")[0]: 
        print ("Your code is shared into http://10.255.125.22:8082/share.txt")

@vim_register(command="Share")
def ShareCodeToClipboard(args):
    word = vim_utils.GetVisualWords()
    open("/tmp/share.txt", "w").write(word)
    if vim_utils.system("python3 ~/xkvim/cmd_script/upload.py --file /tmp/share.txt")[0]: 
        print ("Your code is shared into http://10.255.125.22:8082/share.txt")
        vim.command("ShareCodeCopyClipboard")
        

@vim_register(command="UploadFile", with_args=True, command_completer="customlist,RemoteFileCommandComplete")
def UploadFile(args):
    """ 
    `UploadFile (<remotefs-file>|<remotefs-dir>) `: send a compressed file in local machine into 007 server and renamed to tmpfile.tar
    >>> UploadFile /home/data/tmp.py # upload a single file.
    >>> UploadFile /home/data/ # upload a directory.
    """
    if len(args) != 1: 
        print ("Usage: SendFile <local_file>|<local_dir>")
        return
    FileSystem().command(f"rm -rf /tmp/tmpfile && mkdir -p /tmp/tmpfile && cp -r {args[0]} /tmp/tmpfile")
    FileSystem().command("cd /tmp && tar -zcvf tmpfile.tar tmpfile")
    FileSystem().command("unset http_proxy && unset https_proxy && python3 ~/xkvim/cmd_script/upload.py --file /tmp/tmpfile.tar")

@vim_register(command="SendFile", with_args=True, command_completer="customlist,RemoteFileCommandComplete")
def SendFile(args):
    """ 
    `SendFile (<remotefs-file> | <remotefs-dir>) <remote-machine>`: upload file to 007 server and let remote machine open it.
    ----------------------------------------------------
    >>> SendFile /home/data/tmp.py # send a single file and open it.
    >>> SendFile /home/data/ # send a directory and open it.
    """
    if not FileSystem().exists(args[0]): 
        print("Please inputs a valid direcotry or file path.")
        return
    exe_machine = RemoteConfig().get_remote()
    if len(args) >= 2: exe_machine = args[1]
    assert exe_machine in ["mac", "pc"], "Only support in mac and windows."
    with remote_machine_guard(exe_machine): 
        RemoteConfig().get_machine().send_file(args[0])

@vim_register(command="PreviewFile", with_args=True, command_completer="customlist,RemoteFileCommandComplete")
def PreviewFile(args):
    """ 
    `PreviewFile (<remotefs-file> | <remotefs-dir>) <remote-machine>`: upload file to 007 server and let remote machine open it.
    ----------------------------------------------------
    >>> PreviewFile /home/data/tmp.py # send a single file and open it.
    >>> PreviewFile /home/data/ # send a directory and open it.
    """
    if not FileSystem().exists(args[0]): 
        print("Please inputs a valid direcotry or file path.")
        return
    exe_machine = RemoteConfig().get_remote()
    if len(args) >= 2: exe_machine = args[1]
    SendFile(args)
    with remote_machine_guard(exe_machine): 
        RemoteConfig().get_machine().preview_file(args[0])

@vim_register(command="ShareCodeCopyClipboard")
def CopyClipboard(args):
    RemoteConfig().get_machine().set_clipboard()
    print("Shared!.")
