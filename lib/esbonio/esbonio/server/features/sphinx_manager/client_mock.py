from __future__ import annotations

import asyncio
import typing
from typing import Dict
from typing import Optional
from typing import Union

from esbonio.sphinx_agent import types

if typing.TYPE_CHECKING:
    from esbonio.server import Uri

    from .client import SphinxClient
    from .manager import SphinxManager


class MockSphinxClient:
    """A mock SphinxClient implementation, used for testing."""

    def __init__(
        self,
        create_result: Union[types.SphinxInfo, Exception],
        build_result: Optional[Union[types.BuildResult, Exception]] = None,
        build_file_map: Optional[Dict[Uri, str]] = None,
        startup_delay: float = 0.5,
    ):
        """Create a new instance.

        Parameters
        ----------
        create_result
           The result to return when calling ``create_application``.
           If an exception is given it will be raised.

        build_result
           The result to return when calling ``build``.
           If an exception is given it will be raised.

        build_file_map
           The build file map to use.

        startup_delay
           The duration to sleep for when calling ``start``
        """
        self._create_result = create_result
        self._startup_delay = startup_delay
        self._build_result = build_result or types.BuildResult()

        self.building = False
        self.build_file_map = build_file_map or {}

    async def start(self, *args, **kwargs):
        await asyncio.sleep(self._startup_delay)

    async def stop(self, *args, **kwargs):
        pass

    async def create_application(self, *args, **kwargs) -> types.SphinxInfo:
        """Create an application."""

        if isinstance(self._create_result, Exception):
            raise self._create_result

        return self._create_result

    async def build(self, *args, **kwargs) -> types.BuildResult:
        """Trigger a build"""

        if isinstance(self._build_result, Exception):
            raise self._build_result

        return self._build_result


def mock_sphinx_client_factory(client: Optional[SphinxClient] = None):
    """Return a factory function that can be used with a ``SphinxManager`` instance."""

    def factory(manager: SphinxManager):
        if client is None:
            raise RuntimeError("Unexpected client creation")
        return client

    return factory
