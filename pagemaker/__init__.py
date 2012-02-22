#!/usr/bin/python
"""Underdark uWeb PageMaker class and its various Mixins."""
from __future__ import with_statement

__author__ = 'Elmer de Looff <elmer@underdark.nl>'
__version__ = '0.11'

# Standard modules
import datetime
import mimetypes
import os
import sys
import threading
import warnings

# Custom modules
from underdark.libs import logging
from underdark.libs import pysession

# Package modules
from .. import templateparser

__all__ = 'PageMaker', 'DebuggingPageMaker', 'Response', 'ReloadModules'
RFC_1123_DATE = '%a, %d %b %Y %T GMT'


class CacheStorage(object):
  """A semi-persistent storage with dict-like interface."""
  def __init__(self):
    super(CacheStorage, self).__init__()
    self._dict = {}
    self._lock = threading.RLock()

  def __contains__(self, key):
    return key in self._dict

  def Get(self, key, *default):
    """Returns the current value for `key`, or the `default` if it doesn't."""
    with self._lock:
      if len(default) > 1:
        raise ValueError('Only one default value accepted')
      try:
        return self._dict[key]
      except KeyError:
        if default:
          return default[0]
        raise

  def Set(self, key, value):
    """Sets the `key` in the dictionary storage to `value`."""
    self._dict[key] = value

  def SetDefault(self, key, default=None):
    """Returns the value for `key` or sets it to `default` if it doesn't exist.

    Arguments:
      @ key: obj
        The key to retrieve from the dictionary storage.
      @ default: obj ~~ None
        The default new value for the given key if it doesn't exist yet.
    """
    with self._lock:
      return self._dict.setdefault(key, default)


class MimeTypeDict(dict):
  """Dictionary that defines special behavior for mimetypes.

  Mimetypes (of typical form "type/subtype") are stored as (type, subtype) keys.
  This allows grouping of types to happen, and fallbacks to occur.

  The following is a typical complete MIMEType example:
    >>> mime_type_dict['text/html'] = 'HTML content'

  One could also define a default for the whole type, as follows:
    >>> mime_type_dict['text/*'] = 'Default'

  Looking up a type/subtype that doesn't exist, but for which a bare type does,
  will result in the value for the bare type to be returned:
    >>> mime_type_dict['text/nonexistant']
    'Default'
  """
  def __init__(self, data=(), **kwds):
    super(MimeTypeDict, self).__init__()
    if data:
      self.update(data)
    if kwds:
      self.update(**kwds)

  @staticmethod
  def MimeSplit(mime):
    """Split up a MIMEtype in a type and subtype, return as tuple.

    When the subtype if undefined or '*', only the type is returned, as 1-tuple.
    """
    mime_type, _sep, mime_subtype = mime.lower().partition('/')
    if not mime_subtype or mime_subtype == '*':
      return mime_type,  # 1-tuple
    return mime_type, mime_subtype

  def __setitem__(self, mime, value):
    super(MimeTypeDict, self).__setitem__(self.MimeSplit(mime), value)

  def __getitem__(self, mime):
    parsed_mime = self.MimeSplit(mime)
    try:
      return super(MimeTypeDict, self).__getitem__(parsed_mime)
    except KeyError:
      try:
        return super(MimeTypeDict, self).__getitem__(parsed_mime[:1])
      except KeyError:
        raise KeyError('KeyError: %r' % mime)

  def get(self, mime, default=None):
    try:
      return self[mime]
    except KeyError:
      return default

  def update(self, data=None, **kwargs):
    """Update the dictionary with new values from another dictionary.

    Also takes values from an iterable object of pairwise data.
    """
    if data:
      try:
        for key, value in data.iteritems():
          self[key] = value
      except AttributeError:
        # Argument data is not a proper dict, treat it as an iterable of tuples.
        for key, value in data:
          self[key] = value
    if kwargs:
      self.update(kwargs)


