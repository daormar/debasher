from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class PageFiles(StaticFiles):
    """
    The files of the built frontend, served so that the browser asks the
    backend again each time it opens the page: it keeps its copy, and checks
    with the ETag that it is still the one installed. Without this, a browser
    may take the page from its cache without asking, for longer the older the
    page is, and show the web UI of a version that has been replaced since;
    the token after "#" in the address is not part of the request and does
    not make it ask.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
