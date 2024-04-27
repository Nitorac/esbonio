from typing import Any
from typing import Dict
from typing import Optional
from urllib.parse import urlencode

from lsprotocol import types

from esbonio import server
from esbonio.server import Uri
from esbonio.server.features.project_manager import ProjectManager
from esbonio.server.features.sphinx_manager import SphinxClient
from esbonio.server.features.sphinx_manager import SphinxManager

from .config import PreviewConfig
from .preview import PreviewServer
from .preview import make_http_server
from .webview import WebviewServer
from .webview import make_ws_server


class PreviewManager(server.LanguageFeature):
    """Language feature for managing previews."""

    def __init__(
        self,
        server: server.EsbonioLanguageServer,
        sphinx: SphinxManager,
        projects: ProjectManager,
    ):
        super().__init__(server)
        self.sphinx = sphinx
        self.sphinx.add_listener("build", self.on_build)
        """The sphinx manager."""

        self.config = PreviewConfig()
        """The current configuration."""

        self.projects = projects
        """The project manager."""

        self.preview: Optional[PreviewServer] = None
        """The http server for serving the built files"""

        self.webview: Optional[WebviewServer] = None
        """The server for controlling the webview."""

    def initialized(self, params: types.InitializedParams):
        """Called once the initial handshake between client and server has finished."""
        self.configuration.subscribe(
            "esbonio.preview", PreviewConfig, self.update_configuration
        )

    def shutdown(self, params: None):
        """Called when the client instructs the server to ``shutdown``."""

        if self.preview is not None:
            self.preview.stop()

        if self.webview is not None:
            self.webview.stop()

    @property
    def preview_active(self) -> bool:
        """Return true if the preview is active.

        i.e. there is a HTTP server hosting the build result."""
        return self.preview is not None

    @property
    def preview_controllable(self) -> bool:
        """Return true if the preview is controllable.

        i.e. there is a web socket server available to control the webview.
        """
        return self.webview is not None

    def update_configuration(self, event: server.ConfigChangeEvent[PreviewConfig]):
        """Called when the user's configuration is updated."""
        config = event.value

        # (Re)create the websocket server
        if self.webview is None:
            self.webview = make_ws_server(self.server, config)

        elif (
            config.bind != self.webview.config.bind
            or config.ws_port != self.webview.config.ws_port
        ):
            self.webview.stop()
            self.webview = make_ws_server(self.server, config)

        # (Re)create the http server
        if self.preview is None:
            self.preview = make_http_server(self.server, config)

        elif (
            config.bind != self.preview.config.bind
            or config.http_port != self.preview.config.http_port
        ):
            self.preview.stop()
            self.preview = make_http_server(self.server, config)

        self.config = config

    async def on_build(self, client: SphinxClient, result):
        """Called whenever a sphinx build completes."""

        if self.webview is None or self.preview is None:
            return

        # Only refresh the view if the project we are previewing was built.
        if client.build_uri != self.preview.build_uri:
            return

        self.logger.debug("Refreshing preview")
        self.webview.reload()

    async def scroll_view(self, line: int):
        """Scroll the webview to the given line number."""

        if self.webview is None:
            return

        self.webview.scroll(line)

    async def preview_file(self, params):
        if self.webview is None or self.preview is None:
            return None

        # Always check the fully resolved uri.
        src_uri = Uri.parse(params["uri"]).resolve()
        self.logger.debug("Previewing file: '%s'", src_uri)

        if (client := await self.sphinx.get_client(src_uri)) is None:
            return None

        if (project := self.projects.get_project(src_uri)) is None:
            return None

        if (build_path := await project.get_build_path(src_uri)) is None:
            self.logger.debug(
                "Unable to preview file '%s', not included in build output.", src_uri
            )
            return None

        server = await self.preview
        webview = await self.webview

        self.preview.build_uri = client.build_uri
        query_params: Dict[str, Any] = dict(ws=webview.port)

        if self.config.show_line_markers:
            query_params["show-markers"] = True

        uri = Uri.create(
            scheme="http",
            authority=f"localhost:{server.port}",
            path=build_path,
            query=urlencode(query_params),
        )

        self.logger.info("Preview available at: %s", uri.as_string(encode=False))
        return {"uri": uri.as_string(encode=False)}


def esbonio_setup(
    esbonio: server.EsbonioLanguageServer,
    sphinx: SphinxManager,
    projects: ProjectManager,
):
    manager = PreviewManager(esbonio, sphinx, projects)
    esbonio.add_feature(manager)

    @esbonio.feature("view/scroll")
    async def on_scroll(ls: server.EsbonioLanguageServer, params):
        await manager.scroll_view(params.line)

    @esbonio.command("esbonio.server.previewFile")
    async def preview_file(ls: server.EsbonioLanguageServer, *args):
        return await manager.preview_file(args[0][0])