class BasePageMaker(object):
  """Provides the base pagemaker methods for all the html generators."""
  # Constant for persistent storage accross requests. This will be accessible
  # by all threads of the same application (in the same Python process).
  PERSISTENT = CacheStorage()
  # Base paths for templates and public data. These are used in the PageMaker
  # classmethods that set up paths specific for that pagemaker.
  PUBLIC_DIR = 'www'
  TEMPLATE_DIR = 'templates'

  # Default Static() handler cache durations, per MIMEtype, in days
  CACHE_DURATION = MimeTypeDict({'text': 7, 'image': 30, 'application': 7})

  def __init__(self, req, config=None):
    """sets up the template parser and database connections

    Arguments:
      @ req: request.Request
        The originating request, including environment, GET, POST and cookies.
      % config: dict ~~ None
        Configuration for the pagemaker, with database connection information
        and other settings. This will be available through `self.options`.
    """
    self.__SetupPaths()
    self.req = req
    self.cookies = req.vars['cookie']
    self.get = req.vars['get']
    self.post = req.vars['post']
    self.options = config or {}
    self.persistent = self.PERSISTENT

  def _PostInit(self):
    """Method that gets called for derived classes of BasePageMaker."""

  @classmethod
  def __SetupPaths(cls):
    """This sets up the correct paths for the PageMaker subclasses.

    From the passed in `cls`, it retrieves the filename. Of that path, the
    directory is used as the working directory. Then, the module constants
    PUBLIC_DIR and TEMPLATE_DIR are used to define class constants from.
    """
    # Unfortunately, mod_python does not always support retrieving the caller
    # filename using sys.modules. In those cases we need to query the stack.
    # pylint: disable=W0212
    try:
      local_file = sys.modules[cls.__module__].__file__
    except KeyError:
      frame = sys._getframe()
      initial = frame.f_code.co_filename
      # pylint: enable=W0212
      while initial == frame.f_code.co_filename:
        if not frame.f_back:
          break  # This happens during exception handling of DebuggingPageMaker
        frame = frame.f_back
      local_file = frame.f_code.co_filename
    cls.LOCAL_DIR = cls_dir = os.path.dirname(local_file)
    cls.PUBLIC_DIR = os.path.join(cls_dir, cls.PUBLIC_DIR)
    cls.TEMPLATE_DIR = os.path.join(cls_dir, cls.TEMPLATE_DIR)

  @property
  def parser(self):
    """Provides a templateparser.Parser instance.

    If the config file specificied a [templates] section and a `path` is
    assigned in there, this path will be used.
    Otherwise, the `TEMPLATE_DIR` will be used to load templates from.
    """
    if '__parser' not in self.persistent:
      self.persistent.Set('__parser', templateparser.Parser(
          self.options.get('templates', {}).get('path', self.TEMPLATE_DIR)))
    return self.persistent.Get('__parser')

  def InternalServerError(self, exc_type, exc_value, traceback):
    """Returns a plain text notification about an internal server error."""
    error = 'INTERNAL SERVER ERROR (HTTP 500) DURING PROCESSING OF %r' % (
                self.req.env['PATH_INFO'])
    logging.LogError(error, exc_info=(exc_type, exc_value, traceback))
    return Response(content=error, content_type='text/plain', httpcode=500)

  @staticmethod
  def Reload():
    """Raises `ReloadModules`, telling the Handler() to reload its pageclass."""
    raise ReloadModules('Reloading ... ')

  def Static(self, rel_path):
    """Provides a handler for static content.

    The requested `path` is truncated against a root (removing any uplevels),
    and then added to the working dir + PUBLIC_DIR. If the request file exists,
    then the requested file is retrieved, its mimetype guessed, and returned
    to the client performing the request.

    Should the requested file not exist, a 404 page is returned instead.

    Arguments:
      @ rel_path: str
        The filename relative to the working directory of the webserver.

    Returns:
      Page: contains the content and mimetype of the requested file, or a 404
            page if the file was not available on the local path.
    """
    rel_path = os.path.abspath(os.path.join(os.path.sep, rel_path))[1:]
    abs_path = os.path.join(self.PUBLIC_DIR, rel_path)
    try:
      with file(abs_path) as staticfile:
        content_type, _encoding = mimetypes.guess_type(abs_path)
        if not content_type:
          content_type = 'text/plain'
        cache_days = self.CACHE_DURATION.get(content_type, 0)
        expires = datetime.datetime.utcnow() + datetime.timedelta(cache_days)
        return Response(content=staticfile.read(),
                        content_type=content_type,
                        headers={'Expires': expires.strftime(RFC_1123_DATE)})
    except IOError:
      message = 'This is not the path you\'re looking for. No such file %r' % (
          self.req.env['PATH_INFO'])
      return Response(content=message,
                      content_type='text/plain',
                      httpcode=404)


