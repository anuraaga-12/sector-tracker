"""Minimal Streamlit stand-in used ONLY by tests/test_pages_smoke.py.

It lets every page script execute top-to-bottom without a browser so that pandas / logic
errors in the UI code are caught in CI. Widgets return their default value; selectboxes with
``index=None`` return the first option so drill-down code paths are exercised. Calls to
``format_func`` are made for every option to catch formatting errors.
"""
from __future__ import annotations

import types


class StopRun(Exception):
    pass


class SwitchPage(Exception):
    pass


class _SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


session_state = _SessionState()
query_params = {}
secrets = {}
CALLS: list[tuple] = []


def _record(name):
    def f(*a, **k):
        CALLS.append((name, a, k))
        return None
    return f


for _n in ("set_page_config", "markdown", "title", "header", "subheader", "caption", "write", "info", "warning",
           "error", "success", "divider", "code", "metric", "dataframe", "plotly_chart", "download_button",
           "json", "table", "latex", "toast", "balloons", "image"):
    globals()[_n] = _record(_n)


def _fmt(options, format_func):
    if format_func:
        for o in options:
            format_func(o)


def selectbox(label, options, index=0, format_func=None, placeholder=None, key=None, **kw):
    options = list(options)
    _fmt(options, format_func)
    if not options:
        return None
    if index is None:
        return None if session_state.get("_stub_no_drill", True) else options[0]
    return options[index]


def radio(label, options, index=0, format_func=None, **kw):
    options = list(options)
    _fmt(options, format_func)
    override = session_state.get("_stub_radio", {}).get(label)
    if override is not None:
        return override
    return options[index] if options else None


def multiselect(label, options, default=None, format_func=None, **kw):
    options = list(options)
    _fmt(options, format_func)
    return list(default) if default is not None else []


def slider(label, min_value=None, max_value=None, value=None, step=None, **kw):
    return value


def text_input(label, value="", **kw):
    return value


def toggle(label, value=False, **kw):
    return value


def checkbox(label, value=False, **kw):
    return value


def button(*a, **k):
    return False


def file_uploader(*a, **k):
    return None


def stop():
    raise StopRun()


def switch_page(page):
    raise SwitchPage(page)


def rerun():
    raise StopRun()


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return globals()[name]

    def update(self, *a, **k):
        return None


def columns(spec, **kw):
    n = spec if isinstance(spec, int) else len(spec)
    return [_Ctx() for _ in range(n)]


def tabs(labels):
    return [_Ctx() for _ in labels]


def expander(*a, **k):
    return _Ctx()


def container(*a, **k):
    return _Ctx()


def status(*a, **k):
    return _Ctx()


def spinner(*a, **k):
    return _Ctx()


sidebar = _Ctx()


class _Cache:
    def __call__(self, func=None, **kw):
        if func is None:
            return lambda f: f
        return func

    def clear(self):
        return None


cache_data = _Cache()
cache_resource = _Cache()


def _col(*a, **k):
    return {"args": a, **k}


column_config = types.SimpleNamespace(NumberColumn=_col, ProgressColumn=_col, TextColumn=_col, LinkColumn=_col,
                                      DateColumn=_col, Column=_col)
