#!/usr/bin/python2.5
"""Tests for the templateparser module."""
__author__ = 'Elmer de Looff <elmer@underdark.nl>'
__version__ = '1.0'

# Too many public methods
# pylint: disable-msg=R0904

# Standard modules
import os
import unittest

# Unittest target
import templateparser as templateparser


class TemplateBasicTags(unittest.TestCase):
  """Tests validity and parsing of simple tags."""
  def setUp(self):
    """Sets up a parser instance, as it never changes."""
    self.tmpl = templateparser.Template

  def testPlainTemplate(self):
    """Templates without tags get returned whole"""
    template = 'Template without any tags'
    parsed_template = self.tmpl(template).Parse()
    self.assertEqual(template, parsed_template)
    self.assertTrue(isinstance(parsed_template, templateparser.SafeString))

  def testSingleTagTemplate(self):
    """Templates with basic tags get returned proper"""
    template = 'Template with [single] tag'
    result = 'Template with just one tag'
    self.assertEqual(result, self.tmpl(template).Parse(single='just one'))

  def testCasedTag(self):
    """Template tags may contain uppercase and lowercase or a mix thereof"""
    template = 'The parser has no trouble with [cAsE] case.'
    result = 'The parser has no trouble with mixed case.'
    self.assertEqual(result, self.tmpl(template).Parse(cAsE='mixed'))

  def testUnderscoredTag(self):
    """Template tags may contains underscores as part of their name"""
    template = 'The template may contain [under_scored] tags.'
    result = 'The template may contain underscored tags.'
    self.assertEqual(
        result, self.tmpl(template).Parse(under_scored='underscored'))

  def testMultiTagTemplate(self):
    """Templates with multiple (repeating) tags get parsed properly"""
    template = '[adjective] [noun] are better than other [noun].'
    result = 'Beefy cows are better than other cows.'
    self.assertEqual(
        result, self.tmpl(template).Parse(noun='cows', adjective='Beefy'))

  def testBrokenTags(self):
    """Empty tags or tags containing whitespace are not actual tags"""
    template = 'This [ is a ] broken [] template, ][, really'
    self.assertEqual(template, self.tmpl(template).Parse(
        **{' is a ': 'HORRIBLY', '': ', NASTY'}))

  def testBadCharacterTags(self):
    """Tags with bad characters are not considered tags"""
    bad_chars = """ :~!@#$%^&*()+-={}\|;':",./<>? """
    template = ''.join('[%s] [check]' % char for char in bad_chars)
    result = ''.join('[%s] ..' % char for char in bad_chars)
    replaces = dict((char, 'FAIL') for char in bad_chars)
    replaces['check'] = '..'
    self.assertEqual(result, self.tmpl(template).Parse(**replaces))

  def testUnreplacedTag(self):
    """Template tags for which there is no replacement still exist in output"""
    template = 'Template with an [undefined] tag.'
    self.assertEqual(template, self.tmpl(template).Parse())

  def testBracketsInsideTag(self):
    """The last opening bracket and first closing bracket are the delimiters"""
    template = 'Template tags may not contain [[spam] [eggs]].'
    result = 'Template tags may not contain [opening or closing brackets].'
    self.assertEqual(result, self.tmpl(template).Parse(
        **{'[spam': 'EPIC', 'eggs]': 'FAIL',
           'spam': 'opening or', 'eggs': 'closing brackets'}))


