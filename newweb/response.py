#!/usr/bin/python
"""newWeb response classes."""

# Standard modules
import httplib
from xml.sax import saxutils


class Response(object):
  """Defines a full HTTP response.

  The full response consists of a required content part, and then optional
  http response code, cookies, additional headers, and a content-type.
  """
  # Default content-type for Page objects
  CONTENT_TYPE = 'text/html'

  def __init__(self, content='', content_type=CONTENT_TYPE,
               httpcode=200, headers=None, **kwds):
    """Initializes a Page object.

    Arguments:
      @ content: str
        The content to return to the client. This can be either plain text, html
        or the contents of a file (images for example).
      % content_type: str ~~ CONTENT_TYPE ('text/html' by default)
        The content type of the response. This should NOT be set in headers.
      % httpcode: int ~~ 200
        The HTTP response code to attach to the response.
      % headers: dict ~~ None
        A dictionary with header names and their associated values.
    """
    self.charset = kwds.get('charset', 'utf8')
    self.text = content
    self.httpcode = httpcode
    self.headers = headers or {}
    if ';' not in content_type:
      content_type = '%s; charset=%s' % (content_type, self.charset)
    self.content_type = content_type

  # Get and set content-type header
  @property
  def content_type(self):
    return self.headers['Content-Type']

  @content_type.setter
  def content_type(self, content_type):
    current = self.headers.get('Content-Type', '')
    if ';' in current:
      content_type = '%s; %s' % (content_type, current.split(';', 1)[-1])
    self.headers['Content-Type'] = content_type

  # Get and set body text
  @property
  def text(self):
    return self.content

  @text.setter
  def text(self, content):
    if isinstance(content, unicode):
      self.content = content.encode(self.charset)
    else:
      self.content = str(content)

  # Retrieve a header list
  @property
  def headerlist(self):
    return [(key, val.encode('ascii')) for key, val in self.headers.iteritems()]

  @property
  def status(self):
    return '%d %s' % (self.httpcode, httplib.responses[self.httpcode])

  def __repr__(self):
    return '<%s instance at %#x>' % (self.__class__.__name__, id(self))

  def __str__(self):
    return self.content


class Redirect(Response):
  """A response tailored to do redirects."""
  REDIRECT_PAGE = (
      '<!DOCTYPE html><html><head><title>Page moved</title></head><body>'
      'Page moved, please follow <a href=%s>this link</a></body></html>')

  def __init__(self, location, httpcode=307):
    super(Redirect, self).__init__(
        content=self.REDIRECT_PAGE % saxutils.quoteattr(location),
        content_type='text/html',
        httpcode=httpcode,
        headers={'Location': location})
