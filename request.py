#!/usr/bin/python2.6
"""Underdark micro-Web framework, uWeb, Request module."""

__author__ = 'Elmer de Looff <elmer@underdark.nl>'
__version__ = '0.5'

# Standard modules
import cgi
import Cookie
import os
import re
import socket
import urllib

# Custom modules
#from underdark.libs import logging


class Request(object):
  def __init__(self, request):
    self._request = request
    if hasattr(request, 'path'):
      self._modpython = False
      self.env = EnvironBaseHttp(request)
      self.headers = request.headers
      self._out_headers = []
      self._out_status = 200
      post_data_fp = request.rfile
    else:
      self._modpython = True
      self.env = EnvironModPython(request)
      self.headers = request.headers_in
      post_data_fp = request

    # `self.vars` setup, will contain keys 'cookie', 'get' and 'post'
    self.vars = {'cookie': ExtractCookies(self.env.get('HTTP_COOKIE')),
                 'get': QueryArgsDict(cgi.parse_qs(self.env['QUERY_STRING']))}
    if self.env['REQUEST_METHOD'] == 'POST':
      self.vars['post'] = IndexedFieldStorage(post_data_fp, environ=self.env)
    else:
      self.vars['post'] = IndexedFieldStorage()

  def AddCookie(self, key, value, **attrs):
    cookie = Cookie.SimpleCookie({key: value})
    if 'max_age' in attrs:
      attrs['max-age'] = attrs.pop('max_age')
    cookie[key].update(attrs)
    self.AddHeader('Set-Cookie', cookie[key].OutputString())

  def AddHeader(self, name, value):
    if self._modpython:
      self._request.headers_out.add(name, value)
    else:
      self._out_headers.append((name, value))

  def ExtendedEnvironment(self):
    if self._modpython:
      return ExtendEnvironModPython(self.env, self._request)
    else:
      return ExtendEnvironBaseHttp(self.env, self._request)

  def SetContentType(self, content_type):
    """Sets outgoing header 'content-type' to the given value."""
    if self._modpython:
      self._request.content_type = content_type
    else:
      self.AddHeader('content-type', content_type)

  def SetHttpStatus(self, http_status_code):
    if self._modpython:
      self._request.status = http_status_code
    else:
      self._out_status = http_status_code

  def Write(self, data):
    """Writes the HTTP reply to the requesting party.

    N.B. For the BaseHTTP variant, this is where status and headers are written.
    """
    if self._modpython:
      self._request.write(data)
    else:
      self._request.send_response(self._out_status)
      for name, value in self._out_headers:
        self._request.send_header(name, value)
      self._request.end_headers()
      self._request.wfile.write(data)


class IndexedFieldStorage(cgi.FieldStorage):
  """Adaption of cgi.FieldStorage with a few specific changes.

  Notable differences with cgi.FieldStorage:
    1) `environ.QUERY_STRING` does not add to the returned FieldStorage
       This way we maintain a strict separation between POST and GET variables.
    2) Field names in the form 'foo[bar]=baz' will generate a dictionary:
         foo = {'bar': 'baz'}
       Multiple statements of the form 'foo[%s]' will expand this dictionary.
       Multiple occurrances of 'foo[bar]' will result in unspecified behavior.
  """
  FIELD_AS_ARRAY = re.compile(r'(.*)\[(.*)\]')
  def read_urlencoded(self):
    self.qs_on_post = ''  # We do NOT parse QUERY_STRING in our FIELD_STORAGE.
    previous_len = len(self.list) if self.list else 0
    cgi.FieldStorage.read_urlencoded(self) # OLD class, damnit!
    new_form_fields = self.list[previous_len:]
    del self.list[previous_len:]

    new_fields = {}
    for field in new_form_fields:
      if self.FIELD_AS_ARRAY.match(field.name):
        field_group, field_key = self.FIELD_AS_ARRAY.match(field.name).groups()
        new_fields.setdefault(
            field_group, cgi.MiniFieldStorage(field_group, {}))
        new_fields[field_group].value[field_key] = field.value
      else:
        self.list.append(field)
    self.list.extend(new_fields.values())


class QueryArgsDict(dict):
  def getfirst(self, key, default=None):
    """Returns the first value for the requested key, or a fallback value."""
    try:
      return self[key][0]
    except KeyError:
      return default

  def getlist(self, key):
    """Returns a list with all values that were given for the requested key.

    N.B. If the given key does not exist, an empty list is returned.
    """
    try:
      return self[key]
    except KeyError:
      return []


def EnvironBaseHttp(request):
  path_info, _sep, query_string = request.path.partition('?')
  return {'CONTENT_TYPE': request.headers.get('content-type', ''),
          'CONTENT_LENGTH': request.headers.get('content-length', 0),
          'HTTP_COOKIE': request.headers.get('cookie', ''),
          'HTTP_HOST': request.headers.get('host', ''),
          'HTTP_REFERER': request.headers.get('referer', ''),
          'HTTP_USER_AGENT': request.headers.get('user-agent', ''),
          'PATH_INFO': urllib.unquote_plus(path_info),
          'QUERY_STRING': query_string,
          'REMOTE_ADDR': request.client_address[0],
          'REQUEST_METHOD': request.command,
          'UWEB_MODE': 'BASE_HTTP'}


