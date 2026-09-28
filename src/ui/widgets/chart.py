"""实时曲线控件（QtCharts）。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QPainter, QPen


class RealtimeChart(QChartView):
    def __init__(
        self,
        series_defs: List[Tuple[str, str, str, str]],
        max_points: int = 120,
        y_left: Tuple[float, float] = (0.0, 100.0),
        y_right: Optional[Tuple[float, float]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._max = max(10, int(max_points))
        self._x = 0
        self._series: Dict[str, QLineSeries] = {}

        chart = QChart()
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setBackgroundBrush(QColor("#161b22"))
        chart.setMargins(QMargins(6, 6, 6, 6))
        chart.legend().setLabelColor(QColor("#c9d1d9"))
        chart.legend().setAlignment(Qt.AlignBottom)

        self._axis_x = QValueAxis()
        self._axis_x.setRange(0, self._max)
        self._axis_x.setLabelFormat("%d")
        self._axis_x.setLabelsColor(QColor("#8b949e"))
        self._axis_l = QValueAxis()
        self._axis_l.setRange(*y_left)
        self._axis_l.setLabelsColor(QColor("#8b949e"))
        chart.addAxis(self._axis_x, Qt.AlignBottom)
        chart.addAxis(self._axis_l, Qt.AlignLeft)

        self._axis_r: Optional[QValueAxis] = None
        if y_right:
            self._axis_r = QValueAxis()
            self._axis_r.setRange(*y_right)
            self._axis_r.setLabelsColor(QColor("#8b949e"))
            chart.addAxis(self._axis_r, Qt.AlignRight)

        for key, label, color, axis in series_defs:
            series = QLineSeries()
            series.setName(label)
            pen = QPen(QColor(color))
            pen.setWidthF(1.6)
            series.setPen(pen)
            chart.addSeries(series)
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_l if axis == "left" else (self._axis_r or self._axis_l))
            self._series[key] = series

        self.setChart(chart)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(200)

    def reset(self) -> None:
        self._x = 0
        for series in self._series.values():
            series.clear()
        self._axis_x.setRange(0, self._max)

    def append(self, values: Dict[str, Optional[float]]) -> None:
        self._x += 1
        for key, series in self._series.items():
            value = values.get(key)
            if value is None:
                count = series.count()
                if count:
                    series.append(self._x, series.at(count - 1).y())
                continue
            series.append(self._x, float(value))
        if self._x > self._max:
            axis_min = self._x - self._max
            self._axis_x.setRange(axis_min, self._x)
            for series in self._series.values():
                while series.count() and series.at(0).x() < axis_min:
                    series.remove(0)