class DebuggerMixin(object):
  """Replaces the default handler for Internal Server Errors.

  This one prints a host of debugging and request information, though it still
  lacks interactive functions.
  """
  CACHE_DURATION = MimeTypeDict({})
  ERROR_TEMPLATE = templateparser.Template.FromFile(os.path.join(
      os.path.dirname(__file__), 'http_500.xhtml'))

  def _ParseStackFrames(self, stack):
    """Generates list items for traceback information.

    Each traceback item contains the file- and function name, the line numer
    and the source that belongs with it. For each stack frame, the local
    variables are also added to it, allowing proper analysis to happen.

    This most likely doesn't need overriding / redefining in a subclass.

    Arguments:
      @ stack: traceback.stack
        The stack frames to return analysis on.

    Yields:
      str: Template-parsed HTML with frame information.
    """
    frames = []
    while stack:
      frame = stack.tb_frame
      frames.append({'file': frame.f_code.co_filename,
                     'scope': frame.f_code.co_name,
                     'locals': sorted(frame.f_locals.items()),
                     'source': self._SourceLines(
                         frame.f_code.co_filename, frame.f_lineno)})
      stack = stack.tb_next
    return reversed(frames)

  @staticmethod
  def _SourceLines(filename, line_num, context=3):
    """Yields the offending source line, and `context` lines of context.

    Arguments:
      @ filename: str
        The filename of the
      @ line_num: int
        The line number for the offending line.
      % context: int ~~ 3
        Number of lines context, before and after the offending line.

    Yields:
      str: Templated list-item for a source code line.
    """
    import linecache
    for line_num in xrange(line_num - context, line_num + context + 1):
      yield line_num, linecache.getline(filename, line_num)

  def InternalServerError(self, exc_type, exc_value, traceback):
    """Returns a HTTP 500 response with detailed failure analysis."""
    logging.LogError(
        'INTERNAL SERVER ERROR (HTTP 500) DURING PROCESSING OF %r',
        self.req.env['PATH_INFO'], exc_info=(exc_type, exc_value, traceback))
    return Response(
        httpcode=500,
        content=self.ERROR_TEMPLATE.Parse(
            cookies=[(cookie, self.cookies[cookie].value)
                     for cookie in sorted(self.cookies)],
            environ=sorted(self.req.ExtendedEnvironment().items()),
            query_args=[(var, self.get[var]) for var in sorted(self.get)],
            post_data=[(var, self.post.getlist(var))
                       for var in sorted(self.post)],
            exc={'type': exc_type, 'value': exc_value,
                 'traceback': self._ParseStackFrames(traceback)}))


class MongoMixin(object):
  """Adds MongoDB support to PageMaker."""
  @property
  def mongo(self):
    """Returns a MongoDB database connection."""
    if '__mongo' not in self.persistent:
      import pymongo
      mongo_config = self.options.get('mongo', {})
      connection = pymongo.connection.Connection(
          host=mongo_config.get('host'),
          port=mongo_config.get('port'))
      if 'database' in mongo_config:
        self.persistent.Set('__mongo', connection[mongo_config['database']])
      else:
        self.persistent.Set('__mongo', connection)
    return self.persistent.Get('__mongo')


class MysqlMixin(object):
  """Adds MySQL support to PageMaker."""
  @property
  def connection(self):
    """Returns a MySQL database connection."""
    if '__mysql' not in self.persistent:
      from underdark.libs.sqltalk import mysql
      mysql_config = self.options['mysql']
      self.persistent.Set('__mysql', mysql.Connect(
          host=mysql_config.get('host', 'localhost'),
          user=mysql_config.get('user'),
          passwd=mysql_config.get('password'),
          db=mysql_config.get('database'),
          charset=mysql_config.get('charset', 'utf8'),
          debug=DebuggerMixin in self.__class__.__mro__))
    return self.persistent.Get('__mysql')


class SqliteMixin(object):
  """Adds SQLite support to PageMaker."""
  @property
  def connection(self):
    """Returns an SQLite database connection."""
    if '__sqlite' not in self.persistent:
      from underdark.libs.sqltalk import sqlite
      self.persistent.Set('__sqlite', sqlite.Connect(
          self.options['sqlite']['database']))
    return self.persistent.Get('__sqlite')


