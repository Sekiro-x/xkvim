import vim
import sys
import os
import os.path as osp
from .func_register import *
from .vim_utils import *
from collections import OrderedDict
from .rpc import rpc_call

def win_execute(wid, cmd):
    cmd = escape(cmd)
    log("[WinExe]", f'win_execute({wid}, "{cmd}")')
    vim.eval(f'win_execute({wid}, "{cmd}")')

vim_key_to_char = {
    '\x08': '<bs>',
    '\x04': '<c-d>',
    '\x06': '<c-f>',
    '\x17': '<c-w>',
    '\x15': '<c-u>',
    '\x0b': '<c-k>',
    '\r': '<cr>',
    '\n': '<c-j>',
    ' ' : '<space>',
    '\udc80\udcfd`': "<80><fd>",
    '\udc80kb': "<bs>",
}

@vim_register(name="BufApp_KeyDispatcher", with_args=True)
def Dispatcher(args):
    """ args[0] ==  name
        args[1] ==  key_name
    """
    obj = Buffer.instances[args[0]]
    key = args[1]
    buf_name = obj.name
    if vim.eval("mode()") == "i": 
        key = "i:" + key
    obj.get_keymap()[key](obj, args[1])
    return True

@vim_register(name="BufApp_PopupDispatcher", with_args=True)
def PopupDispatcher(args):
    """ args[0] ==  name
        args[1] ==  key_name
    """
    log("Handing raw:", args)
    bufname = vim.eval(f'bufname(winbufnr({args[0]}))')
    obj = Buffer.instances[bufname]
    key = args[1]
    if key in vim_key_to_char:
        key = vim_key_to_char[key]
    log("Handling: ", key)
    buf_name = obj.name
    keymapper = obj.get_keymap()
    if key not in keymapper: 
        vim.command("let g:popup_handle=0")
        return 
    handled = keymapper[key](obj, key)
    if handled is not None:
        vim.command("let g:popup_handle=1")
    else: 
        vim.command("let g:popup_handle=0")

def BufApp_AutoCmdDispatcher(name, key):
    obj = Buffer.instances[name]
    obj.auto_cmd(key)
    return True

def WindowQuit(name):
    obj = Buffer.instances[name]
    obj.delete()


class Buffer:
    instances = {}
    number = 0
    def __init__(self, appname, history=None, options=None):
        """
        options: 
            name = str: the name of application
            syntax = filepath
            clean  = [true] boolean, is clear all addtion keymap.
            vimopt = {
                key: value
            }
        """
        self.options = options if options else {}
        self.appname = appname
        self.name = appname + self._name_generator()
        self.history = history
        Buffer.instances[self.name] = self
        # TODO: add status here
        self.state="create"

    def get_keymap(self):
        return {}

    def execute(self, cmd):
        if hasattr(self, "wid"): win_execute(self.wid, cmd)
        else: vim.command(cmd)

    def _name_generator(self):
        Buffer.number += 1
        return str(Buffer.number)

    def save(self):
        """ return the history to save.
        """
        return None

    def onrestore(self, history):
        """ restore object by history.
        """
        pass

    def _clear(self):
        self.execute('execute "normal! ggdG"')
    
    def _put_string(self, text, pos=1):
        text = escape(text)
        vim.eval(f"setbufline({self.bufnr}, {pos}, \"{text}\")")

    def _put_strings(self, texts):
        for idx, text in enumerate(texts):
            self._put_string(text, idx+1)

    def onredraw(self):
        pass
    
    def oninit(self):
        pass
    
    def redraw(self):
        with CursorGuard():
            #saved = int(vim.eval('&modifiable'))
            #vim.command('setlocal modifiable')
            self.onredraw()
            #if saved == 0: 
                #vim.command('setlocal nomodifiable')

    def onwipeout(self):
        pass

    def _set_default_options(self):
        vim.command("set filetype=")
        vim.command("set syntax=")
        vim.command("setlocal bufhidden=hide")
        vim.command('setlocal modifiable')
        vim.command("setlocal buftype=nofile")
        vim.command("setlocal nofoldenable")

    def create(self):
        self._create_buffer()
        with CurrentBufferGuard(self.bufnr):
            if self.history: 
                self.onrestore(self.history)
            self._set_keymap()
            self._set_syntax()
            # custom initialized buffer options.
            self._set_autocmd()
            self._set_default_options()
            self.oninit()
            self.redraw()
            self.after_redraw()
        return self

    def after_redraw(self):
        pass

    def delete(self):
        self._unset_autocmd()
        self.onwipeout()
        with CurrentBufferGuard(self.bufnr): 
            vim.command(f"b #")
            vim.command(f"bwipeout {self.bufnr}")
        del Buffer.instances[self.name]
        self.state="exit"
        #vim.command(f"echom {name} is Quit. len(instances) is {len(Buffer.instance)}")

    def _unset_autocmd(self):
        vim.command(f"augroup {self.name}")
        vim.command(f"au!")
        vim.command(f"augroup END")

    def auto_cmd(self, key):
        pass

    def show(self):
        assert hasattr(self, "bufnr")
        self.wid = vim.eval(f"VimPopupExperiment({self.bufnr})")

    def _set_autocmd(self):
        if not self.auto_cmd(None): return
        vim.command(f"augroup {self.name}")
        vim.command(f"au!")
        for event in self.auto_cmd(None):
            vim.command(f"au {event} {self.name} py3 Xiongkun.BufApp_AutoCmdDispatcher('{self.name}', '{event}')")
        vim.command(f"augroup END")

    def _set_keymap(self):
        for key in self.get_keymap().keys():
            flag = "n"
            prefix = ""
            if key.startswith("i:"): 
                flag = 'i'
                prefix = prefix[0:2]
                key = key[2:]
            origin_key = key
            if key.startswith("<") and key.endswith(">"): 
                key = "<lt>" + key[1:]
            key = prefix + key
            map_cmd = {
                'n': 'nnoremap', 
                'i': 'inoremap',
            }[flag]
            vim.command("{map_cmd} <buffer> {orikey} <Cmd>call BufApp_KeyDispatcher([\"{name}\", \"{key}\"])<cr>".format(map_cmd=map_cmd, orikey=origin_key, key=key, name=self.name))
            
    def _set_syntax(self):
        pass

    def _create_buffer(self):
        self.bufnr = vim.eval(f"bufadd('{self.name}')")
        vim.eval(f"bufload({self.bufnr})")

