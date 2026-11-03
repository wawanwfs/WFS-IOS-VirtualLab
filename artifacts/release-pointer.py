import ctypes
import sys
x11=ctypes.CDLL('libX11.so.6')
x11.XOpenDisplay.restype=ctypes.c_void_p
x11.XFlush.argtypes=[ctypes.c_void_p]
display=x11.XOpenDisplay(b':99')
assert display
xtst=ctypes.CDLL('libXtst.so.6')
xtst.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
for button in (1,2,3):
    xtst.XTestFakeButtonEvent(display,button,False,0)
x11.XFlush(display)
sys.path.insert(0,'/workspace/hackios/qemu')
from touch import Qmp
Qmp().pointer(.5,.5,False)
print('Released X11 and QEMU pointer buttons')
