"""
Async helpers for DRF APIViews / ViewSets under ASGI.

Design goals:
- Keep request workers non-blocking: ORM and other sync I/O run in
  threadpool via ``sync_to_async`` (thread_sensitive=True for Django ORM).
- Heavy work (Docker deploy, builds) must NEVER run in the request path;
  always enqueue Celery and return 202/200 with task id.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, TypeVar

from asgiref.sync import sync_to_async

F = TypeVar("F", bound=Callable[..., Any])


def async_to_thread(fn: F) -> F:
    """Run a sync callable in the ASGI threadpool (Django-ORM safe)."""
    return sync_to_async(fn, thread_sensitive=True)  # type: ignore[return-value]


def as_async_action(method: Callable) -> Callable:
    """
    Decorator: turn a sync DRF action into an async one that offloads the
    body to the threadpool. Safe to apply multiple times (idempotent).
    """
    if getattr(method, "_async_api_wrapped", False):
        return method
    if inspect.iscoroutinefunction(method):
        method._async_api_wrapped = True  # type: ignore[attr-defined]
        return method

    @functools.wraps(method)
    async def async_wrapper(self, *args, **kwargs):
        return await sync_to_async(method, thread_sensitive=True)(self, *args, **kwargs)

    async_wrapper._async_api_wrapped = True  # type: ignore[attr-defined]
    return async_wrapper


def as_async_api_view(fn: Callable) -> Callable:
    """Same as as_async_action but for function-based @api_view handlers."""
    if getattr(fn, "_async_api_wrapped", False):
        return fn
    if inspect.iscoroutinefunction(fn):
        fn._async_api_wrapped = True  # type: ignore[attr-defined]
        return fn

    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        return await sync_to_async(fn, thread_sensitive=True)(*args, **kwargs)

    async_wrapper._async_api_wrapped = True  # type: ignore[attr-defined]
    return async_wrapper


class AsyncAPIViewMixin:
    """
    Mixin for APIView / ViewSet subclasses.

    After the class body is created, call ``AsyncAPIViewMixin.wrap_handlers(cls)``
    (done automatically by ``async_api_view`` class decorator) to convert
    HTTP handlers to async threadpool wrappers.
    """

    _ASYNC_HANDLER_NAMES = frozenset(
        {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "head",
            "options",
            "trace",
            "list",
            "create",
            "retrieve",
            "update",
            "partial_update",
            "destroy",
        }
    )

    @classmethod
    def wrap_handlers(cls, target: type) -> type:
        for name in list(cls._ASYNC_HANDLER_NAMES):
            if name not in target.__dict__:
                continue
            attr = target.__dict__[name]
            if not callable(attr):
                continue
            if inspect.iscoroutinefunction(attr):
                continue
            setattr(target, name, as_async_action(attr))
        # Also wrap custom @action methods that are defined on the class
        for name, attr in list(target.__dict__.items()):
            if name.startswith("_") or name in cls._ASYNC_HANDLER_NAMES:
                continue
            if not callable(attr):
                continue
            # DRF @action sets mapping / detail / methods attributes
            if getattr(attr, "mapping", None) is not None or getattr(attr, "detail", None) is not None:
                if not inspect.iscoroutinefunction(attr):
                    setattr(target, name, as_async_action(attr))
        return target


def async_api_view(cls: type) -> type:
    """Class decorator: wrap all HTTP / ViewSet handlers as async."""
    return AsyncAPIViewMixin.wrap_handlers(cls)


def enqueue_deploy_task(task, *args, **kwargs):
    """
    Fire-and-forget Celery dispatch. Never call .get() in the request path.
    Returns (AsyncResult, task_id).
    """
    async_result = task.apply_async(args=args, kwargs=kwargs)
    return async_result, getattr(async_result, "id", None)