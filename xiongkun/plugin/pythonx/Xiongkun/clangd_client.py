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
from .windows import GlobalPreviewWindow
import time
from .log import log
from urllib.parse import quote, unquote
from . import remote_fs
from .rpc import RPCServer
from .remote_fs import FileSystem

def _StartAutoCompile():# {{{
    cmd = """
augroup ClangdServer
    autocmd!
    autocmd BufEnter *.py,*.cc,*.h,*.cpp cal LSPDidOpen([])
    autocmd BufWritePost *.py,*.cc,*.h,*.cpp cal LSPDidChange([])
augroup END
"""
    vim_utils.commands(cmd)# }}}

def _EndAutoCompile():# {{{
    cmd = """
augroup ClangdServer
    autocmd!
augroup END
"""
    vim_utils.commands(cmd)# }}}

@contextmanager
def StopAutoCompileGuard():# {{{
    """ with this guard, all autocmd `ClangdServer` will not compile. 
    """
    try:
        _EndAutoCompile()
        yield
    finally:
        _StartAutoCompile()

clangd = None

def clangd_initialize(id):# {{{
    json = {
        "jsonrpc": "2.0",
        "id" : str(id),
        "method": "initialize",
        "params": {}
    }
    send_by_python(json)# }}}

def do_path_map(x, f, t):
    return x

def clangd_complete(id, filepath, pos=(0,0)):# {{{
    json = {
        "jsonrpc": "2.0",
        "id": str(id),
        "method": "textDocument/completion",
        "params": {
            "limit": 20,
            "context": {
                "triggerKind": 1, # invoke trigger.
            },
            "textDocument": {
                "uri": "file://" + do_path_map(filepath, "vim", "clangd"),
            },
            "position": {
                "line": pos[0], 
                "character" : pos[1],
            },
        }
    }
    return json

class LSPServer(RPCServer):
    def __init__(self, remote_server=None):
        self.server = RPCServer("LSP", remote_server, "lsp", "Xiongkun.lsp_server()")
        self.channel = self.server.channel

    def receive(self): # for hooker.
        msg = vim.eval(f"{self.channel.receive_name}")
        if not msg: return
        id, is_finished, output = json.loads(msg)
        if "error" in output: 
            print (f"[lsp] error happen: {output}")
            return 
        if id == -1: 
            return self.handle_method(output)
        return self.channel.on_receive(msg)

    def handle_method(self, package):
        pass

class LSPClient():# {{{
    def __init__(self, host):
        self.lsp_server = LSPServer(host)
        self.loaded_file = set()
        self.id = 1

    def _getid(self):
        self.id += 1
        return self.id

    def _lastid(self):
        return self.id

    def get_diagnostics(self, filepath):
        self.did_open(filepath)
        json = {
            "method": "get_diags",
            "file": "file://" + do_path_map(osp.abspath(filepath), 'vim', 'clangd'),
        }
        def get_diags(json):
            """
            example of diagnostics: 
            {'jsonrpc': '2.0', 'method': 'textDocument/publishDiagnostics', 'params': {'diagnostics': [{'code': 'access', 'message': "'bar' is a private member of 'MyClass'\n\nhello_world.cpp:5:8: note: implicitly declared private here", 'range': {'end': {'character': 9, 'line': 19}, 'start': {'character': 6, 'line': 19}}, 'severity': 1, 'source': 'clang'}, {'message': "Implicitly declared private here\n\nhello_world.cpp:20:7: error: 'bar' is a private member of 'MyClass'", 'range': {'end': {'character': 10, 'line': 4}, 'start': {'character': 7, 'line': 4}}, 'severity': 3}, {'code': 'undeclared_var_use', 'message': "Use of undeclared identifier 'dasdfs'", 'range': {'end': {'character': 10, 'line': 21}, 'start': {'character': 4, 'line': 21}}, 'severity': 1, 'source': 'clang'}, {'code': '-Wunused-private-field', 'message': "Private field 'foo' is not used", 'range': {'end': {'character': 9, 'line': 3}, 'start': {'character': 6, 'line': 3}}, 'severity': 1, 'source': 'clang', 'tags': [1]}], 'uri': 'file:///home/data/hello_world.cpp', 'version': 0}}
            """
            diags = send_by_python(json, timeout=(10, 10)).json()
            if diags == {}: return
            locs = []
            texts = []
            for diag in diags['params']['diagnostics']: 
                texts.append(diag['message'])
                locs.append(remote_fs.Location(
                    uri2abspath(diags['params']['uri']),
                    diag['range']['start']['line']+1, 
                    diag['range']['start']['character']+1))
            vim_utils.vim_dispatcher.call(vim_utils.SetQuickFixList, [locs, True, False, texts])
        threading.Thread(target=get_diags, args=(json,), daemon=True).start()
    # block
    def goto_ref(self, filepath, position):
        id = self._getid()
        self.did_open(filepath)
        rsp = clangd_goto(id, filepath, 'references', position)
        if rsp is None:
            return None
        rsp = [json.loads(rsp.content)]
        return [r for r in rsp if r.get('id', -1) == str(id)][0]

    def complete(self, filepath, position):
        id = self._getid()
        self.did_open(filepath)
        rsp = clangd_complete(id, filepath, position)
        if rsp is None: return None
        rsp = json.loads(rsp.content)
        kind2type = {# {{{
            7: "c", 2: "m", 1: "t", 4: "m", 22: "s", 6: "v", 3: "f"
        }# }}}
        results = []
        for item in rsp['result']['items']:# {{{
            #if '•' in item['label']: continue  # dont contain other library function.
            r = {}
            r['word'] = item['insertText']
            r['abbr'] = item['label']
            r['info'] = item['label']
            r['kind'] = kind2type.get(item['kind'], str(item['kind']))
            r['dup'] = 1
            results.append(r)# }}}
        return results