class TemplateIndexedTags(unittest.TestCase):
  """Tests the handling of complex tags (those with attributes/keys/indexes)."""
  def setUp(self):
    """Sets up a parser instance, as it never changes."""
    self.tmpl = templateparser.Template

  def testTemplateMappingKey(self):
    """Template tags can address mappings properly"""
    template = 'This uses a [dictionary:key].'
    result = 'This uses a spoon.'
    self.assertEqual(
        result, self.tmpl(template).Parse(dictionary={'key': 'spoon'}))

  def testTemplateIndexing(self):
    """Template tags can access indexed iterables"""
    template = 'Template that grabs the [obj:2] key from the given tuple/list.'
    result = 'Template that grabs the third key from the given tuple/list.'
    numbers = 'first', 'second', 'third'
    self.assertEqual(result, self.tmpl(template).Parse(obj=numbers))
    numbers = list(numbers)
    self.assertEqual(result, self.tmpl(template).Parse(obj=numbers))

  def testTemplateAttributes(self):
    """Template tags will do attribute lookups, but only if 'by key' fails"""
    class Mapping(dict):
      """A subclass of a dictionary, so we can define attributes on it."""
      NAME = 'attribute'

    template = 'Template used [tag:NAME] lookup.'
    lookup_attr = 'Template used attribute lookup.'
    lookup_dict = 'Template used key (mapping) lookup.'

    mapp = Mapping()
    self.assertEqual(lookup_attr, self.tmpl(template).Parse(tag=mapp))
    mapp['NAME'] = 'key (mapping)'
    self.assertEqual(lookup_dict, self.tmpl(template).Parse(tag=mapp))

  def testTemplateMissingIndexes(self):
    """Complex tags with missing indexes (:index) will NOT be replaced"""
    class Object(object):
      """A simple object to store an attribute on."""
      NAME = 'Freeman'

    template = 'Hello [titles:1] [names:NAME], how is [names:other] [date:now]?'
    result = 'Hello [titles:1] Freeman, how is [names:other] [date:now]?'
    self.assertEqual(result, self.tmpl(template).Parse(
        titles=['Mr'], names=Object(), date={}))

  def testTemplateMultipleIndexing(self):
    """Template tags can contain nested indexes"""
    template = 'Welcome to the [foo:bar:zoink].'
    result = 'Welcome to the World.'
    self.assertEqual(result, self.tmpl(template).Parse(
        foo={'bar': {'zoink': 'World'}}))

  def testPerformance(self):
    """Basic performance test for 2 template replacements"""
    for _template in range(100):
      template = 'This [obj:foo] is just a quick [bar]'
      tmpl = self.tmpl(template)
      for _parse in xrange(100):
        tmpl.Parse(obj={'foo':'text'}, bar='hack')

class TemplateTagFunctions(unittest.TestCase):
  """Tests the functions that are performed on replaced tags."""
  def setUp(self):
    """Sets up a parser instance, as it never changes."""
    self.parser = templateparser.Parser()

  def testPipedFunctionUse(self):
    """Piped functions do not break the parser"""
    template = 'This function does [none|raw].'
    result = 'This function does "nothing".'
    self.assertEqual(result, self.parser.ParseString(
        template, none='"nothing"'))

  def testDefaultHtmlEscapeFunction(self):
    """The default function escapes HTML entities, and works properly"""
    default = 'This function does [none].'
    escaped = 'This function does [none|html].'
    result = 'This function does &quot;nothing&quot;.'
    self.assertEqual(result, self.parser.ParseString(default, none='"nothing"'))
    self.assertEqual(result, self.parser.ParseString(escaped, none='"nothing"'))

  def testNoDefaultForSafeString(self):
    """SafeString objects are not fed through the default templating function"""
    first_template = 'Hello doctor [name]'
    second_template = '<assistant> [quote].'
    result = '<assistant> Hello doctor &quot;Who&quot;.'
    result_first = self.parser.ParseString(first_template, name='"Who"')
    result_second = self.parser.ParseString(second_template, quote=result_first)
    self.assertEqual(result, result_second)

  def testCustomFunction(self):
    """Custom functions added to the parser work as expected"""
    self.parser.RegisterFunction('twice', lambda x: x + ' ' + x)
    template = 'The following will be stated [again|twice].'
    result = 'The following will be stated twice twice.'
    self.assertEqual(result, self.parser.ParseString(template, again='twice'))

  def testMultipleFunctions(self):
    """Multiple functions can be piped after one another"""
    self.parser.RegisterFunction('len', len)
    self.parser.RegisterFunction('count', lambda x: '%s characters' % x)
    template = 'A replacement processed by two functions: [spam|len|count].'
    result = 'A replacement processed by two functions: 8 characters.'
    self.assertEqual(result, self.parser.ParseString(template, spam='ham&eggs'))

  def testFunctionSeparation(self):
    """Template functions are only called for fragments that require them"""
    fragments_received = []
    def CountAndReturn(fragment):
      """Returns the given fragment after adding it to a counter list."""
      fragments_received.append(fragment)
      return fragment

    self.parser.RegisterFunction('x', CountAndReturn)
    template = 'X only has [num|x] call, else it\'s [expletive] [noun|raw].'
    result = 'X only has one call, else it\'s horribly broken.'
    self.assertEqual(result, self.parser.ParseString(
        template, num='one', expletive='horribly', noun='broken'))
    self.assertEqual(1, len(fragments_received))