class BufferSmartPoint:
    def __init__(self):
        self.buf = None

    def create(self, buf):
        self.buf = buf
        self.buf.create()

    def get(self):
        return self.buf

class Layout: 
    def __init__(self, active_win=None):
        self.active_win_name = active_win
        self.windows = {} # str -> winids
        self.buffers = {} # str -> Buffer

    def _create_windows(self):
        raise RuntimeError("dont implemented.")

    def _close_windows(self):
        for key, val in self.windows.items():
            with CurrentWindowGuard(val):
                vim.command("q")

    def create(self, buf_dict=None): 
        with CurrentWindowGuard(): 
            self.windows = self._create_windows()
        if self.active_win_name:
            winid = self._jump_to_winid(self.windows[self.active_win_name])
        if buf_dict: 
            self.reset_buffers(buf_dict)
        return self.windows

    def get_windows(self):
        return self.windows

    def set_buffer(self, name, buf):
        """ remove the original buffers
        """
        wid = self.windows[name]
        with CurrentWindowGuard(wid):
            vim.command(f"b {buf.bufnr}")
            if self.buffers.get(name) is not None: 
                self.buffers.get(name).delete()
        self.buffers[name] = buf
    
    def reset_buffers(self, buf_dict): 
        """ set buffer while create.
        """
        for key in buf_dict.keys():
            self.set_buffer(key, buf_dict[key])

    def _jump_to_winid(self, winid):
        vim.eval(f"win_gotoid({winid})")

    def _get_current_winid(self):
        return vim.eval("win_getid()")

    def windiff(self, names, on=True):
        for name in names: 
            with CurrentWindowGuard(self.windows[name]): 
                if on: vim.command("diffthis")
                else: vim.command("diffoff")

class CreateWindowLayout(Layout):
    """
    create window in a new tabe page 
    """
    def __init__(self, cmds=["tabe"], active_win=None):
        super().__init__(active_win)
        self.cmds = cmds

    def _create_windows(self):
        for cmd in self.cmds:
            vim.command(f"{cmd}")
        ret = {"win": self._get_current_winid()}
        return ret

class Application: 
    def __init__(self):
        pass

    def start(self):
        pass

