"""Adapt the packaged noVNC input path to a slow emulated touchscreen."""
from pathlib import Path

path = Path('/usr/share/novnc/core/rfb.js')
source = path.read_text()
marker = '// WFS touchscreen input'
if marker not in source:
    replacements = [
        ('const MOUSE_MOVE_DELAY = 17;', 'const MOUSE_MOVE_DELAY = 100;'),
        ('handleMouse: this._handleMouse.bind(this),',
         'handleMouse: this._handleMouse.bind(this),\n'
         '            releasePointer: this._releasePointer.bind(this),'),
        ("this._canvas.addEventListener('mousemove', this._eventHandlers.handleMouse);",
         "this._canvas.addEventListener('mousemove', this._eventHandlers.handleMouse);\n"
         "        window.addEventListener('blur', this._eventHandlers.releasePointer);\n"
         "        document.addEventListener('visibilitychange', this._eventHandlers.releasePointer);"),
        ("this._canvas.removeEventListener('mousemove', this._eventHandlers.handleMouse);",
         "this._canvas.removeEventListener('mousemove', this._eventHandlers.handleMouse);\n"
         "        window.removeEventListener('blur', this._eventHandlers.releasePointer);\n"
         "        document.removeEventListener('visibilitychange', this._eventHandlers.releasePointer);"),
        ('    _handleMouseButton(x, y, down, bmask) {',
         '    _handleMouseButton(x, y, down, bmask) {\n'
         "        this._mousePos = { 'x': x, 'y': y };"),
        ('    _handleMouseMove(x, y) {',
         '    // WFS touchscreen input: release touches when the browser loses focus.\n'
         '    _releasePointer() {\n'
         '        if (this._mouseButtonMask) {\n'
         '            this._handleMouseButton(this._mousePos.x, this._mousePos.y, false, 0xffff);\n'
         '        }\n'
         '    }\n\n'
         '    _handleMouseMove(x, y) {\n'
         '        // The local cursor moves without sending hover events to the guest.\n'
         '        if (!this.dragViewport && !this._mouseButtonMask) { return; }'),
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise SystemExit(f'Unexpected noVNC version; missing unique input hook: {old}')
        source = source.replace(old, new)
    path.write_text(source)
