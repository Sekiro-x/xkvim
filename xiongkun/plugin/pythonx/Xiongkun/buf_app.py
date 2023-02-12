import vim
import sys
import os
import os.path as osp
from .func_register import *
from .vim_utils import *
from collections import OrderedDict

@vim_register(name="BufApp_KeyDispatcher", with_args=True)
def Dispatcher(args):
    """ args[0] ==  name
        args[1] ==  key_name
    """
    obj = Buffer.instances[args[0]]
    key = args[1]
    obj.get_keymap()[key](obj, key)
    return True

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

    def get_keymap(self):
        return {}

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
        with CurrentBufferGuard(self.bufnr):
            vim.command("execute 'normal! ggdG'")
    
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
            saved = int(vim.eval('&modifiable'))
            vim.command('setlocal modifiable')
            self.onredraw()
            if saved == 0: 
                vim.command('setlocal nomodifiable')

    def onwipeout(self):
        pass

    def _set_default_options(self):
        vim.command("set filetype=")
        vim.command("set syntax=")
        vim.command("setlocal bufhidden=hide")
        vim.command('setlocal nomodifiable')
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
        #vim.command(f"echom {name} is Quit. len(instances) is {len(Buffer.instance)}")

    def _unset_autocmd(self):
        vim.command(f"augroup {self.name}")
        vim.command(f"au!")
        vim.command(f"augroup END")

    def auto_cmd(self, key):
        pass

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
    def __init__(self, screen_size, string_buffer):
        self.screen_size = screen_size  # (h, w)
        self.string_buffer = string_buffer # [None] * h

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

    def on_input_start(self):
        """ do something
        """
        pass

    def on_input_end(self):
        """ do something
        """
        pass

    def on_sync(self):
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

    def on_input_end(self):
        offset = len(self.prom) + 5
        line = GetAllLines()[self.position[0]]
        self.text = line[offset:].strip("|")

    def on_input_start(self):
        vim.command("startreplace")

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
        buffer[position[0]] = f">>> {self.text}"
        self._rematch("match_id", "ErrorMsg", None, ">>>")

    def get_height(self):
        return 1

    def on_focus(self):
        return (self.position[0], 5)

    def on_sync(self):
        line = GetAllLines()[self.position[0]-1]
        self.text = line[4:].strip()

    def on_input_start(self):
        pass

    def on_input_end(self):
        self.on_sync()
    
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
        draw_context = DrawContext(wsize, [""] * (wsize[0] + 1))
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

    def on_sync(self):
        for n, w in self.widgets.items(): 
            w.on_sync()
    
    def on_input(self):
        widget = self.get_input_widget(GetCursorXY())
        self.last_input_widget = widget
        widget.on_input_start()

    def on_input_end(self):
        if self.last_input_widget: 
            self.last_input_widget.on_input_end()
        self.last_input_widget = None
        self.redraw()

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
            'dd': lambda x,y: print("Can't delete one line."),
            'dj': lambda x,y: print("Can't delete one line."),
            'dk': lambda x,y: print("Can't delete one line."),
            '<c-c>': lambda x,y: self.on_exit(),
            'i:<c-c>': lambda x,y: self.on_exit(),
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
            self.on_sync()
            self.redraw()
            self.on_last_input()

    def on_insert_cursor_move(self):
        self.cursor_valid_check()

    def on_cursor_hold(self):
        pass

    def auto_cmd(self, cmd):
        if cmd == None: 
            return [
                "InsertLeave", "CursorMoved", "CursorMovedI", "InsertEnter", "CursorHoldI",
            ]
        if cmd == "InsertLeave": self.on_input_end()
        if cmd == "InsertEnter": self.on_input()
        if cmd == "CursorMoved": self.on_cursor_move()
        if cmd == "CursorMovedI": self.on_insert_cursor_move()
        if cmd == "CursorHoldI": self.on_cursor_hold()
        if cmd == "CursorHold": self.on_cursor_hold()

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
        self.cur_match_id = None
        self.highlight_group = "ListBoxLine"
        self.search_match_id = None
        self.search_highlight = "ListBoxKeyword"
        self.search_keyword = None
        self.tmp_mid = None
    
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

        # line highlight to indicate current selected items.
        self._rematch("cur_match_id", self.highlight_group, (self.cur, self.cur+2), None)
        if self.search_keyword: 
            self._rematch("search_match_id", "ErrorMsg", (0, self.height+1), self.search_keyword)
        self._rematch("tmp_mid", self.search_highlight, (self.cur, self.cur+2), self.search_keyword, 10)
        
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
    mru = MruList()
    mru_path = "/home/data/.vim_mru"
    @classmethod
    def preprocess(self):
        self.files = []
        for line in vim.eval("system(\"find ./\")").split("\n"):
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