class FixStringBuffer(Buffer):
    def __init__(self, text, history=None, options=None):
        super().__init__("fix_string", history, options)
        self.text = text

    def onredraw(self):
        self._clear()
        self._put_string(self.text)

    def get_keymap(self):
        """ some special key map for example.
        """
        return {
            '<enter>': lambda x,y: print ("<enter>"),
            '<space>': lambda x,y: print ("<space>"),
            '<up>': lambda x,y: print ("<up>"),
            '<f1>': lambda x,y: print ("<f1>"),
            '<bs>': lambda x,y: print ("<bs>"),
        }

class BashCommandResultBuffer(Buffer):
    def __init__(self, bash_cmd, syntax=None, history=None, options=None):
        super().__init__("bash_cmd", history, options)
        self.syntax = syntax
        self.bash_cmd = bash_cmd

    def oninit(self):
        if self.syntax: 
            vim.command(f'set syntax={self.syntax}')

    def onredraw(self):
        self._clear()
        if self.bash_cmd: 
            vim.command(f"silent! 0read! {self.bash_cmd}")
        vim.command(f"normal! gg")

class HelloworldApp(Application):
    def __init__(self):
        super().__init__()
        self.layout = CreateWindowLayout(active_win="win")
        self.mainbuf = FixStringBuffer("Hellow World")

    def start(self):
        self.layout.create()
        self.mainbuf.create()
        self.layout.set_buffer("win", self.mainbuf)

class WidgetOption:
    def __init__(self):
        self.name = None
        self.is_focus = False
        self.is_input = False
        self.position = (-1, -1) # expect position

class DrawContext:
    def __init__(self, bufnr, screen_size, string_buffer):
        self.screen_size = screen_size  # (h, w)
        self.string_buffer = string_buffer # [None] * h
        self.bufnr = bufnr

class Widget():
    def __init__(self, woptions): 
        self.wopt = woptions
        self.position = () # [start, end)

    def ondraw(self, draw_context, position): 
        """ draw self on a tmp string.
            including addmatch to colorize some area.

            different widget will never intersect with each other.
        """
        raise RuntimeError("Not Implement Error!")

    def get_widgets(self): 
        return [[self.wopt.name, self]]

    def get_height(self):
        return 1

    def has_focus(self):
        return self.wopt.is_focus

    def has_input(self):
        return self.wopt.is_input

    def on_focus(self):
        """ return cursor position
        """
        return (self.position[0], 1)

    def on_unfocus(self):
        pass

    def post_draw(self, context, position):
        pass

    def _rematch(self, attr, high, rrange, keyword=None, priority=0):
        if keyword is not None:
            keyword = escape(keyword, "~%")
            keyword = escape(keyword, "\\")
        if getattr(self, attr) is not None: 
            mid = getattr(self, attr)
            vim.eval(f"matchdelete({mid})")
        items = []
        if rrange: 
            start, end = rrange
            items.append(r"\\%>{}l\\&\\%<{}l".format(start, end))
        if keyword: 
            items.append(keyword)
        cmd = r"\\&".join(items)
        cmd += r"\\c"
        mid = vim.eval("matchadd(\"{}\", \"{}\", {})".format(
            high, 
            cmd, 
            priority))
        setattr(self, attr, mid)


class TextWidget(Widget):
    def __init__(self, text):
        opt = WidgetOption()
        opt.is_focus = False
        opt.is_input = False
        super().__init__(opt)
        self.text = text
        
    def ondraw(self, draw_context, position):
        self.position = position
        buffer = draw_context.string_buffer
        buffer[position[0]] = str(self.text)

class InputWidget(Widget):
    def __init__(self, prom="", text="", name=None):
        opt = WidgetOption()
        opt.is_focus = True
        opt.is_input = True
        opt.name = name
        super().__init__(opt)
        self.text = " "
        self.prom = prom

    def get_height(self):
        return 3
        
    def ondraw(self, draw_context, position):
        self.position = position
        buffer = draw_context.string_buffer
        content = "| " + self.prom + " : " + self.text + " |"
        width = len(content)
        # default behavior: set all lines to nullptr
        buffer[position[0] + 0] = "|" + '-' * (width - 2) + "|"
        buffer[position[0] + 1] = content
        buffer[position[0] + 2] = "|" + '-' * (width - 2) + "|"

    def on_focus(self):
        offset = len(self.prom) + 5
        return (self.position[0] + 1, offset + 1)

    def is_input_range_valid(self, cursor):
        x, y = cursor
        s, e = self.position
        if x >= s and s < e: return True
        return False

