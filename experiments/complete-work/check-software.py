"""External requirement checks, run from a clean reviewer workspace."""
import io
import unittest

import frontmatter
from frontmatter.default_handlers import JSONHandler, TOMLHandler, YAMLHandler


class MetadataCollisionTests(unittest.TestCase):
    def test_roundtrip_and_file_apis(self):
        metadata = {'content': 'metadata body', 'handler': 'metadata handler',
                    'title': 'café', 'nested': {'value': 7}}
        handlers = [YAMLHandler(), JSONHandler(), TOMLHandler()]
        for handler in handlers:
            with self.subTest(handler=type(handler).__name__):
                original = frontmatter.Post('Document body', handler)
                original.metadata.update(metadata)
                serialized = frontmatter.dumps(original)
                for post in [frontmatter.loads(serialized), frontmatter.load(io.StringIO(serialized))]:
                    self.assertEqual(post.content, 'Document body')
                    self.assertEqual(post.metadata, metadata)
                    self.assertIsInstance(post.handler, type(handler))
                    self.assertEqual(frontmatter.loads(frontmatter.dumps(post)).metadata, metadata)

    def test_constructor_compatibility(self):
        handler = YAMLHandler()
        for post in [frontmatter.Post('body', handler, title='t'),
                     frontmatter.Post(content='body', handler=handler, title='t')]:
            self.assertEqual(post.content, 'body')
            self.assertIs(post.handler, handler)
            self.assertEqual(post.metadata, {'title': 't'})


if __name__ == '__main__':
    unittest.main()
