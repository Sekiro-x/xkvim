import vim
import sys
import os
import os.path as osp
from .func_register import *
from .vim_utils import *
from collections import OrderedDict
from .rpc import rpc_call
start = None

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
    '\udc80kd': "<down>",
    '\udc80kr': "<right>", 
    '\udc80kl': '<left>',
    '\udc80ku': '<up>',
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

@vim_register(name="BufApp_PopupClose", with_args=True)
def WindowQuit(args):
    bufname = vim.eval(f'bufname(winbufnr({args[0]}))')
    log (f"[WindowQuit] closing {bufname}")
    obj = Buffer.instances[bufname]
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
            self.onredraw()

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
        with CursorGuard(), CurrentBufferGuard(self.bufnr):
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
        if self.state != "exit":
            self._unset_autocmd()
            self.onwipeout()
            log(f"[BufferDelete] start delete `bwipeout! {self.bufnr}`")
            vim.command(f"bwipeout! {self.bufnr}")
            del Buffer.instances[self.name]
            self.state="exit"
            self.on_exit()

    def _unset_autocmd(self):
        vim.command(f"augroup {self.name}")
        vim.command(f"au!")
        vim.command(f"augroup END")

    def auto_cmd(self, key):
        pass

    def show(self):
        assert hasattr(self, "bufnr")
        self.options['cursorline'] = 0
        config = dict2str(self.options)
        self.wid = vim.eval(f"VimPopupExperiment({self.bufnr}, {config})")

    def start(self):
        self.create()
        self.show()

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

    def close(self):
        vim.command("set updatetime=4000")
        vim.command(f"call popup_close({self.wid})")
        self.delete()

    def on_exit(self):
        pass


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
            self.execute(f'set syntax={self.syntax}')

    def onredraw(self):
        self._clear()
        if self.bash_cmd: 
            self.execute(f"silent! 0read! {self.bash_cmd}")
        self.execute(f"normal! gg")

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
            split_char = "_-/+ "
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

    def get_keymap(self):
        """ some special key map for example.
        """
        return {
            '<tab>': self.on_change_focus,
            '<c-c>': lambda x,y: self.close(),
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
            '<bs>', '<tab>', '<space>', '<c-w>', '<c-u>', '_', '-', '+', '=', '.', '/'
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

        if self.line_highlight is None: 
            self.line_highlight = TextProp("select", draw_context.bufnr, "ListBoxLine")
        self.line_highlight.clear()
        self.line_highlight.prop_add(self.cur+1, 1, 1000)
        if self.search_keyword is None:
            return

        if self.text_prop is None: 
            self.text_prop = TextProp("ff_search", draw_context.bufnr, "ErrorMsg")

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

        excludes = GetSearchConfig(self.directory)
        base_cmd = f"find {directory} "
        find_cmd = []
        for exclude in excludes: 
            find_cmd.append(" ".join(["-not", "-path", f"\"*{exclude}\""]))

        log("[FindCmd]: ", find_cmd)
        find_cmd = " -a ".join(find_cmd)
        find_cmd = base_cmd + find_cmd
        log("[FindCmd]: ", find_cmd)

        self.files = []
        for line in vim.eval("system('{cmd}')".format(cmd=find_cmd)).split("\n"):
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

class SimpleInputBuffer(WidgetBufferWithInputs):
    def __init__(self, name="input", history=None, options=None):
        widgets = [
            SimpleInput(prom="input", name="input"),
        ]
        root = WidgetList("", widgets, reverse=False)
        super().__init__(root, name, history, options)

    def on_insert_input(self, key):
        self.widgets['input'].on_type(key)
        self.redraw()
        return True

class FuzzyList(WidgetBufferWithInputs):
    def __init__(self, type, items, name="FuzzyList", history=None, options=None):
        widgets = [
            ListBoxWidget(name="result", height=14, items=[]),
            SimpleInput(prom="input", name="input"),
        ]
        options = {
            'title': "FuzzyList", 
            'maxwidth': 100, 
            'maxheight': 15, 
        }
        root = WidgetList("", widgets, reverse=False)
        self.items = items
        self.type = type
        super().__init__(root, name, history, options)
        self.set_items(self.type, self.items)

    def on_insert_input(self, key):
        self.widgets['input'].on_type(key)
        self.onredraw() # we should redraw the input widget to show the input text. time consume: 0.002+
        self.on_text_changed_i()
        return True

    def update_ui(self, res): 
        """
        res is a tuple of (res_list, search_base)
        """
        if self.state == "exit":
            return
        res, search_base = res
        if not search_base: res = self.items
        self.widgets['result'].set_items(res)
        self.widgets['result'].set_keyword(search_base)
        self.redraw()

    def on_search(self):
        """ 
        """
        search_text = self.widgets['input'].text.strip().lower()
        rpc_call("fuzzyfinder.search", self.update_ui, self.type, search_text)

    def on_text_changed_i(self):
        self.on_search()

    def on_enter(self, cmd):
        pass

    def on_item_up(self):
        self.widgets['result'].cur_up()
        self.redraw()
        return True
    
    def on_item_down(self):
        self.widgets['result'].cur_down()
        self.redraw()
        return True

    def set_items(self, name, items):
        def _set(cur_type):
            if cur_type is False:
                rpc_call("fuzzyfinder.set_items", None, name, items)
        rpc_call("fuzzyfinder.is_init", _set, name)

    def get_keymap(self):
        """ some special key map for example.
        """
        m = super().get_keymap()
        m.update({
            "<up>": lambda x,y: self.on_item_up(),
            "<down>": lambda x,y: self.on_item_down(),
            '<c-k>': lambda x,y: self.on_item_up(),
            '<c-j>': lambda x,y: self.on_item_down(),
            '<cr>': lambda x,y: self.on_enter("e"),
            '<c-s>': lambda x,y: self.on_enter("v"),
            '<c-t>': lambda x,y: self.on_enter("t"),
            '<c-p><c-p>': lambda x,y: x,
            '<c-p>': lambda x,y: x,
            '<tab>': lambda x,y: self.on_change_database(),
        })
        return m

    def oninit(self):
        super().oninit()
        self.update_ui(([], None))

class CommandList(FuzzyList):
    def __init__(self, type, names, commands):
        super().__init__(type, names)
        assert (len(names) == len(commands)), "Length should be equal."
        self.name2cmd = {
            n: c for n, c in zip(names, commands)
        }

    def on_enter(self, cmd):
        cur_name = self.widgets['result'].cur_item()
        cmd = self.name2cmd[cur_name]
        vim.command(cmd)
        self.close()

class FileFinderBuffer(FuzzyList):
    def __init__(self, directory="./", name="FileFinder", history=None, options=None):
        self.directory = directory
        if FileFinderPGlobalInfo.directory != directory: 
            FileFinderPGlobalInfo.preprocess(directory)
        self.on_change_database()
        super().__init__(self.file_type, self.files, name, history, options)
        self.last_window_id = vim.eval("win_getid()")
        self.saved_cursor = GetCursorXY()

    def oninit(self):
        super().oninit()
        vim.command(f'let w:filefinder_mode="{self.mode}"')
        vim.command(f'let w:filefinder_dir="{self.directory}"')
        vim.command('set filetype=filefinder')

    def on_enter(self, cmd):
        item = self.widgets['result'].cur_item()
        self.goto(item, cmd)

    @property
    def file_type(self):
        return self.directory+"@"+self.mode

    def goto(self, filepath, cmd=None):
        FileFinderPGlobalInfo.update_mru(filepath)
        self.close()
        if filepath:
            loc = Location(filepath)
            GoToLocation(loc, cmd)

    def on_exit(self):
        SetCursorXY(*self.saved_cursor)

    def on_change_database(self):
        if hasattr(self, 'mode') and self.mode == "file":
            setattr(self, "mode", "mru")
            self.files = FileFinderPGlobalInfo.get_mru()[::-1]
        else: 
            setattr(self, "mode", "file")
            self.files = FileFinderPGlobalInfo.files

@vim_register(command="FR", with_args=True, command_completer="file")
def FileFinderReflesh(args):
    directory = "./"
    if len(args) == 1: 
        directory = args[0]
    FileFinderPGlobalInfo.preprocess(directory)

@vim_register(command="FF", with_args=True, command_completer="file")
def FileFinder(args):
    """ Find a file / buffer by regular expression.

        sort the files by the following order: 
        1. buffer with name
        2. mru files
        3. normal files
        4. with build / build_svd
    """
    directory = "./"
    if len(args) == 1: 
        directory = args[0]
    ff = FileFinderBuffer(directory=directory)
    ff.start()

@vim_register(command="B", with_args=True, command_completer="buffer")
def BufferFinder(args):
    ff.start()
    ff.mainbuf.files = GetBufferList()
    input = "" if len(args)==0 else " ".join(args)
    ff.mainbuf.widgets['input'].text = input
    ff.mainbuf.redraw()
    ff.mainbuf.on_search()
    if len(ff.mainbuf.widgets['result']) == 1: 
        ff.mainbuf.on_enter("b")
        
@vim_register(command="SB", with_args=True, command_completer="buffer")
def SplitBufferFinder(args):
    ff = FileFinderApp()
    ff.start()
    ff.mainbuf.files = GetBufferList()
    input = "" if len(args)==0 else " ".join(args)
    ff.mainbuf.widgets['input'].text = input
    ff.mainbuf.redraw()
    ff.mainbuf.on_search()
    if len(ff.mainbuf.widgets['result']) == 1: 
        ff.mainbuf.on_enter("sb")
    
@vim_register(command="TestInput")
def TestInput(args):
    ff = SimpleInputBuffer()
    ff.create()
    ff.show()
    
@vim_register(command="TestFuzzyList")
def TestFuzzyList(args):
    ff = AbbreList("abbre", ['aaa', 'bbb', 'ccc'])
    ff.create()
    ff.show()
    