class SimpleInput(InputWidget):
    def __init__(self, prom="", text="", name=None):
        self.match_id = None
        super().__init__(prom, text, name)

    def ondraw(self, draw_context, position):
        self.position = position
        buffer = draw_context.string_buffer
        buffer[position[0]] = f">>>{self.text}"
        self._rematch("match_id", "ErrorMsg", None, ">>>")

    def get_height(self):
        return 1

    def on_focus(self):
        return (self.position[0], 5)

    def on_type(self, key):
        if key == "<space>": 
            key = " "
        elif key == "<bs>": 
            self.text = self.text[:-1]
        elif key == "<c-u>": 
            self.text = ""
        elif key == "<c-w>":
            split_char = "-/+ "
            tmp = 0
            for i, c in enumerate(self.text): 
                if c in split_char: 
                    tmp = i
            self.text = self.text[:tmp]
        else: 
            self.text = self.text + key
        return True
    
    def is_input_range_valid(self, cursor):
        if not super().is_input_range_valid(cursor): 
            return False
        if cursor[1] >= 5: return True

class WidgetBuffer(Buffer):
    """ content of buffer means a form to fill
        each widget is composed of several lines:
        Text-Based widget: not the most expressive solution, but it's the most effective solution.
    """
    def __init__(self, root_widget, name="WidgetBuffer", history=None, options=None):
        super().__init__(name, history, options)
        self.root = root_widget
        self.widgets = OrderedDict()
        self.focus_pos = -1
        self.last_input_widget = None
        for name, w in root_widget.get_widgets(): 
            if name: self.widgets[name] = w

    def oninit(self):
        if self.syntax: 
            vim.command(f'set syntax={self.syntax}')
            vim.command(f'hi CursorLine term=bold ctermbg=240')

    def parse(self):
        lines = GetAllLines(self.bufnr)

    def _get_window_size(self):
        return int(vim.eval("winheight(0)")), int(vim.eval("winwidth(0)"))

    def oninit(self):
        vim.command("set nowrap")
        vim.command("set updatetime=300")

    def onredraw(self):
        wsize = self._get_window_size()
        draw_context = DrawContext(self.bufnr, wsize, [""] * (wsize[0] + 1))
        given_lines = (1, draw_context.screen_size[0] + 1)
        self._clear()
        self.root.ondraw(draw_context, given_lines)
        for idx, line in enumerate(draw_context.string_buffer[1:]):
            cmd = ("setbufline({bufnr}, {idx}, \"{text}\")".format(
                bufnr = self.bufnr,
                idx = idx + 1,
                text= escape(line, "\"")
            ))
            vim.eval(cmd)
        vim.command(f"normal! gg")
        self.root.post_draw(draw_context, given_lines)

    def count_number(self, attr):
        number = 0
        for n, w in self.widgets.items():
            if getattr(w, attr)(): number += 1
        return number

    def get_widget_by_idx(self, i):
        for idx, (n, w) in enumerate(self.widgets.items()):
            if idx == i: return (n, w)
        raise RuntimeError("Out of index")

    def on_change_focus(self, name, key):
        if self.focus_pos != -1: 
            name, widget = self.get_widget_by_idx(self.focus_pos)
            widget.on_unfocus()

        if self.count_number("has_focus") == 0: 
            vim.command("echoe 'no focusable widget found. forgot to name it?'")
            return

        select_widget = None
        while True:
            self.focus_pos += 1
            self.focus_pos %= len(self.widgets)
            select_widget = self.get_widget_by_idx(self.focus_pos)[1]
            if select_widget.has_focus(): break

        cursor_position = select_widget.on_focus()
        self.redraw()
        SetCursorXY(*cursor_position)

    def on_change_size(self, key):
        pass

    def on_enter(self):
        pass

    def on_last_input(self):
        vim.command("setlocal modifiable")
        vim.command("normal G$")
        vim.command("startinsert!")

    def get_keymap(self):
        """ some special key map for example.
        """
        return {
            '<tab>': self.on_change_focus,
            'gi': lambda x,y: self.on_last_input(),
            '<c-c>': lambda x,y: self.on_exit(),
        }

    def get_input_widget(self, cursor): 
        for n, w in self.widgets.items():
            if w.has_input() and w.is_input_range_valid(cursor): 
                return w
        return None

    def on_cursor_move(self):
        c = GetCursorXY()
        if self.get_input_widget(c):
            vim.command('setlocal modifiable')
        else: 
            vim.command('setlocal nomodifiable')

    def on_exit(self):
        pass

    def cursor_valid_check(self):
        c = GetCursorXY()
        inp = self.last_input_widget
        if inp and not inp.is_input_range_valid(c): 
            self.redraw()
            self.on_last_input()

    def on_insert_cursor_move(self):
        self.cursor_valid_check()

    def on_cursor_hold(self):
        pass

    def insert_char_pre(self, char):
        pass

    def on_text_changed_i(self):
        pass

    def auto_cmd(self, cmd):
        if cmd == None: 
            return []
        else:
            method = getattr(self, cmd.lower(), None)
            if method: 
                method(self)

