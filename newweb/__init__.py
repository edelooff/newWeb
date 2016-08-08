#!/usr/bin/python
"""newWeb Framework"""

__version__ = '0.4.0-dev'

# Standard modules
import ConfigParser
import logging
import os
import re
import sys
from wsgiref.simple_server import make_server

# Add the ext_lib directory to the path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), 'ext_lib')))

# Package modules
from . import pagemaker
from . import request

# Package classes
from .response import Response
from .response import Redirect
from .pagemaker import PageMaker
from .pagemaker import DebuggingPageMaker


class Error(Exception):
  """Superclass used for inheritance and external excepion handling."""


class ImmediateResponse(Exception):
  """Used to trigger an immediate repsonse, foregoing the regular returns."""


class NoRouteError(Error):
  """The server does not know how to route this request"""


class Registry(object):
  """Something to hook stuff to"""


class NewWeb(object):
  """Returns a configured closure for handling page requests.

  This closure is configured with a precomputed set of routes and handlers using
  the Router function. After this, incoming requests are processed and delegated
  to the correct PageMaker handler.

  The url in the received `req` object is taken and matches against the
  `router`` (refer to Router() for more documentation on this).


  Takes:
    @ page_class: PageMaker
      Class that holds request handling methods as defined in the `routes`
    @ router: request router
      The result of the Router() function.
    @ config: dict
      Configuration for the PageMaker. Typically contains entries for database
      connections, default search paths etc.

  Returns:
    RequestHandler: Configured closure that is ready to process requests.
  """
  def __init__(self, page_class, routes, config):
    self.page_class = page_class
    self.registry = Registry()
    self.registry.logger = logging.getLogger('root')
    self.router = router(routes)
    self.config = config if config is not None else {}

  def __call__(self, env, start_response):
    """WSGI request handler.

    Accpepts the WSGI `environment` dictionary and a function to start the
    response and returns a response iterator.
    """
    req = request.Request(env, self.registry)
    page_maker = self.page_class(req, config=self.config)
    response = self.get_response(page_maker, req.path, req.method)
    if not isinstance(response, Response):
      req.response.text = response
      response = req.response
    start_response(response.status, response.headerlist)
    yield response.content

  def get_response(self, page_maker, path, method):
    try:
      # We're specifically calling _PostInit here as promised in documentation.
      # pylint: disable=W0212
      page_maker._PostInit()
      # pylint: enable=W0212
      handler, args = self.router(path, method)
      return getattr(page_maker, handler)(*args)
    except pagemaker.ReloadModules, message:
      reload_message = reload(sys.modules[self.page_class.__module__])
      return Response(content='%s\n%s' % (message, reload_message))
    except ImmediateResponse as err:
      return err[0]
    except (NoRouteError, Exception):
      return page_maker.InternalServerError(*sys.exc_info())

  def serve(self):
    """Sets up and starts WSGI development server for the current app."""
    host = self.config['development'].get('host', 'localhost')
    port = self.config['development'].get('port', 8001)
    server = make_server(host, int(port), self)
    print 'Running server on http://%s:%s' % server.server_address
    server.serve_forever()


def read_config(config_file):
  """Parses the given `config_file` and returns it as a nested dictionary."""
  parser = ConfigParser.SafeConfigParser()
  try:
    parser.read(config_file)
  except ConfigParser.ParsingError:
    raise ValueError('Not a valid config file: %r.' % config_file)
  return dict((section, dict(parser.items(section)))
              for section in parser.sections())


def router(routes):
  """Returns the first request handler that matches the request URL.

  The `routes` argument is an iterable of 3-tuples, each of which contain a
  pattern (regex), request methods and the name of the handler to use for matching requests.

  Before returning the closure, all regexes are compiled, and handler methods
  are retrieved from the provided `page_class`.

  Arguments:
    @ routes: iterable of 3-tuples.
      Each tuple is a set of `pattern`, `methods` and `handler`, all are strings.

  Returns:
    request_router: Configured closure that processes urls.
  """
  req_routes = []
  default_methods = {'GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'}
  for route in routes:
    try:
      pattern, methods, handler = route
    except ValueError:
      pattern, handler = route
      methods = default_routes
    req_routes.append((re.compile(pattern + '$', re.UNICODE), methods, handler))

  def request_router(url, method):
    """Returns the appropriate handler and arguments for the given `url`.

    The`url` is matched against the compiled patterns in the `req_routes`
    provided by the outer scope. Upon finding a pattern that matches, the
    match groups from the regex and the unbound handler method are returned.

    N.B. The rules are such that the first matching route will be used. There
    is no further concept of specificity. Routes should be written with this in
    mind.

    Arguments:
      @ url: str
        The URL requested by the client.

    Raises:
      NoRouteError: None of the patterns match the requested `url`.

    Returns:
      2-tuple: handler method (unbound), and tuple of pattern matches.
    """
    for pattern, methods, handler in req_routes:
      match = pattern.match(url)
      if match and (method in methods):
        return handler, match.groups()
    raise NoRouteError(url +' cannot be handled')
  return request_router