#}}}

def goto_definition(args, preview=False):# {{{
    """ if preview is True, open in preview windows.
    """
    cur_file = osp.abspath(vim_utils.CurrentEditFile())
    position = vim_utils.GetCursorXY()
    position = position[0]-1, position[1]-1

    def handle(rsp):
        if rsp['result'] is None: 
            print ("Definition No Found !")
            return []
        all_locs = _clangd_to_location( rsp['result'] )
        if len(all_locs) == 0: 
            print ("Implementation No Found !")
            return []
        if preview: 
            GlobalPreviewWindow.set_locs(all_locs)
            GlobalPreviewWindow.show()
        else:
            if len(all_locs) == 1:
                first_loc = all_locs[0]
                log("[Clangd Get Result]", first_loc.getfile())
                remote_fs.GoToLocation(first_loc, '.')
            else: 
                vim_utils.SetQuickFixList(all_locs, True, False)
        
    if args[0] == 'def': 
        clangd.lsp_server.call("goto", handle, cur_file, "definition", position)
    elif args[0] == 'ref': 
        clangd.lsp_server.call("goto", handle, cur_file, "implementation", position)

@vim_register(name="GoToDefinition", command="Def")
def py_goto_definition(args):
    file = vim_utils.CurrentEditFile()
    if clangd: goto_definition(['def'])
    else: 
        vim.command("normal gd")

@vim_register(name="GoToReference", command="Ref")
def Clangd_GoToRef(args):# {{{
    Clangd_GoTo(['ref'])# }}}

@vim_register(name="LSPDidOpen")
def LSPDidOpen(args):# {{{
    if not clangd: ClangdStart([])
    #filepath = FileSystem().current_filepath()
    filepath = vim_utils.CurrentEditFile(True)
    filepath = FileSystem().filepath(filepath)
    clangd.lsp_server.call("add_document", None, filepath)

@vim_register(command="LSPRestart")
def LSPRestart(args):# {{{
    #send_by_python(cmd='restart', directory=do_path_map(vim_utils.GetPwd(), "vim", "clangd"))
    global clangd
    clangd = None
    ClangdStart([])# }}}

@vim_register(name="LSPDidChange")
def LSPDidChange(args):
    filepath = vim_utils.CurrentEditFile(True)
    content = vim_utils.GetAllLines()
    lsp_server().call("did_change", None, filepath, content, True)

@vim_register(name="ClangdServerDiags", command="Compile")
def ClangdGetDiags(args):
    if clangd: 
        clangd.reparse_currentfile(True) # make sure file is the newest.
        time.sleep(0.5)
        clangd.get_diagnostics(vim_utils.CurrentEditFile(True))

@vim_register(name="ClangdServerComplete1", command="CP")
def ClangdCompleteInterface(args):# {{{
    support_filetype = ['cc', 'h', 'cpp']
    cur_file = osp.abspath(vim_utils.CurrentEditFile())
    suffix =  cur_file.split(".")[-1]
    if suffix not in support_filetype:
        print("Not a cpp file")
        return []
    position = vim_utils.GetCursorXY()
    position = position[0]-1, position[1]-1
    clangd.reparse_currentfile(True) # make sure file is the newest.
    time.sleep(0.3)
    return clangd.complete(cur_file, position)
# }}}

def uri2abspath(uri):
    """
    NOTES: uri is quoted. 
    C++ -> "C%2B%2B", we need unquote to decode.
    """
    uri = unquote(uri)
    return do_path_map(uri[7:], "clangd", "vim")

@vim_register(name="ClangdServerComplete")
def ClangdComplete(args):# {{{
    """
    {'isIncomplete': False, 'items': [{'filterText': 'MyClass', 'insertText': 'MyClass', 'insertTextFormat': 1, 'kind': 7, 'label': ' MyClass', 'score': 2.0423638820648193, 'sortText': '3ffd49e9MyClass', 'textEdit': {'newText': 'MyClass', 'range': {'end': {'character': 10, 'line': 16}, 'start': {'character': 4, 'line': 16}} } }]}
    """
    def find_start_pos():# {{{
        line = vim_utils.GetCurrentLine()
        col = vim_utils.GetCursorXY()[1] - 2 # 1-base -> 0-base
        while col >= 0 and (col >= len(line) or line[col].isalpha() or line[col] in ['_']):
            col -= 1
        return col + 2  # 1 for offset, 2 for 1-base}}}
    if clangd:
        l = ClangdCompleteInterface(args)
        vim_l = vim_utils.VimVariable().assign(l)
        vim.eval('complete(%d, %s)' % (find_start_pos(), vim_l))# }}}

@vim_register(name="ClangdClose", command="ClangdStop")
def ClangdClose(args):# {{{
    if clangd: _EndAutoCompile()

def _clangd_to_location(result):# {{{
    loc = []
    for r in result:
        loc.append(remote_fs.Location(uri2abspath(r['uri']), r['range']['start']['line']+1, r['range']['start']['character']+1))
    return loc# }}}

def lsp_server():
    return clangd.lsp_server

def set_remote_lsp(config_file):
    _EndAutoCompile()
    _StartAutoCompile()
    global clangd
    import yaml  
    if not os.path.exists(config_file): 
        print ("not exist.")
        return
    with open(config_file, 'r') as f:  
        data = yaml.safe_load(f)  
    host = data['host']
    clangd = LSPClient(host)