class SessionMixin(object):
  """Adds pysession support to PageMaker."""
  def __init__(self, *args, **kwds):
    super(SessionMixin, self).__init__(*args, **kwds)
    self._userid = None

  @property
  def userid(self):
    """Provides the ID of the logged in user, if a valid session is available"""
    if self._userid is None:
      self._userid = self._GetSessionUserId()
    return self._userid

  def _GetSessionHandler(self):
    """Creates a session handler used to check sessions"""
    return pysession.Session(
        connection=self.connection,
        usertable='users',
        sessiontable='sessions',
        domain='true',
        remoteip=self.req['remote_addr'],
        columns={'user': 'emailaddress',
                 'password': 'password',
                 'useractive': 'status'},
        activestates='valid')

  def _GetSessionUserId(self):
    """Tries to validate a session by its cookiestring and IP address

    sets:
      self.options['login']: to True if logged in
      self.session['id']:    session id
      self.session['key']:   session password

    returns:
      True if logged in
      False if session is invalid
    """
    if 'session' not in self.cookies:
      return False
    raw_session = self.cookies.get['session'].value
    session_id, _sep, session_key = raw_session.partition(':')
    if not (session_id and session_key):
      return False
    try:
      session_handler = self._GetSessionHandler()
      session_handler.ResumeSession(session_id, session_key)
      return session_handler.userid
    except (pysession.SessionError, ValueError):
      return False


class SmorgasbordMixin(object):
  """Provides multiple-database connectivity.

  This enables a developer to use a single 'connection' property (`bord`) which
  can be used for regular relation database and MongoDB access. The caller will
  be given the relation database connection, unless Smorgasbord is aware of
  the caller's needs for another database connection.
  """
  class Connections(dict):
    """Connection autoloading class for Smorgasbord."""
    def __init__(self, pagemaker):
      super(SmorgasbordMixin.Connections, self).__init__()
      self.pagemaker = pagemaker

    def __getitem__(self, key):
      """Returns the requested database connection type.

      If the database connection type isn't locally available, it is retrieved
      using one of the _Load* methods.
      """
      try:
        return super(SmorgasbordMixin.Connections, self).__getitem__(key)
      except KeyError:
        return getattr(self, '_Load%s' % key.title())()

    def _LoadMongo(self):
      """Returns the PageMaker's MongoDB connection."""
      return self.pagemaker.mongo

    def _LoadRelational(self):
      """Returns the PageMaker's relational database connection."""
      return self.pagemaker.connection

  @property
  def bord(self):
    """Returns a Smorgasbord of autoloading database connections."""
    if '__bord' not in self.persistent:
      from .. import model
      self.persistent.Set('__bord', model.Smorgasbord(
          connections=SmorgasbordMixin.Connections(self)))
    return self.persistent.Get('__bord')


# ##############################################################################
# Classes for public use (wildcard import)
#
class ReloadModules(Exception):
  """Communicates the handler that it should reload the pageclass"""


class PageMaker(MysqlMixin, SessionMixin, BasePageMaker):
  """The basic PageMaker class, providing MySQL and Pysession support."""


class DebuggingPageMaker(DebuggerMixin, PageMaker):
  """The same basic PageMaker, with added debugging on HTTP 500."""


class Response(object):
  """Defines a full HTTP response.

  The full response consists of a required content part, and then optional
  http response code, cookies, additional headers, and a content-type.
  """
  # Default content-type for Page objects
  CONTENT_TYPE = 'text/html'

  def __init__(self, content='', content_type=CONTENT_TYPE,
               cookies=(), headers=None,  httpcode=200):
    """Initializes a Page object.

    Arguments:
      @ content: str
        The content to return to the client. This can be either plain text, html
        or the contents of a file (images for example).
      % content_type: str ~~ CONTENT_TYPE ('text/html' by default)
        The content type of the response. This should NOT be set in headers.
      % cookies: dict ~~ None
        Cookies are expected to be dictionaries, made up of the following keys:
        * Keys they MUST contain: `key`, `value`
        * Keys they MAY contain:  `expires`, `path`, `comment`, `domain`,
                                  `max-age`, `secure`, `version`, `httponly`
      % headers: dictionary ~~ None
        A dictionary mappging the header name to its value.
      % httpcode: int ~~ 200
        The HTTP response code to attach to the response.
    """
    if isinstance(content, unicode):
      self.content = content.encode('utf8')
    else:
      self.content = str(content)
    self.cookies = cookies
    self.httpcode = httpcode
    self.headers = headers or {}
    self.content_type = content_type

  def __repr__(self):
    return '<%s instance at %#x>' % (self.__class__.__name__, id(self))

  def __str__(self):
    return self.content
