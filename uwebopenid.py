#!/usr/bin/python

# standard imports
from underdark.libs.uweb import request as uwebrequest

# Custom imports
import openid
from openid.store import memstore
from openid.store import filestore
from openid.consumer import consumer
from openid.oidutil import appendArgs
from openid.cryptutil import randomString
from openid.fetchers import setDefaultFetcher, Urllib2Fetcher
from openid.extensions import pape, sreg

# Used with an OpenID provider affiliate program.
OPENID_PROVIDER_NAME = 'uweb OpenID'
OPENID_PROVIDER_URL ='https://www.myopenid.com/affiliate_signup?affiliate_id=39'

class Error(Exception):
  """A uweb OpenID error has occured"""


class InvalidOpenIdUrl(Error):
  """The supplied openIDurl is invalid"""


class InvalidOpenIdService(Error):
  """The supplied openID Service is invalid"""


class VerificationFailed(Error):
  """The verification for the user failed"""


class VerificationCanceled(Error):
  """The verification for the user was canceled"""


class OpenId(object):
  def __init__(self, request, cookiename='uwebopenid'):
    self.request = request
    self.session = None
    self.cookiename = cookiename

  def getConsumer(self, stateless=False):
    if stateless:
      store = None
    else:
      store = None
    return consumer.Consumer(self.getSession(), store)

  def getSession(self):
    """Return the existing session or a new session"""
    if self.session is not None:
      return self.session

    # Get value of cookie header that was sent
    if self.cookiename in self.request.cookies:
      sid = self.cookies.get(cookiename).value
    else:
      sid = randomString(16, '0123456789abcdef')

    session = {'id':sid}
    self.session = session
    return session

  def setSessionCookie(self):
    self.request.AddCookie(self.cookiename, sid)

  def Verify(self, openIdUrl, trustroot, returnurl, registrationData=False, phishingResistant=False, stateless=False, immediate=False):
    """
    Takes the openIdUrl from the user and sets up the request to send the user 
    to the correct page that will validate our trustroot to receive the data.
    
    Takes:
      OpenIdUrl: str, the user supplied openId url
      trstroot: str, the url of our webservice, will be displayed to the user as
                     the consuming url
      returnUrl: str, the url that will handle the Process step for the user 
                      being returned to us by the openId supplier
      registrationData: bool, do we want to request registration data for the 
                              user from the supplier
      phishingResistant: bool, do we want to use a phishing resistant openId 
                               auth policy
      stateless: bool, setup the authentication in stateless mode
      immediate: bool, use immediate mode.
      
    Returns either an uweb Page object redirectnig the user to the OpenId 
    provider or page with some variabeles
    """
    oidconsumer = self.getConsumer(stateless = stateless)
    try:
      request = oidconsumer.begin(openIdUrl)
    except consumer.DiscoveryFailure, exc:
      raise InvalidOpenIdUrl(openIdUrl)
    else:
      if request:
        if registrationData:
          self.requestRegistrationData(request)
          
        if phishingResistant:
          self.requestPAPEDetails(request)
        
        if request.shouldSendRedirect():
          redirect_url = request.redirectURL(
              trustroot, returnurl, immediate=immediate)
          return uweb.uwebrequest(httpcode=302).AddHeader('Location', redirect_url)
        else:
          return request.htmlMarkup(
              trustroot, returnurl,
              form_tag_attrs={'id':'openid_message'},
              immediate=immediate)
      else:
        raise InvalidOpenIdService()

  def requestRegistrationData(self, request):
    sreg_request = sreg.SRegRequest(
        required=['nickname'], optional=['fullname', 'email'])
    request.addExtension(sreg_request)

  def requestPAPEDetails(self, request):
    pape_request = pape.Request([pape.AUTH_PHISHING_RESISTANT])
    request.addExtension(pape_request)

  def doProcess(self):
    """Handle the redirect from the OpenID server."""
    oidconsumer = self.getConsumer()

    # Ask the library to check the response that the server sent
    # us.  Status is a code indicating the response type. info is
    # either None or a string containing more information about
    # the return type.
    url = 'http://'+self.request.req.env['HTTP_HOST']+self.request.req.env['PATH_INFO']
    queryargs = dict((key, value[0]) for key, value in self.request.get.items())
    info = oidconsumer.complete(queryargs, url)

    sreg_resp = None
    pape_resp = None
    display_identifier = info.getDisplayIdentifier()

    if info.status == consumer.FAILURE and display_identifier:
      # In the case of failure, if info is non-None, it is the
      # URL that we were verifying. We include it in the error
      # message to help the user figure out what happened.
      raise VerificationFailed("Verification of %s failed: %s" % (
          display_identifier, info.message))

    elif info.status == consumer.SUCCESS:
      # Success means that the transaction completed without
      # error. If info is None, it means that the user cancelled
      # the verification.
    
      # This is a successful verification attempt. If this
      # was a real application, we would do our login,
      # comment posting, etc. here.
      sreg_resp = sreg.SRegResponse.fromSuccessResponse(info)
      pape_resp = pape.Response.fromSuccessResponse(info)
      # You should authorize i-name users by their canonicalID,
      # rather than their more human-friendly identifiers.  That
      # way their account with you is not compromised if their
      # i-name registration expires and is bought by someone else.
      return (display_identifier, sreg_resp, pape_resp, info.endpoint.CanonicalID)

    elif info.status == consumer.CANCEL:
      # cancelled
      raise VerificationCanceled('Verification cancelled')

    elif info.status == consumer.SETUP_NEEDED:
      if info.setup_url:
        message = '<a href=%s>Setup needed</a>' % info.setup_url
      else:
        # This means auth didn't succeed, but you're welcome to try
        # non-immediate mode.
        message = 'Setup needed'
    else:
      # Either we don't understand the code or there is no
      # openid_url included with the error. Give a generic
      # failure message. The library should supply debug
      # information in a log.
      raise VerificationFailed('Verification failed.')
