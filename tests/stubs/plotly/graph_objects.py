class _Trace:
    def __init__(self, *a, **k):
        self.kwargs = k


class Figure:
    def __init__(self, data=None, **k):
        self.data = [data] if data is not None else []

    def add_trace(self, trace, row=None, col=None, **k):
        self.data.append(trace)
        return self

    def _noop(self, *a, **k):
        return self

    update_layout = update_xaxes = update_yaxes = update_traces = add_shape = add_annotation = _noop
    add_vline = add_hline = _noop


def __getattr__(name):  # go.Scatter, go.Bar, go.Heatmap, go.Candlestick, …
    return _Trace


class _Layout:
    Template = _Trace


layout = _Layout()
