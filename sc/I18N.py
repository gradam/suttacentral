""" Support for internationalization (I18N is the usual abbreviation) 

The I18N class allows access to the data stored in the I18N CSV file.
The CSV file will have an arbitrary number of columns, the first being
the key by which localizable elements are identified. The subsequent 
columns are named according to ISO language conventions. Each language
has one and only one column (this should be checked!) Some values
may be missing and defaults provided. So something like this:

    key,en,vn
    dn1,The All Embracing Net of Views,Kinh Phạm võng
    dn2,The Fruits of Recluseship,,

This data is slurped up into memory along with the rest of the IMM.
At this point we ignore issues of performance and memory usage, but
I'm happy to change things as the design becomes more clear.

USAGE:

>>> from sc import I18N
>>> localizer = I18N.I18N()
>>> english = localizer.localize('dn1', 'en')
>>> print(english)
The All-embracing Net of Views

"""

import csv
import sc

from sc.util import ScCsvDialect

class I18N:
    def __init__(self):
        self.i18n_data = {}
        self.file_name = 'I18N.csv'
        self.column_names = []

    """ Open the CSV file containing our localizations
        with & as used to make sure the file is unlocked
        if an exception is thrown. """
    def read_data(self):
        with (sc.table_dir / self.file_name).open('r',
              encoding='utf-8', newline='') as f:
            reader = csv.reader(f, dialect=ScCsvDialect)
            # The first line in the CSV file contains 
            # the column names. Includes key and languages.
            self.column_names = next(reader)

            # Process each line of data one by one.
            for line in reader:
                self.add_line(line)

    """ Add a language to which translations can be added. """
    def add_language(self, language):
        self.i18n_data[language] = {}

    """ Return true if the language has already been
        added to the i18n_data structure """
    def language_exists(self, language):
        return language in self.i18n_data
    
    """ Given the column number return the language """
    def get_language(self, column_number):
        return self.column_names[column_number]

    """ Add a translation for a given key and language """
    def add_translation(self, language, key, translation):
        self.i18n_data[language][key] = translation

    """ Given a key and a language, return the translation 
        If we can't find what we are looking for, return 
        an empty string. Another way of handling missing data
        would be to throw an exception. But we don't do that. """
    def get_translation(self, language, key):
        if language not in self.i18n_data: return ''
        if key not in self.i18n_data[language]: return ''

        return self.i18n_data[language][key]

    """ Given the data for a single line in the CSV file
    add whatever translations are present in the line
    to the i18n_data structure """
    def add_line(self, line):
        if not any(line): # Drop entirely blank lines
            return
        if line[0].startswith('#'): # Drop comment lines
            return
        
        key = line[0] # Get key for this line.

        for index, translation in enumerate(line):
            
            # Have the key, move on to language columns.
            if index == 0:
                continue

            language = self.get_language(index)
            if self.language_exists(language):
                self.add_translation(language, key, translation)
            else:
                self.add_language(language)
                self.add_translation(language, key, translation)
                
