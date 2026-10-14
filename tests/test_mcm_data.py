import unittest

from coevo.mcm_data import before_year, decode_csv


class MCMDataTests(unittest.TestCase):
    def test_target_and_future_outcomes_are_removed(self):
        rows = [{'Year': str(y), 'NOC': 'X'} for y in (2012, 2016, 2020, 2024, 2028)]
        self.assertEqual([r['Year'] for r in before_year(rows, 2020)], ['2012', '2016'])

    def test_original_legacy_encoding_is_decoded_without_replacement(self):
        text, encoding = decode_csv('Sport,café\n'.encode('cp1252'))
        self.assertEqual(text, 'Sport,café\n')
        self.assertEqual(encoding, 'cp1252')


if __name__ == '__main__':
    unittest.main()