class TemplateUnicodeSupport(unittest.TestCase):
  """TemplateParser handles Unicode gracefully."""
  def setUp(self):
    """Sets up a parser instance, as it never changes."""
    self.parser = templateparser.Parser()

  def testUnicodeInput(self):
    """TemplateParser can handle unicode objects on input, converts to utf8"""
    template = 'Underdark Web framework, also known as [name].'
    result = u'Underdark Web framework, also known as \xb5Web.'.encode('utf8')
    name = u'\xb5Web'
    self.assertEqual(result, self.parser.ParseString(template, name=name))

  def testCreoleTemplateParsing(self):
    """The Creole module's return of <unicode> doesn't break the parser"""
    from underdark.libs import creole
    self.parser.RegisterFunction('creole', creole.CreoleToHtml)
    template = 'Creole [expression|creole]!'
    result = 'Creole <p><strong>rocks</strong> \xc2\xb5Web</p>\n!'
    self.assertEqual(result, self.parser.ParseString(
        template, expression=u'**rocks** \xb5Web'))

  def testTemplateFunctionReturnUnicode(self):
    """Template functions may return unicode objects, they are later encoded"""
    function_result = u'No more \N{BLACK HEART SUIT}'
    def StaticReturn(_fragment):
      """Returns a static string, for any input fragment."""
      return function_result

    self.parser.RegisterFunction('nolove', StaticReturn)
    template = '[love|nolove]'
    result = function_result.encode('utf8')
    self.assertEqual(result, self.parser.ParseString(template, love='love'))


class TemplateControlFunctions(unittest.TestCase):
  """TemplateParser properly handles the include statement."""
  def setUp(self):
    """Sets up a testbed."""
    self.inline_template = 'This is a subtemplate by [name].'
    self.parser = templateparser.Parser()
    self.tmpl = templateparser.Template

  def testInlineExisting(self):
    """{{ inline }} Parser will inline an already existing template reference"""
    self.parser['template'] = self.tmpl(self.inline_template)
    template = '{{ inline template }}'
    result = 'This is a subtemplate by Elmer.'
    self.assertEqual(result, self.parser.ParseString(template, name='Elmer'))

  def testInlineFile(self):
    """{{ inline }} Parser will load an inlined template from file if needed"""
    with file('tmp_template', 'w') as inline_file:
      inline_file.write(self.inline_template)
      inline_file.flush()
    try:
      template = '{{ inline tmp_template }}'
      result = 'This is a subtemplate by Elmer.'
      self.assertEqual(result, self.parser.ParseString(template, name='Elmer'))
    finally:
      os.unlink('tmp_template')

  def testLoopCount(self):
    """{{ for }} Parser will loop once for each item in the for loop"""
    template = '{{ for num in [range] }}x{{ endfor }}'
    result = 'xxxxx'
    self.assertEqual(result, self.parser.ParseString(template, range=range(5)))

  def testLoopReplaceBasic(self):
    """{{ for }} The loop variable is available via tagname"""
    template = '{{ for var in [numbers] }}number [var], {{ endfor }}'
    result = 'number 0, number 1, number 2, number 3, number 4, '
    self.assertEqual(result, self.parser.ParseString(
        template, numbers=range(5)))

  def testLoopReplaceScope(self):
    """{{ for }} The loop variable overwrites similar names from outer scope"""
    template = '[num] {{ for num in [numbers] }}[num], {{ endfor }}[num]'
    result = 'OUTER 0, 1, 2, 3, 4, OUTER'
    self.assertEqual(result, self.parser.ParseString(
        template, numbers=range(5), num='OUTER'))

  def testLoopOverIndexedTag(self):
    """{{ for }} Loops can be performed over indexed tags"""
    template = '{{ for num in [numbers:1] }}x{{ endfor }}'
    result = 'xxxxx'
    self.assertEqual(result, self.parser.ParseString(
      template, numbers=[range(10), range(5), range(10)]))

if __name__ == '__main__':
  unittest.main(testRunner=unittest.TextTestRunner(verbosity=2))