class FileFinderBuffer(WidgetBuffer):
    def __init__(self, name="FileFinder", history=None, options=None):
        widgets = [
            ListBoxWidget(name="result", height=14, items=[]),
            SimpleInput(prom="input", name="input"),
        ]
        root = WidgetList("", widgets, reverse=True)
        super().__init__(root, name, history, options)
        if FileFinderPGlobalInfo.files is None: 
            FileFinderPGlobalInfo.preprocess()
        self.last_window_id = vim.eval("win_getid()")
        self.saved_cursor = GetCursorXY()
        self.files = FileFinderPGlobalInfo.files
        self.mode = "file"

    def on_search(self):
        """ 
        """
        import glob
        import re
        self.on_sync()
        search_text = self.widgets['input'].text.strip().lower()
        join = []
        for t in search_text: 
            if t == '+' or t == '-': join.append("|"+t)
            else: join.append(t)
        search_text = "".join(join)
        pieces = search_text.split("|")
        qualifier = []
        qualifier_name_set = set()
        search_base = None
        FileFinder
        for p in pieces: 
            p = p.strip()
            if not p: continue
            if p.startswith("+") or p.startswith("-"): 
                qualifier.append(p)
                qualifier_name_set.add(p)
            else: search_base = p
        if ".git/" not in qualifier_name_set: 
            qualifier.append("-git/")
        if "/build" not in qualifier_name_set: 
            qualifier.append("-/build")
        if "cmake/" not in qualifier_name_set: 
            qualifier.append("-cmake/")

        def filt(filepath): 
            basename = os.path.basename(filepath).lower()
            filepath = filepath.lower()
            if basename.startswith("."): return False
            if basename.endswith(".o"): return False
            if basename.endswith(".pyc"): return False
            #if not re.search(search_base, basename): return False
            if not re.search(search_base, filepath): return False
            for qual in qualifier: 
                if qual.startswith("+") and not re.search(qual[1:], filepath): return False
                if qual.startswith("-") and re.search(qual[1:], filepath): return False
            return True

        def score(filepath):
            basename = os.path.basename(filepath).lower()
            filepath = filepath.lower()
            addition = 0
            if re.search(search_base, basename): 
                addition = -10000 # high priority
            return addition + abs(len(basename) - len(search_base))

        if search_base is None: 
            self.widgets['result'].set_items(self.files)
            self.widgets['result'].set_keyword(None)
        else:
            res = sorted(list(filter(filt, self.files)), key=lambda x: score(x))
            self.widgets['result'].set_items(res)
            self.widgets['result'].set_keyword(search_base)
        self.redraw()

    def goto(self, filepath, cmd=None):
        FileFinderPGlobalInfo.update_mru(filepath)
        self.on_exit()
        if filepath:
            loc = Location(filepath)
            GoToLocation(loc, cmd)

    def on_exit(self):
        vim.command("set updatetime=4000")
        vim.command("stopinsert")
        vim.command("q")
        self.delete()
        vim.eval(f"win_gotoid({self.last_window_id})")
        SetCursorXY(*self.saved_cursor)

    def on_cursor_hold(self):
        self.on_search()

    def on_enter(self, cmd):
        self.on_sync()
        item = self.widgets['result'].cur_item()
        self.goto(item, cmd)

    def on_input_end(self):
        super().on_input_end()
        self.on_search()

    def oninit(self):
        super().oninit()
        vim.command(f'let w:filefinder_mode="{self.mode}"')
        vim.command('set filetype=filefinder')

    def on_item_up(self):
        self.widgets['result'].cur_up()
        self.redraw()
    
    def on_item_down(self):
        self.widgets['result'].cur_down()
        self.redraw()

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
            'i:<enter>': lambda x,y: self.on_enter("e"),
            '<enter>': lambda x,y: self.on_enter("e"),
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
        if not hasattr(self, "mode") or self.mode == "file":
            setattr(self, "mode", "mru")
            self.files = FileFinderPGlobalInfo.get_mru()[::-1]
        else: 
            setattr(self, "mode", "file")
            self.files = FileFinderPGlobalInfo.files
        vim.command(f"let w:filefinder_mode = \"{self.mode}\"")
        vim.command("AirlineRefresh")

class FileFinderApp(Application):
    """ 
    ListBoxWidget
    >>> input 
    """
    def __init__(self):
        super().__init__()
        self.layout = CreateWindowLayout(cmds=["botright new", "resize 15"], active_win="win")
        self.mainbuf = FileFinderBuffer()

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

@vim_register(command="FF")
def FileFinder(args):
    """ Find a file / buffer by regular expression.

        sort the files by the following order: 
        1. buffer with name
        2. mru files
        3. normal files
        4. with build / build_svd
    """
    ff = FileFinderApp()
    ff.start()

@vim_register(command="B", with_args=True, command_completer="buffer")
def BufferFinder(args):
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
    
