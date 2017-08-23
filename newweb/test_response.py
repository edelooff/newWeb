#!/usr/bin/python
"""Tests for the response module."""

# Standard modules
import unittest

# Unittest target
from . import response


class RedirectTest(unittest.TestCase):
  """Tests for redirect responses."""

  def testRedirect(self):
    """Redirects generate a minimal body with a hyperlink for dumb clients."""
    redirect = response.Redirect('https://google.com')
    self.assertIn('https://google.com', redirect.text)

  def testRedirectEscapedBodyLink(self):
    """Redirect links are correctly entity-escaped to prevent XSS and such."""
    redirect = response.Redirect('<script>alert("hi")</script>')
    self.assertNotIn('<script>', redirect.text)
    self.assertIn('&lt;script&gt;', redirect.text)


if __name__ == '__main__':
  unittest.main(testRunner=unittest.TextTestRunner(verbosity=2))
