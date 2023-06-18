from . import vim_utils
import vim
from .func_register import *
from .rpc import rpc_call
from .command_doc_popup import DocPreviewBuffer

@vim_utils.Singleton
class HoogleSearchWindow:
    def __init__(self):
        self.doc_buffer = DocPreviewBuffer()
        self.markdowns = []
        self.cur = 0
        self.is_show = False

    def hide(self):
        self.doc_buffer.hide()
        self.is_show = False

    def show(self):
        if self.cur < len(self.markdowns) and self.cur >= 0:
            self.doc_buffer.set_markdown_doc(self.markdowns[self.cur])
            self.doc_buffer.show()
            self.is_show = True

    def set_markdowns(self, markdowns):
        self.markdowns = markdowns

@vim_register(keymap="<c-[>", command="Hoogle", with_args=True)
def HoogleSearch(args):
    if len(args) == 0: keyword = vim_utils.GetCurrentWord()
    else: keyword = args[0]
    def on_return(markdown_doc):
        HoogleSearchWindow().set_markdowns([markdown_doc])
        HoogleSearchWindow().show()

    if HoogleSearchWindow().is_show: 
        HoogleSearchWindow().hide()
    else:
        rpc_call("hoogle.search", on_return, keyword)