class WidgetBufferWithInputs(WidgetBuffer):
    def get_keymap(self):
        key_map = {}
        base_key = list(range(ord('a'), ord('z'))) + list(range(ord('A'), ord('Z')))
        for i in base_key:
            key_map[f"{chr(i)}"] = lambda x,y: self.on_insert_input(y)
        special_keys = [
            '<bs>', '<tab>', '<space>', '<c-w>', '<c-u>', '_', '-', '+', '=',
        ]
        for key in special_keys: 
            key_map[key] = lambda x,y: self.on_insert_input(y)
        return key_map

    def _create_buffer(self):
        super()._create_buffer()
        vim.command("imapclear <buffer>")
    
    def on_insert_input(self, key):
        pass

class WidgetList(Widget): 
    def __init__(self, name, widgets, reverse=False): 
        wopt = WidgetOption()
        wopt.name = name
        wopt.is_focus = False
        wopt.is_input = False
        super().__init__(wopt)
        self.widgets = widgets
        self.reverse = reverse

    def ondraw(self, draw_context, position): 
        """ draw self on a tmp string.
            including addmatch to colorize some area.

            different widget will never intersect with each other.
        """
        start, end = position
        self.position = position
        if self.reverse: 
            for w in self.widgets[::-1]:
                if end - w.get_height() < start: break
                w.ondraw(draw_context, (end-w.get_height(), end))
                end = end - w.get_height()
        else:
            for w in self.widgets:
                if start + w.get_height() >= end: break
                w.ondraw(draw_context, (start, start+w.get_height()))
                start = start + w.get_height()

    def post_draw(self, draw_context, position): 
        start, end = position
        self.position = position
        if self.reverse: 
            for w in self.widgets[::-1]:
                if end - w.get_height() < start: break
                w.post_draw(draw_context, (end-w.get_height(), end))
                end = end - w.get_height()
        else:
            for w in self.widgets:
                if start + w.get_height() >= end: break
                w.post_draw(draw_context, (start, start+w.get_height()))
                start = start + w.get_height()

    def get_height(self):
        return sum([w.get_height() for w in self.widgets])

    def get_widgets(self):
        return [ [w.wopt.name, w] for w in self.widgets ]

class ListBoxWidget(Widget):
    def __init__(self, name=None, height=5, items=[]): 
        wopt = WidgetOption()
        wopt.name = name
        super().__init__(wopt)
        self.items = items
        self.cur = 0
        self.height = height
        self.search_match_id = None
        self.search_keyword = None
        self.tmp_mid = None
        self.text_prop = None
        self.line_highlight = None
    
    def cur_item(self):
        if self.cur >= len(self.items): return None
        return self.items[self.cur]

    def cur_up(self): 
        if self.cur > 0 : self.cur -= 1

    def cur_down(self):
        if self.cur < self.height - 1: self.cur += 1

    def set_items(self, items=None): 
        if items is not None: self.items = items
        if self.cur >= len(items): self.cur = max(len(items) - 1, 0)
    
    def set_keyword(self, keyword):
        self.search_keyword = keyword

    def ondraw(self, draw_context, position): 
        width = draw_context.screen_size[1]
        bufnr = draw_context.bufnr
        def padded(text):
            return str(text) + (width - len(str(text))) * ' '
        self.position = position
        start, end = position
        buffer = draw_context.string_buffer
        if not len(self.items): 
            buffer[start] = padded("Not Found")
        else: 
            for text in self.items:
                if start >= end: break
                buffer[start] = padded(str(text))
                start += 1

    def post_draw(self, draw_context, position): 
        # line highlight to indicate current selected items.
        self.position = position
        start, end = position
        if self.search_keyword is None:
            return

        if self.text_prop is None: 
            self.text_prop = TextProp("ff_search", draw_context.bufnr, "ErrorMsg")
            self.line_highlight = TextProp("select", draw_context.bufnr, "ListBoxLine")

        self.line_highlight.clear()
        self.line_highlight.prop_add(self.cur+1, 1, 1000)

        def find_pos(search, cur_text):
            pointer = 0
            res = []
            search = search[::-1]
            cur_text = cur_text[::-1]
            length = len(cur_text)
            # reverse
            for col, c in enumerate(cur_text): 
                if c == search[pointer]: 
                    res.append(length - col)
                    pointer += 1
                if pointer == len(search): break
            return res

        cur_line = start
        self.text_prop.clear()
        for text in self.items:
            if cur_line >=  end: break
            for col in find_pos(self.search_keyword, text):
                self.text_prop.prop_add(cur_line, col)
            cur_line += 1

    def get_widgets(self): 
        return [[self.wopt.name, self]]

    def get_height(self):
        return self.height

    def __len__(self):
        return len(self.items)

