"""OpenGL 渲染画布：预览 + 渲染基准。"""
from __future__ import annotations

import struct
from typing import List, Optional, Tuple

from PySide6.QtCore import QElapsedTimer, QTimer, Signal
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

GL_FLOAT = 0x1406
GL_TRIANGLE_STRIP = 0x0005
GL_COLOR_BUFFER_BIT = 0x4000

_VS = """#version 330 core
layout(location=0) in vec2 aPos;
out vec2 vUV;
void main(){ vUV = aPos*0.5+0.5; gl_Position = vec4(aPos, 0.0, 1.0); }
"""

_FS = """#version 330 core
in vec2 vUV;
out vec4 frag;
uniform float uTime;
uniform float uIter;
void main(){
    vec2 p = vUV;
    float acc = 0.0;
    for (int i = 0; i < 512; i++){
        if (float(i) >= uIter) break;
        p = vec2(p.x + sin(p.y + uTime), p.y + cos(p.x + uTime));
        acc += length(p);
    }
    frag = vec4(fract(acc*0.017), fract(acc*0.031), fract(acc*0.053), 1.0);
}
"""


class GpuCanvas(QOpenGLWidget):
    benchProgress = Signal(int, str)
    benchFinished = Signal(float, int, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self._program: Optional[QOpenGLShaderProgram] = None
        self._vao: Optional[QOpenGLVertexArrayObject] = None
        self._vbo: Optional[QOpenGLBuffer] = None
        self._gl = None
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)
        self._elapsed = QElapsedTimer()
        self._config: List[Tuple[int, int]] = [(128, 300), (384, 300)]
        self._stage = 0
        self._stage_iter = 128
        self._stage_frames = 300
        self._frame = 0
        self._total_frames = 0
        self._running = False
        self._preview_time = 0.0

    def initializeGL(self) -> None:
        try:
            self._gl = self.context().functions()
            self._gl.glClearColor(0.05, 0.07, 0.10, 1.0)
            program = QOpenGLShaderProgram()
            if not program.addShaderFromSourceCode(QOpenGLShader.Vertex, _VS):
                raise RuntimeError(program.log())
            if not program.addShaderFromSourceCode(QOpenGLShader.Fragment, _FS):
                raise RuntimeError(program.log())
            if not program.link():
                raise RuntimeError(program.log())
            self._program = program
            self._vao = QOpenGLVertexArrayObject()
            self._vao.create()
            self._vao.bind()
            self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            self._vbo.create()
            self._vbo.bind()
            verts = struct.pack("8f", -1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
            self._vbo.allocate(verts, len(verts))
            program.bind()
            program.enableAttributeArray(0)
            program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 0)
            self._vbo.release()
            self._vao.release()
        except Exception as exc:
            self._program = None
            print("OpenGL 初始化失败:", exc)

    def start_preview(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def start_benchmark(self, frames_total: int = 600) -> None:
        if self._running:
            return
        half = max(60, int(frames_total) // 2)
        self._config = [(96, half), (384, half)]
        self._stage = 0
        self._frame = 0
        self._total_frames = 0
        self._apply_stage()
        self._elapsed.restart()
        self._running = True
        if not self._timer.isActive():
            self._timer.start()

    def request_stop(self) -> None:
        self._running = False

    def _apply_stage(self) -> None:
        it, frames = self._config[self._stage]
        self._stage_iter = it
        self._stage_frames = frames

    def _advance_stage(self) -> None:
        self._stage += 1
        if self._stage >= len(self._config):
            elapsed = self._elapsed.elapsed() / 1000.0
            avg = self._total_frames / max(elapsed, 1e-6)
            self._running = False
            self.benchProgress.emit(100, "完成")
            self.benchFinished.emit(avg, self._total_frames, elapsed)
        else:
            self._frame = 0
            self._apply_stage()
            self._elapsed.restart()
            self.benchProgress.emit(50, "第二阶段…")

    def _tick(self) -> None:
        if self._running:
            self._frame += 1
            self._total_frames += 1
            total = sum(f for _, f in self._config)
            pct = int(min(99, self._total_frames / max(1, total) * 100))
            self.benchProgress.emit(pct, f"渲染中 {self._total_frames}/{total}")
            if self._frame >= self._stage_frames:
                self._advance_stage()
        self.update()

    def paintGL(self) -> None:
        if self._gl is None:
            return
        self._gl.glClear(GL_COLOR_BUFFER_BIT)
        if self._program is None:
            return
        self._preview_time += 0.016
        self._vao.bind()
        self._program.bind()
        self._program.setUniformValue("uTime", float(self._preview_time))
        self._program.setUniformValue("uIter", float(self._stage_iter))
        self._gl.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        self._program.release()
        self._vao.release()

    def resizeGL(self, w: int, h: int) -> None:
        if self._gl is not None:
            self._gl.glViewport(0, 0, max(1, w), max(1, h))
