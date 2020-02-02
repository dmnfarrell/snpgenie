from setuptools import setup
import sys,os

with open('pathogenie/description.txt') as f:
    long_description = f.read()

setup(
    name = 'pathogenie',
    version = '0.1.0',
    description = 'variant calling and phylogenies from NGS data',
    long_description = long_description,
    url='https://github.com/dmnfarrell/btbgenie',
    license='GPL v3',
    author = 'Damien Farrell',
    author_email = 'farrell.damien@gmail.com',
    packages = ['pathogenie'],
    package_data={'pathogenie': ['data/*.*','logo.png',
                  'description.txt']
                 },
    install_requires=['numpy>=1.10',
                      'pandas>=0.24',
                      'matplotlib>=3.0',
                      'biopython>=1.5',
                      'pyside2>=5.1',
                      'future'],
    entry_points = {
        'console_scripts': [            
            'pathogeniegui=pathogenie.gui:main']
            },
    classifiers = ['Operating System :: OS Independent',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3.7',
            'Operating System :: MacOS :: MacOS X',
            'Operating System :: Microsoft :: Windows',
            'Operating System :: POSIX',
            'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
            'Development Status :: 4 - Beta',
            'Intended Audience :: Science/Research',
            'Topic :: Scientific/Engineering :: Bio-Informatics'],
    keywords = ['bioinformatics','biology','genomics']
)