class MruList:
    def __init__(self):
        self.items = []

    def push(self, item):
        if item in self.items: 
            idx = self.items.index(item)
            del self.items[idx]
        self.items.append(item)

    def get_as_list(self):
        return self.items

    def save(self, file):
        import pickle
        pickle.dump(self.items, open(file, "wb"))

    def load(self, file):
        import pickle
        if os.path.isfile(file):
            self.items = pickle.load(open(file, "rb"))

class FileFinderPGlobalInfo: 
    files = None
    directory = None
    mru = MruList()
    mru_path = f"{HOME_PREFIX}/.vim_mru"
    @classmethod
    def preprocess(self, directory):
        self.directory = directory
        self.files = []
        for line in vim.eval("system(\"find {dir}\")".format(dir=directory)).split("\n"):
            line = line.strip()
            if line and os.path.isfile(line):
                self.files.append(line)
        self.mru.load(self.mru_path)

    @classmethod
    def get_mru(self):
        return self.mru.get_as_list()

    @classmethod
    def update_mru(self, filepath):
        absp = os.path.abspath(filepath)
        self.mru.push(absp)
        self.mru.save(self.mru_path)

class FileFinderBuffer(WidgetBufferWithInputs):
    def __init__(self, directory="./", name="FileFinder", history=None, options=None):
        widgets = [
            ListBoxWidget(name="result", height=14, items=[]),
            SimpleInput(prom="input", name="input"),
        ]
        root = WidgetList("", widgets, reverse=False)
        super().__init__(root, name, history, options)
        self.directory = directory
        if FileFinderPGlobalInfo.directory != directory: 
            FileFinderPGlobalInfo.preprocess(directory)
        self.on_change_database()
        self.last_window_id = vim.eval("win_getid()")
        self.saved_cursor = GetCursorXY()

    def on_insert_input(self, key):
        self.widgets['input'].on_type(key)
        self.on_text_changed_i()
        return True

    def on_search(self):
        """ 
        """
        def update_ui(res): 
            if self.state == "exit":
                return
            res, search_base = res
            self.widgets['result'].set_items(res)
            self.widgets['result'].set_keyword(search_base)
            self.redraw()

        search_text = self.widgets['input'].text.strip().lower()
        rpc_call("filefinder.search", update_ui, search_text)

    def goto(self, filepath, cmd=None):
        FileFinderPGlobalInfo.update_mru(filepath)
        self.on_exit()
        if filepath:
            loc = Location(filepath)
            GoToLocation(loc, cmd)

    def on_exit(self):
        vim.command("set updatetime=4000")
        vim.command(f"call popup_close({self.wid})")
        self.delete()
        vim.eval(f"win_gotoid({self.last_window_id})")
        SetCursorXY(*self.saved_cursor)

    def on_text_changed_i(self):
        self.on_search()

    def on_enter(self, cmd):
        item = self.widgets['result'].cur_item()
        self.goto(item, cmd)

    def oninit(self):
        super().oninit()
        vim.command(f'let w:filefinder_mode="{self.mode}"')
        vim.command(f'let w:filefinder_dir="{self.directory}"')
        vim.command('set filetype=filefinder')

    def on_item_up(self):
        self.widgets['result'].cur_up()
        self.redraw()
        return True
    
    def on_item_down(self):
        self.widgets['result'].cur_down()
        self.redraw()
        return True

    def get_keymap(self):
        """ some special key map for example.
        """
        m = super().get_keymap()
        m.update({
            "i:<up>": lambda x,y: self.on_item_up(),
            "<up>": lambda x,y: self.on_item_up(),
            "i:<down>": lambda x,y: self.on_item_down(),
            "<down>": lambda x,y: self.on_item_down(),
            'i:<c-k>': lambda x,y: self.on_item_up(),
            'i:<c-j>': lambda x,y: self.on_item_down(),
            '<c-k>': lambda x,y: self.on_item_up(),
            '<c-j>': lambda x,y: self.on_item_down(),
            'i:<cr>': lambda x,y: self.on_enter("e"),
            '<cr>': lambda x,y: self.on_enter("e"),
            'i:<c-s>': lambda x,y: self.on_enter("v"),
            '<c-s>': lambda x,y: self.on_enter("v"),
            '<c-t>': lambda x,y: self.on_enter("t"),
            'i:<c-t>': lambda x,y: self.on_enter("t"),
            '<c-p><c-p>': lambda x,y: x,
            '<c-p>': lambda x,y: x,
            'i:<tab>': lambda x,y: self.on_change_database(),
            '<tab>': lambda x,y: self.on_change_database(),
        })
        return m

    def on_change_database(self):
        if hasattr(self, 'mode') and self.mode == "file":
            setattr(self, "mode", "mru")
            self.files = FileFinderPGlobalInfo.get_mru()[::-1]
        else: 
            setattr(self, "mode", "file")
            self.files = FileFinderPGlobalInfo.files
        vim.command(f"let w:filefinder_mode = \"{self.mode}\"")
        vim.command("AirlineRefresh")
        type = self.directory+"@"+self.mode
        def set_file(cur_type):
            log("Type is:", cur_type, type)
            if cur_type != type:
                rpc_call("filefinder.set_files", None, type, self.files)
        rpc_call("filefinder.get_type", set_file)

