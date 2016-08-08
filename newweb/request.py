#!/usr/bin/python2.6
"""newWeb request module."""

# Standard modules
import cgi
import cStringIO
import Cookie as cookie
import re

# newWeb modules
from . import response


class Cookie(cookie.SimpleCookie):
  """Cookie class that uses the most specific value for a cookie name.

  According to RFC2965 (http://tools.ietf.org/html/rfc2965):
      If multiple cookies satisfy the criteria above, they are ordered in
      the Cookie header such that those with more specific Path attributes
      precede those with less specific.  Ordering with respect to other
      attributes (e.g., Domain) is unspecified.

  This class adds this behaviour to cookie parsing. That is, a key:value pair
  WILL NOT overwrite an already existing (and thus more specific) pair.

  N.B.: this class assumes the given cookie to follow the standards outlined in
  the RFC. At the moment (2011Q1) this assumption proves to be correct for both
  Chromium (and likely Webkit in general) and Firefox. Other browsers have not
  been testsed, and might possibly deviate from the suggested standard.
  As such, it's recommended not to re-use the cookie name with different values
  for different paths.
  """
  # Unfortunately this works by redefining a private method.
  def _BaseCookie__set(self, key, real_value, coded_value):
    """Inserts a morsel into the Cookie, strictly on the first occurrance."""
    if key not in self:
      morsel = cookie.Morsel()
      morsel.set(key, real_value, coded_value)
      dict.__setitem__(self, key, morsel)


class Request(object):
  def __init__(self, env, registry):
    self.env = env
    self.headers = dict(self.headers_from_env(env))
    self.registry = registry
    self._out_headers = []
    self._out_status = 200
    self._response = None

    # `self.vars` setup, will contain keys 'cookie', 'get' and 'post'
    self.vars = {'cookie': dict((name, value.value) for name, value in
                                Cookie(self.env.get('HTTP_COOKIE')).items()),
                 'get': QueryArgsDict(cgi.parse_qs(self.env['QUERY_STRING']))}
    if self.env['REQUEST_METHOD'] == 'POST':
      self.vars['post'] = ParseForm(env['wsgi.input'], env)
    else:
      self.vars['post'] = IndexedFieldStorage()

  @property
  def path(self):
    try:
      return self.env['PATH_INFO'].decode('UTF8')
    except UnicodeDecodeError:
      return self.env['PATH_INFO']

  @property
  def method(self):
    try:
      return self.env['REQUEST_METHOD'].decode('UTF8')
    except UnicodeDecodeError:
      return self.env['REQUEST_METHOD']

  @property
  def response(self):
    if self._response is None:
      self._response = response.Response()
    return self._response

  def headers_from_env(self, env):
    for key, value in env.iteritems():
      if key.startswith('HTTP_'):
        yield key[5:].lower().replace('_', '-'), value

  def AddCookie(self, key, value, **attrs):
    """Adds a new cookie header to the repsonse.

    Arguments:
      @ key: str
        The name of the cookie.
      @ value: str
        The actual value to store in the cookie.
      % expires: str ~~ None
        The date + time when the cookie should expire. The format should be:
        "Wdy, DD-Mon-YYYY HH:MM:SS GMT" and the time specified in UTC.
        The default means the cookie never expires.
        N.B. Specifying both this and `max_age` leads to undefined behavior.
      % path: str ~~ '/'
        The path for which this cookie is valid. This default ('/') is different
        from the rule stated on Wikipedia: "If not specified, they default to
        the domain and path of the object that was requested".
      % domain: str ~~ None
        The domain for which the cookie is valid. The default is that of the
        requested domain.
      % max_age: int
        The number of seconds this cookie should be used for. After this period,
        the cookie should be deleted by the client.
        N.B. Specifying both this and `expires` leads to undefined behavior.
      % secure: boolean
        When True, the cookie is only used on https connections.
      % httponly: boolean
        When True, the cookie is only used for http(s) requests, and is not
        accessible through Javascript (DOM).
    """
    new_cookie = Cookie({key.encode('ascii'): value})
    if 'max_age' in attrs:
      attrs['max-age'] = attrs.pop('max_age')
    new_cookie[key].update(attrs)
    self.AddHeader('Set-Cookie', new_cookie[key].OutputString())

  def AddHeader(self, name, value):
    self.response.headers[name] = value


class IndexedFieldStorage(cgi.FieldStorage):
  """Adaption of cgi.FieldStorage with a few specific changes.

  Notable differences with cgi.FieldStorage:
    1) `environ.QUERY_STRING` does not add to the returned FieldStorage
       This way we maintain a strict separation between POST and GET variables.
    2) Field names in the form 'foo[bar]=baz' will generate a dictionary:
         foo = {'bar': 'baz'}
       Multiple statements of the form 'foo[%s]' will expand this dictionary.
       Multiple occurrances of 'foo[bar]' will result in unspecified behavior.
    3) Automatically attempts to parse all input as UTF8. This is the proposed
       standard as of 2005: http://tools.ietf.org/html/rfc3986.
  """
  FIELD_AS_ARRAY = re.compile(r'(.*)\[(.*)\]')
  def iteritems(self):
    return ((key, self.getlist(key)) for key in self)

  def items(self):
    return list(self.iteritems())

  def read_urlencoded(self):
    indexed = {}
    self.list = []
    for field, value in cgi.parse_qsl(self.fp.read(self.length),
                                      self.keep_blank_values,
                                      self.strict_parsing):
      if self.FIELD_AS_ARRAY.match(field):
        field_group, field_key = self.FIELD_AS_ARRAY.match(field).groups()
        indexed.setdefault(field_group, cgi.MiniFieldStorage(field_group, {}))
        indexed[field_group].value[field_key] = value.decode('utf8')
      else:
        self.list.append(cgi.MiniFieldStorage(field, value.decode('utf8')))
    self.list = indexed.values() + self.list
    self.skip_lines()


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


def ParseForm(file_handle, environ):
  """Returns an IndexedFieldStorage object from the POST data and environment.

  This small wrapper is necessary because cgi.FieldStorage assumes that the
  provided file handles supports .readline() iteration. File handles as provided
  by BaseHTTPServer do not support this, so we need to convert them to proper
  cStringIO objects first.
  """
  data = cStringIO.StringIO(file_handle.read(int(environ['CONTENT_LENGTH'])))
  return IndexedFieldStorage(fp=data, environ=environ)
