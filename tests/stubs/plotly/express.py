from .graph_objects import Figure


def _fig(data_frame=None, *a, **k):
    for key in ("x", "y", "color", "size", "text"):
        col = k.get(key)
        if isinstance(col, str) and data_frame is not None and col not in data_frame.columns:
            raise KeyError(f"plotly.express stub: column {col!r} not in frame")
    return Figure()


bar = scatter = line = area = histogram = imshow = _fig