class FileFinderApp(Application):
    def __init__(self, directory='./'):
        super().__init__()
        self.layout = CreateWindowLayout(cmds=["botright new", "resize 15"], active_win="win")
        self.mainbuf = FileFinderBuffer(directory=directory)

    def start(self):
        self.layout.create()
        self.mainbuf.create()
        self.layout.set_buffer("win", self.mainbuf)
        self.mainbuf.on_change_focus(None, None)
        vim.command("setlocal modifiable")
        vim.command("startinsert")

@vim_register(command="FR")
def FileFinderReflesh(args):
    FileFinderPGlobalInfo.preprocess()

#@vim_register(command="FF", with_args=True, command_completer="file")
#def FileFinder(args):
    #""" Find a file / buffer by regular expression.

        #sort the files by the following order: 
        #1. buffer with name
        #2. mru files
        #3. normal files
        #4. with build / build_svd
    #"""
    #directory = "./"
    #if len(args) == 1: 
        #directory = args[0]
    #ff = FileFinderApp(directory=directory)
    #ff.start()

@vim_register(command="B", with_args=True, command_completer="buffer")
def BufferFinder(args):
    ff.start()
    #ff.on_cursor_hold = on_auto_hold
    ff.mainbuf.files = GetBufferList()
    input = "" if len(args)==0 else " ".join(args)
    ff.mainbuf.widgets['input'].text = input
    ff.mainbuf.redraw()
    ff.mainbuf.on_last_input()
    ff.mainbuf.on_search()
    if len(ff.mainbuf.widgets['result']) == 1: 
        ff.mainbuf.on_enter("b")
        
@vim_register(command="SB", with_args=True, command_completer="buffer")
def SplitBufferFinder(args):
    ff = FileFinderApp()
    ff.start()
    #ff.on_cursor_hold = on_auto_hold
    ff.mainbuf.files = GetBufferList()
    input = "" if len(args)==0 else " ".join(args)
    ff.mainbuf.widgets['input'].text = input
    ff.mainbuf.redraw()
    ff.mainbuf.on_last_input()
    ff.mainbuf.on_search()
    if len(ff.mainbuf.widgets['result']) == 1: 
        ff.mainbuf.on_enter("sb")
    

@vim_register(command="FF")
def TestPopup(args):
    ff = FileFinderBuffer(directory="./")
    ff.create()
    ff.show()
    