def EnvironModPython(request):
  return {'CONTENT_TYPE': request.headers_in.get('content-type', ''),
          'CONTENT_LENGTH': request.headers_in.get('content-length', 0),
          'HTTP_COOKIE': request.headers_in.get('cookie', ''),
          'HTTP_HOST': request.hostname,
          'HTTP_REFERER': request.headers_in.get('referer', ''),
          'HTTP_USER_AGENT': request.headers_in.get('user-agent', ''),
          'PATH_INFO': urllib.unquote_plus(request.uri),
          'QUERY_STRING': request.args or '',
          'REMOTE_ADDR': request.connection.remote_ip,
          'REQUEST_METHOD': request.method,
          'UWEB_MODE': 'MOD_PYTHON'}


def ExtendEnvironBaseHttp(environ, request):
  environ.update(
      {'AUTH_TYPE': None,
       'CONNECTION_ID': None,
       'DOCUMENT_ROOT': os.getcwd(),
       'RAW_REQUEST': request.raw_requestline,
       'REMOTE_HOST': socket.getfqdn(environ['REMOTE_ADDR']),
       'REMOTE_USER': None,
       'SERVER_NAME': request.server.server_name,
       'SERVER_PORT': request.server.server_port,
       'SERVER_LOCAL_NAME': socket.gethostname(),
       'SERVER_LOCAL_IP': GetLocalIp(environ['REMOTE_ADDR']),
       'SERVER_PROTOCOL': request.request_version})
  return HeadersIntoEnviron(environ, request.headers)


def ExtendEnvironModPython(environ, request):
  environ.update(
      {'AUTH_TYPE': request.ap_auth_type,
       'CONNECTION_ID': request.connection.id,
       'DOCUMENT_ROOT': request.document_root(),
       'RAW_REQUEST': request.the_request,
       'REMOTE_HOST': socket.getfqdn(environ['REMOTE_ADDR']),
       'REMOTE_USER': request.user,
       'SERVER_NAME': request.server.server_hostname,
       'SERVER_PORT': request.connection.local_addr[1],
       'SERVER_LOCAL_NAME': socket.gethostname(),
       'SERVER_LOCAL_IP': request.connection.local_ip,
       'SERVER_PROTOCOL': request.protocol,
       # Some specific mod_python love
       'MODPYTHON_HANDLER': request.handler,
       'MODPYTHON_INTERPRETER': request.interpreter,
       'MODPYTHON_PHASE': request.phase})
  return HeadersIntoEnviron(environ, request.headers_in)


def GetLocalIp(remote_addr):
  """Returns the local IP address of the server.

  BaseHTTP itself only knows the IP address it's bound to. This is likely to be
  a bogus address, such as '0.0.0.0'. Unfortunately, with BaseHTTP, it's
  impossible to know which internal address rreceived the incoming request.

  What is done to make a best guess:
  - A UDP socket to the `remote_addr` is set up. Opening a UDP socket does not
    initiate a handshake, transfers no data, and is super-fast.
  - The name of the socket is retrieved, which is the local address and port.

  Arguments:
    @ remote_addr: str
      The content of the REMOTE_ADDR as present in the requests' environment.

  Returns:
    str: the local IP address, dot separated.
  """
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  # The port is irrelevant as we're not going to transfer any data.
  sock.connect((remote_addr, 80))
  return sock.getsockname()[0]


def HeadersIntoEnviron(environ, headers, skip_pre_existing_http=True):
  """Adds the headers into the environment.

  If a header is already present, it's skipped, otherwise it's added with a
  leading 'HTTP_'.

  Arguments:
    @ environ: dict
      Dictionary of environment variables as (roughly) defined in CGI spec.
    @ headers: dict-like
      Dictionary of HTTP-response headers. Any object with a tuple-iterator
      on .items() method will do.
    % skip_pre_existing_http: boolean ~~ True
      A list of pre-existing 'HTTP_*' environment vars is made, and any headers
      that match, will *not* be added to the environment again.

  Returns
   dict: the environ as passed in, with added HTTP environment variables.
  """
  pre_existing_http = ()
  if skip_pre_existing_http:
    pre_existing_http = set(var[5:] for var in environ if var[:5] == 'HTTP_')
  for name, value in headers.items():
    name = name.replace('-', '_').upper()
    if name in environ or name in pre_existing_http:
      continue  # Skip headers we already have in environ
    if 'HTTP_' + name in environ:
      # Comma-separate headers that occur more than once
      environ['HTTP_' + name] += ',' + value
    else:
      environ['HTTP_' + name] = value
  return environ


def ExtractCookies(raw_cookie):
  """Returns a SimpleCookie based on the raw cookie string received."""
  if isinstance(raw_cookie, list):
    raw_cookie = ';'.join(raw_cookie)
  return Cookie.SimpleCookie(raw_cookie)
